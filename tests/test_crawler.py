"""Tests for crawler configuration, routing, and browser-based crawling."""

import json
from pathlib import Path

import pytest
from playwright.sync_api import sync_playwright

from crawler.crawler import (
    build_product_url,
    crawl_product,
    import_session_credentials,
    load_product_ids,
    main,
    run_crawler,
)
from tests.test_parser import SAMPLE_PRODUCT_HTML


def test_build_product_url():
    url = build_product_url("1151020c1")
    assert url == "https://www.marukyu-koyamaen.co.jp/english/shop/products/1151020c1"


def test_load_product_ids(tmp_path: Path):
    sample_file = tmp_path / "products.json"
    sample_file.write_text(json.dumps(["1151020c1", "2251020c2"]), encoding="utf-8")

    ids = load_product_ids(sample_file)
    assert ids == ["1151020c1", "2251020c2"]


def test_load_product_ids_invalid(tmp_path: Path):
    sample_file = tmp_path / "invalid.json"
    sample_file.write_text(json.dumps({"product": "1151020c1"}), encoding="utf-8")

    with pytest.raises(ValueError):
        load_product_ids(sample_file)


def test_crawl_product_with_mocked_route():
    product_id = "1151020c1"
    target_url = build_product_url(product_id)

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        page = context.new_page()

        # Route the target url to return our mock HTML
        def handle_route(route):
            route.fulfill(
                status=200,
                content_type="text/html",
                body=SAMPLE_PRODUCT_HTML,
            )

        page.route(target_url, handle_route)

        result = crawl_product(page, product_id)
        assert result["product_id"] == "1151020c1"
        assert result["status"] == "success"
        assert len(result["varieties"]) == 4

        # Check stock values
        varieties = result["varieties"]
        assert varieties[0]["variety"] == "Can 40g"
        assert varieties[0]["in_stock"] is True
        assert varieties[1]["variety"] == "Can 100g"
        assert varieties[1]["in_stock"] is False

        browser.close()


def test_run_crawler_with_mocked_route(tmp_path: Path):
    products_file = tmp_path / "products.json"
    products_file.write_text(json.dumps(["1151020c1"]), encoding="utf-8")
    product_ids = load_product_ids(products_file)

    target_url = build_product_url(product_ids[0])

    with sync_playwright() as p:
        browser = p.firefox.launch(headless=True, args=["--no-sandbox"])
        context = browser.new_context()
        page = context.new_page()

        page.route(
            target_url,
            lambda route: route.fulfill(
                status=200,
                content_type="text/html",
                body=SAMPLE_PRODUCT_HTML,
            ),
        )

        res = crawl_product(page, product_ids[0])
        assert res["status"] == "success"
        assert res["varieties"][0]["in_stock"] is True
        assert res["varieties"][1]["in_stock"] is False

        browser.close()


def test_import_session_credentials_missing_raises_error(tmp_path: Path):
    output_path = tmp_path / "session.json"
    with pytest.raises(RuntimeError) as exc_info:
        import_session_credentials("nonexistent-test-domain.xyz", output_path)

    assert "Searched paths:" in str(exc_info.value)
    assert "nonexistent-test-domain.xyz" in str(exc_info.value)


def test_polling_loop(monkeypatch):
    poll_results = []

    def mock_crawl(page, pid, timeout=30000):
        return {"product_id": pid, "status": "success", "varieties": []}

    monkeypatch.setattr("crawler.crawler.crawl_product", mock_crawl)

    def on_poll_callback(results):
        poll_results.append(results)

    results = run_crawler(
        product_ids=["1151020c1"],
        poll=True,
        interval=0.01,
        max_polls=3,
        on_poll=on_poll_callback,
    )

    assert len(poll_results) == 3
    assert len(results) == 1
    assert results[0]["product_id"] == "1151020c1"


def test_cli_polling_arguments(monkeypatch):
    test_args = ["crawler", "--poll", "--interval", "5.5"]
    monkeypatch.setattr("sys.argv", test_args)

    called_kwargs = {}

    def mock_run_crawler(**kwargs):
        called_kwargs.update(kwargs)
        return []

    monkeypatch.setattr("crawler.crawler.run_crawler", mock_run_crawler)
    monkeypatch.setattr("crawler.crawler.load_product_ids", lambda p: ["1151020c1"])
    monkeypatch.setattr("crawler.crawler.import_session_credentials", lambda d, o: o)
    monkeypatch.setattr("pathlib.Path.exists", lambda self: True)

    main()

    assert called_kwargs.get("poll") is True
    assert called_kwargs.get("interval") == 5.5
