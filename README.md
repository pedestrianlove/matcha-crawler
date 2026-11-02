# Marukyu Koyamaen Variety Stock Crawler

Autonomous crawler for checking the stock status of product varieties on [Marukyu Koyamaen](https://www.marukyu-koyamaen.co.jp/english/shop/).

## Overview

The crawler loads an array of product IDs from `products.json`, opens each product URL (`https://www.marukyu-koyamaen.co.jp/english/shop/products/{{ product_id }}`), locates variety data under `.product-form-rows` / `.product-form-row`, extracts variety names from `.product-form-info-block > .product-attributes dd`, and checks `.single_add_to_cart_button` to determine whether each variety is in stock (`true`) or out of stock (`false`).

Results are formatted as JSON.

## Requirements

- Python >= 3.12 (managed via `uv`)
- Dependencies pinned in `uv.lock`

## Setup

Install dependencies and Playwright browser:

```bash
uv sync
uv run playwright install chromium
```

## Configuration

Seed product IDs in `products.json`:

```json
[
  "1151020c1"
]
```

### Authentication & Session Reuse

To reuse an existing authenticated browser session:

1. **Storage state file**: Export Playwright session cookies/storage to `session.json` (or pass `--storage-state path/to/state.json`).
2. **Persistent user profile**: Point `--user-data-dir` or `CHROME_USER_DATA_DIR` to your existing browser profile directory.

## Usage

Run via CLI command:

```bash
uv run crawler
```

Or via python script:

```bash
uv run python main.py
```

### CLI Options

- `-p, --products <path>`: Path to `products.json` (default: `products.json`).
- `-o, --output <path>`: Save results to output file (default: stdout).
- `--user-data-dir <dir>`: Path to browser profile directory for authentication persistence.
- `--storage-state <path>`: Path to saved storage state / cookies JSON file.
- `--headed`: Run browser in visible headed mode.
- `--timeout <ms>`: Timeout per page in milliseconds (default: `30000`).
- `-v, --verbose`: Enable debug logging.

## Running Tests

Run all unit and integration tests:

```bash
uv run pytest
```
