"""Tests for parsing Marukyu Koyamaen product pages."""

import pytest
from bs4 import BeautifulSoup
from crawler.parser import parse_product_page_html, parse_variety_row


SAMPLE_PRODUCT_HTML = """
<!DOCTYPE html>
<html>
<body>
<div class="product-form-rows">
    <div class="product-form-row">
        <div class="product-form-info-block">
            <div class="product-attributes">
                <dl>
                    <dt>Package / Size</dt>
                    <dd>Can 40g</dd>
                </dl>
            </div>
        </div>
        <div class="product-form-input-block">
            <button type="submit" name="add-to-cart" value="101" class="single_add_to_cart_button button alt">
                Add to cart
            </button>
        </div>
    </div>
    <div class="product-form-row">
        <div class="product-form-info-block">
            <div class="product-attributes">
                <dl>
                    <dt>Package / Size</dt>
                    <dd>Can 100g</dd>
                </dl>
            </div>
        </div>
        <div class="product-form-input-block">
            <button type="button" class="single_add_to_cart_button button alt disabled" disabled="disabled">
                Out of stock
            </button>
        </div>
    </div>
    <div class="product-form-row">
        <div class="product-form-info-block">
            <div class="product-attributes">
                <dl>
                    <dt>Package / Size</dt>
                    <dd>Bag 100g</dd>
                </dl>
            </div>
        </div>
        <div class="product-form-input-block">
            <button type="submit" class="single_add_to_cart_button button alt">
                Add to cart
            </button>
        </div>
    </div>
    <div class="product-form-row">
        <div class="product-form-info-block">
            <div class="product-attributes">
                <dl>
                    <dt>Package</dt>
                    <dd>Bag 200g</dd>
                </dl>
            </div>
        </div>
        <div class="product-form-input-block">
            <button type="button" class="single_add_to_cart_button button alt" aria-disabled="true">
                Sold Out
            </button>
        </div>
    </div>
</div>
</body>
</html>
"""


def test_parse_product_page_html_varieties_and_stock():
    varieties = parse_product_page_html(SAMPLE_PRODUCT_HTML)
    assert len(varieties) == 4

    assert varieties[0] == {"variety": "Can 40g", "in_stock": True}
    assert varieties[1] == {"variety": "Can 100g", "in_stock": False}
    assert varieties[2] == {"variety": "Bag 100g", "in_stock": True}
    assert varieties[3] == {"variety": "Bag 200g", "in_stock": False}


def test_parse_variety_multiple_dd_attributes():
    html = """
    <div class="product-form-row">
        <div class="product-form-info-block">
            <div class="product-attributes">
                <dl>
                    <dt>Type</dt>
                    <dd>Matcha</dd>
                    <dt>Size</dt>
                    <dd>Can 20g</dd>
                </dl>
            </div>
        </div>
        <div class="product-form-input-block">
            <button class="single_add_to_cart_button">Add</button>
        </div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    row = soup.select_one(".product-form-row")
    assert row is not None
    result = parse_variety_row(row)
    assert result["variety"] == "Matcha / Can 20g"
    assert result["in_stock"] is True


def test_parse_empty_page():
    varieties = parse_product_page_html("<html><body><div>No products</div></body></html>")
    assert varieties == []


def test_parse_button_missing():
    html = """
    <div class="product-form-row">
        <div class="product-form-info-block">
            <div class="product-attributes">
                <dd>Special Pack</dd>
            </div>
        </div>
        <div class="product-form-input-block">
        </div>
    </div>
    """
    soup = BeautifulSoup(html, "html.parser")
    row = soup.select_one(".product-form-row")
    assert row is not None
    result = parse_variety_row(row)
    assert result["variety"] == "Special Pack"
    assert result["in_stock"] is False



def test_parse_product_title():
    from crawler.parser import parse_product_title

    assert parse_product_title('<h1 class="product_title"> Matcha Tin </h1>') == 'Matcha Tin'
    assert parse_product_title('<p></p>') == ''

