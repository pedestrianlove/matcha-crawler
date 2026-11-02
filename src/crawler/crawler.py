"""Autonomous crawler for Marukyu Koyamaen product variety stock status."""

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from playwright.sync_api import BrowserContext, Page, sync_playwright

from crawler.parser import parse_product_page_html

BASE_PRODUCT_URL = "https://www.marukyu-koyamaen.co.jp/english/shop/products/{product_id}"

logger = logging.getLogger(__name__)


def build_product_url(product_id: str) -> str:
    """Build the product page URL from the product ID."""
    return BASE_PRODUCT_URL.format(product_id=product_id.strip())


def load_product_ids(filepath: str | Path) -> List[str]:
    """Load product IDs from a JSON file containing an array of strings."""
    path = Path(filepath)
    if not path.exists():
        raise FileNotFoundError(f"Product file not found: {filepath}")

    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list):
        raise ValueError(f"Expected a JSON array of product IDs in {filepath}")

    return [str(pid).strip() for pid in data if pid]


def crawl_product(page: Page, product_id: str, timeout: int = 30000) -> Dict[str, Any]:
    """Crawl a single product page and return varieties stock status."""
    url = build_product_url(product_id)
    logger.info("Crawling %s (url: %s)...", product_id, url)

    try:
        page.goto(url, timeout=timeout, wait_until="domcontentloaded")
        # Wait for either .product-form-rows or single_add_to_cart_button or network idle
        try:
            page.wait_for_selector(".product-form-rows, .product-form-row", timeout=5000)
        except Exception:
            logger.debug("Selector wait timed out or not immediately visible for %s", product_id)

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
    product_ids: List[str],
    user_data_dir: Optional[str] = None,
    storage_state_path: Optional[str] = None,
    headless: bool = True,
    timeout: int = 30000,
) -> List[Dict[str, Any]]:
    """Run crawler over a list of product IDs using Playwright.

    Supports reusing existing authenticated browser sessions via:
    1. Persistent user data directory (e.g. ~/.config/google-chrome, or ./browser_profile)
    2. Saved Playwright storage_state (cookies/session JSON file)
    """
    results: List[Dict[str, Any]] = []

    with sync_playwright() as p:
        context: BrowserContext
        browser = None

        if user_data_dir:
            user_data_path = str(Path(user_data_dir).expanduser().resolve())
            logger.info("Using persistent browser context at: %s", user_data_path)
            context = p.chromium.launch_persistent_context(
                user_data_dir=user_data_path,
                headless=headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            page = context.pages[0] if context.pages else context.new_page()
        else:
            browser = p.chromium.launch(
                headless=headless,
                args=["--no-sandbox", "--disable-setuid-sandbox"],
            )
            context_kwargs = {}
            if storage_state_path and Path(storage_state_path).exists():
                logger.info("Loading existing storage state from: %s", storage_state_path)
                context_kwargs["storage_state"] = str(Path(storage_state_path).resolve())
            context = browser.new_context(**context_kwargs)
            page = context.new_page()

        try:
            for product_id in product_ids:
                res = crawl_product(page, product_id, timeout=timeout)
                results.append(res)
        finally:
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
    results = run_crawler(
        product_ids=product_ids,
        user_data_dir=args.user_data_dir,
        storage_state_path=args.storage_state,
        headless=not args.headed,
        timeout=args.timeout,
    )

    output_json = json.dumps(results, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(output_json, encoding="utf-8")
        logger.info("Saved output to %s", args.output)
    else:
        print(output_json)


if __name__ == "__main__":
    main()
