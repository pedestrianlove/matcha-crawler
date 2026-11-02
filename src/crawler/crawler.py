"""Autonomous crawler for Marukyu Koyamaen product variety stock status."""

import argparse
import json
import logging
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import BrowserContext, Page, sync_playwright

from crawler.parser import parse_product_page_html

BASE_PRODUCT_URL = (
    "https://www.marukyu-koyamaen.co.jp/english/shop/products/{product_id}"
)
TARGET_DOMAIN = urlparse(BASE_PRODUCT_URL).hostname.replace("www.", "")

logger = logging.getLogger(__name__)


def build_product_url(product_id: str) -> str:
    """Build the product page URL from the product ID."""
    return BASE_PRODUCT_URL.format(product_id=product_id.strip())


def load_product_ids(filepath: str | Path) -> list[str]:
    """Load product IDs from a JSON file containing an array of strings."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Product file not found: {filepath}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array of product IDs in {filepath}")

    return [str(pid).strip() for pid in data if pid]


def import_session_credentials(target_domain: str, output_path: Path) -> Path:
    """Import target_domain cookies from browser profiles into session.json.

    Raises RuntimeError listing searched paths if no credentials found.
    """
    import shutil
    import sqlite3
    import tempfile

    searched_paths: list[str] = []

    # 1. Firefox profiles
    ff_dir = Path(os.path.expandvars(r"%APPDATA%\Mozilla\Firefox\Profiles"))
    if ff_dir.exists():
        for p in sorted(
            ff_dir.iterdir(),
            key=lambda x: x.stat().st_mtime if x.exists() else 0,
            reverse=True,
        ):
            db = p / "cookies.sqlite"
            if db.exists():
                searched_paths.append(str(db))
                with tempfile.TemporaryDirectory() as tmp:
                    temp_db = Path(tmp) / "cookies.sqlite"
                    shutil.copy2(db, temp_db)
                    conn = sqlite3.connect(temp_db)
                    cursor = conn.cursor()
                    cursor.execute(
                        "SELECT host, name, value, path, expiry, isSecure, isHttpOnly, sameSite "
                        "FROM moz_cookies WHERE host LIKE ?",
                        (f"%{target_domain}%",),
                    )
                    rows = cursor.fetchall()
                    conn.close()

                    if rows:
                        cookies = []
                        same_site_map = {0: "None", 1: "Lax", 2: "Strict"}
                        for r in rows:
                            secure = bool(r[5])
                            ss = same_site_map.get(r[7], "Lax")
                            if ss == "None" and not secure:
                                ss = "Lax"
                            exp = r[4]
                            if exp and exp > 1e11:
                                exp = exp / 1000
                            cookies.append(
                                {
                                    "name": r[1],
                                    "value": r[2],
                                    "domain": r[0],
                                    "path": r[3],
                                    "expires": float(exp) if exp else -1,
                                    "httpOnly": bool(r[6]),
                                    "secure": secure,
                                    "sameSite": ss,
                                }
                            )
                        output_path.write_text(
                            json.dumps({"cookies": cookies, "origins": []}, indent=2),
                            encoding="utf-8",
                        )
                        logger.info(
                            "Imported %d cookies from %s into %s",
                            len(cookies),
                            db,
                            output_path,
                        )
                        return output_path

    # 2. Chrome profiles (for path reporting if not found)
    chrome_dir = Path(os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data"))
    if chrome_dir.exists():
        for item in chrome_dir.iterdir():
            db = item / "Network" / "Cookies"
            if db.exists():
                searched_paths.append(str(db))

    paths_str = (
        "\n".join(f"  - {p}" for p in searched_paths)
        if searched_paths
        else "  (none found)"
    )
    raise RuntimeError(
        f"No credentials or Cloudflare challenge clearance found for '{target_domain}'.\n"
        f"Please log in or solve the Cloudflare challenge in your browser first.\n"
        f"Searched paths:\n{paths_str}"
    )


def crawl_product(page: Page, product_id: str, timeout: int = 30000) -> dict[str, Any]:
    """Crawl a single product page and return varieties stock status."""
    url = build_product_url(product_id)
    logger.info("Crawling %s (url: %s)...", product_id, url)

    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        # Wait for either .product-form-rows or single_add_to_cart_button or network idle
        try:
            page.wait_for_selector(
                ".product-form-rows, .product-form-row", timeout=5000
            )
        except Exception:
            logger.debug(
                "Selector wait timed out or not immediately visible for %s", product_id
            )

        content = page.content()
        varieties = parse_product_page_html(content)

        return {
            "product_id": product_id,
            "url": url,
            "status": "success",
            "varieties": varieties,
        }
    except Exception as e:
        logger.error("Failed to crawl product %s: %s", product_id, e)
        return {
            "product_id": product_id,
            "url": url,
            "status": "error",
            "error": str(e),
            "varieties": [],
        }


def run_crawler(
    product_ids: list[str],
    user_data_dir: str | None = None,
    storage_state_path: str | None = None,
    headless: bool = True,
    timeout: int = 30000,
    browser_type: str = "firefox",
    poll: bool = False,
    interval: float = 15.0,
    max_polls: int | None = None,
    on_poll: Callable[[list[dict[str, Any]]], None] | None = None,
) -> list[dict[str, Any]]:
    """Run crawler over a list of product IDs using Playwright.

    Supports reusing existing authenticated browser sessions via:
    1. Persistent user data directory (e.g. ~/.config/google-chrome, or ./browser_profile)
    2. Saved Playwright storage_state (cookies/session JSON file)
    """
    results: list[dict[str, Any]] = []

    with sync_playwright() as p:
        context: BrowserContext | None = None
        browser = None
        context_kwargs: dict[str, Any] = {}
        if browser_type == "chrome":
            launcher = p.chromium
            launch_kwargs = {"channel": "chrome"}
        elif browser_type == "chromium":
            launcher = p.chromium
            launch_kwargs = {}
        else:
            launcher = p.firefox
            launch_kwargs = {}

        if user_data_dir:
            user_data_path = str(Path(user_data_dir).expanduser().resolve())
            logger.info("Using persistent browser context at: %s", user_data_path)
            context = launcher.launch_persistent_context(
                user_data_dir=user_data_path,
                headless=headless,
                **launch_kwargs,
            )
        else:
            browser = launcher.launch(
                headless=headless,
                **launch_kwargs,
            )
            if storage_state_path and Path(storage_state_path).exists():
                logger.info(
                    "Loading existing storage state from: %s", storage_state_path
                )
                context_kwargs["storage_state"] = str(
                    Path(storage_state_path).resolve()
                )

        try:
            poll_count = 0
            while True:
                poll_count += 1
                current_results = []

                if context:
                    page = context.new_page()
                    try:
                        for product_id in product_ids:
                            res = crawl_product(page, product_id, timeout=timeout)
                            current_results.append(res)
                    finally:
                        page.close()
                else:
                    cycle_context = browser.new_context(**context_kwargs)
                    cycle_page = cycle_context.new_page()
                    try:
                        for product_id in product_ids:
                            res = crawl_product(cycle_page, product_id, timeout=timeout)
                            current_results.append(res)
                    finally:
                        cycle_context.close()

                results = current_results
                if on_poll:
                    on_poll(results)

                if not poll or (max_polls is not None and poll_count >= max_polls):
                    break

                logger.info("Waiting %.1fs until next poll...", interval)
                time.sleep(interval)
        except KeyboardInterrupt:
            logger.info("Polling stopped by user.")
        finally:
            if context:
                context.close()
            if browser:
                browser.close()

    return results


def main() -> None:
    """CLI entrypoint."""
    parser = argparse.ArgumentParser(
        description="Autonomous crawler for Marukyu Koyamaen product varieties stock status."
    )
    parser.add_argument(
        "-p",
        "--products",
        default="products.json",
        help="Path to products.json (default: products.json)",
    )
    parser.add_argument(
        "-o",
        "--output",
        default=None,
        help="Path to output JSON file (default: stdout)",
    )
    parser.add_argument(
        "--browser",
        default="firefox",
        choices=["firefox", "chromium", "chrome"],
        help="Browser backend: firefox, chromium, or chrome (default: firefox)",
    )
    parser.add_argument(
        "--user-data-dir",
        default=os.environ.get("CHROME_USER_DATA_DIR"),
        help="Path to browser user data directory for persistent authenticated session",
    )
    parser.add_argument(
        "--storage-state",
        default=os.environ.get("STORAGE_STATE_PATH", "session.json"),
        help="Path to saved storage state (cookies/session) JSON file",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Run browser in headed mode (default is headless)",
    )
    parser.add_argument(
        "--poll",
        action="store_true",
        help="Continuously poll product stock at a periodic interval",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=15.0,
        help="Polling interval in seconds (default: 15.0)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30000,
        help="Navigation timeout in milliseconds (default: 30000)",
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Enable verbose logging",
    )

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    product_ids = load_product_ids(args.products)
    storage_state_path = args.storage_state
    if not args.user_data_dir:
        state_file = Path(storage_state_path)
        if not state_file.exists():
            import_session_credentials(TARGET_DOMAIN, state_file)

    def handle_result(res: list[dict[str, Any]]) -> None:
        output_json = json.dumps(res, indent=2, ensure_ascii=False)
        if args.output:
            Path(args.output).write_text(output_json, encoding="utf-8")
            logger.info("Saved output to %s", args.output)
        else:
            print(output_json)

    results = run_crawler(
        product_ids=product_ids,
        user_data_dir=args.user_data_dir,
        storage_state_path=args.storage_state,
        headless=not args.headed,
        timeout=args.timeout,
        browser_type=args.browser,
        poll=args.poll,
        interval=args.interval,
        on_poll=handle_result if args.poll else None,
    )

    if not args.poll:
        handle_result(results)


if __name__ == "__main__":
    main()
