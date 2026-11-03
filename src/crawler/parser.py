"""HTML parsing logic for extracting variety names and stock statuses."""

from typing import Any, Dict, List
from bs4 import BeautifulSoup, Tag


def parse_variety_row(row: Tag) -> Dict[str, Any]:
    """Parse an individual .product-form-row element.

    - Under `.product-form-info-block > .product-attributes`, extract the `dd` element
      content as the name for the variety.
    - Check `.product-form-input-block > .single_add_to_cart_button` to determine stock status.
      If disabled, out of stock (False). Otherwise, in stock (True).
    """
    # 1. Variety name
    name = ""
    info_block = row.select_one(".product-form-info-block .product-attributes")
    if info_block:
        dd_elements = info_block.find_all("dd")
        if dd_elements:
            name_parts = [dd.get_text(strip=True) for dd in dd_elements if dd.get_text(strip=True)]
            name = " / ".join(name_parts)

    # Fallback if no .product-attributes dd found directly
    if not name:
        dd = row.select_one("dd")
        if dd:
            name = dd.get_text(strip=True)

    # 2. Stock status
    btn = row.select_one(".product-form-input-block .single_add_to_cart_button")
    if btn is None:
        btn = row.select_one(".single_add_to_cart_button")

    in_stock = False
    if btn:
        classes = btn.get("class", [])
        if isinstance(classes, str):
            classes = classes.split()

        has_disabled_attr = btn.has_attr("disabled")
        has_disabled_class = "disabled" in classes
        aria_disabled = btn.get("aria-disabled", "").lower() == "true"

        is_disabled = has_disabled_attr or has_disabled_class or aria_disabled
        in_stock = not is_disabled

    return {
        "variety": name,
        "in_stock": in_stock,
    }


def parse_product_title(html_content: str) -> str:
    """Return the text content of the `.product_title` element, or empty string."""
    soup = BeautifulSoup(html_content, "html.parser")
    el = soup.select_one(".product_title")
    return el.get_text(strip=True) if el else ""


def parse_product_page_html(html_content: str) -> List[Dict[str, Any]]:
    """Parse product page HTML and return list of varieties and their stock status.

    Looks up:
    - `.product-form-rows`: container of all varieties
    - `.product-form-row`: individual variety entries
    """
    soup = BeautifulSoup(html_content, "html.parser")
    rows = soup.select(".product-form-rows .product-form-row")
    if not rows:
        # Fallback if .product-form-rows container is absent but individual rows exist
        rows = soup.select(".product-form-row")

    varieties: List[Dict[str, Any]] = []
    for row in rows:
        varieties.append(parse_variety_row(row))

    return varieties
