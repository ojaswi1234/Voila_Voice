# Browser Automation Tool — Voila Local Agent

Drives Chromium / Microsoft Edge via Chrome DevTools Protocol (CDP) and Playwright.  
Focuses on semantic locators, actionability auto-waits, frame-aware element extraction, smart multi-control form filling, spreadsheet data entry, table extraction, and dedicated **Payment Guardrails (Deny by Default)**.

---

## Quick Start

```bash
# Check CDP health
python browser_tools.py --action health

# Navigate to URL (returns extract_hint=true)
python browser_tools.py --action goto --url "https://example.com"

# Extract interactive elements with suggested locators, frame tags & DOM signature hash
python browser_tools.py --action extract_interactive

# Click using accessible locator
python browser_tools.py --action click --selector 'role=button[name="Submit"]'

# Smart multi-control form filling (skips/blocks payment fields)
python browser_tools.py --action fill_form --value '{"First Name": "Jane", "Email": "jane@example.com", "Country": "Canada", "Subscribe": true}'

# Select native dropdown option by label, value, or index
python browser_tools.py --action select_option --selector "select#country" --label "Canada"

# Read-only structured scrape (title, meta description, main text, tables, price displays)
python browser_tools.py --action scrape_structured

# Multi-tab research helper (opens tab, extracts structured data, auto-closes tab)
python browser_tools.py --action research_extract --url "https://en.wikipedia.org/wiki/Robotics" --close true

# Wait for and intercept file download
python browser_tools.py --action wait_download --selector 'button#export-report'

# Bulk tabular data entry into Google Sheets / Excel Online / Airtable / Datagrids
python browser_tools.py --action enter_table_data --value '[["Product", "Price", "Qty"], ["Widget A", "19.99", "5"], ["Widget B", "29.99", "2"]]'

# Extract table data into JSON records and Markdown table
python browser_tools.py --action extract_table --selector "table.data-table"

# Select or jump to a spreadsheet cell (e.g. "B5" in Google Sheets via Name Box)
python browser_tools.py --action select_cell --value "B5"

# Upload file via filechooser / set_input_files
python browser_tools.py --action upload --selector 'input[type=file]' --value 'C:\path\to\doc.pdf'
```

---

## Action Capability Matrix

| Action | Description | Primary Parameters | Key Guarantees & Safeguards |
| :--- | :--- | :--- | :--- |
| `health` | Checks CDP connectivity on port 9222 | None | Fast probe (0.5s timeout) |
| `ensure` | Confirms browser window readiness | None | Ensures active page |
| `goto` | Navigates current tab to URL | `--url`, `--wait_time`, `--wait-networkidle` | Payment URL deny gate; search engine URL block; returns `extract_hint=true` |
| `new_tab` | Opens new tab and navigates | `--url` | Payment URL deny gate; auto-switches active tab index |
| `list_tabs` | Lists all open tabs across contexts | None | Reports tab index, active tab, URL, title |
| `switch_tab` | Switches active focus to tab | `--value` (index or title/URL fragment) | Brings target page to front |
| `close_tab` | Closes active or target tab | `--value` (optional tab index) | Safe close; adjusts active index |
| `wait_for` | Waits for selector, text, state, or timeout | `--selector`, `--text`, `--state`, `--wait_time` | Supports `load`, `domcontentloaded`, `networkidle` |
| `click` | Clicks element with 3-tier fallback | `--selector` | Payment CTA / field deny; reports `click_path` (`normal`, `force`, `js`) |
| `type` | Types into input with auto-clear | `--selector`, `--value` | Blocks PAN card numbers & payment fields; label-to-input mapping |
| `press` | Presses keyboard key | `--value` (key name), `--selector` (optional) | Blocks Enter on payment controls |
| `scroll` | Scrolls window or element | `--value` (`up`, `down`, pixels) | Smooth scrolling |
| `hover` | Hovers mouse pointer over element | `--selector` | Triggers hover flyouts/menus |
| `search_word` | Finds word on page & scrolls into view | `--value` | Pierces iframes; reports occurrence count |
| `extract_interactive` | Scans page for clickable/input elements | None | Frame-aware (up to 10 frames); shadow DOM piercing; ranked by reliability |
| `scrape` | Scrapes text or element texts | `--selector` (optional) | Fast text capture |
| `scrape_structured` | Extracts rich document metadata | None | Read-only title, meta description, main text, tables, price displays |
| `select_option` | Selects dropdown option | `--selector`, `--value`/`--label`/`--index` | Native `<select>` manipulation |
| `fill_form` | Smart form filling across multiple widgets | `--value` (JSON field dictionary) | Skips/blocks payment fields; supports native, ARIA, and rich text editors |
| `submit_form` | Submits form or clicks primary submit | `--selector` (optional) | Identifies submit button or falls back to Enter |
| `wait_download` | Intercepts browser file download | `--selector` or `--url`, `--timeout_ms` | Saves to `%LOCALAPPDATA%\Voila\downloads`; reports path & size |
| `research_extract` | Background research across tabs | `--url`, `--close` (default true) | Payment gate on URL; opens tab, scrapes structured data, auto-closes |
| `enter_table_data` | Bulk/sequential spreadsheet data entry | `--value` (2D array, dict list, TSV), `--mode` | High-throughput TSV clipboard paste (`Ctrl+V`) for Google Sheets/Excel |
| `extract_table` | Extracts table/grid to JSON & Markdown | `--selector` (optional) | Structured extraction from `<table>`, `[role=table]`, `[role=grid]` |
| `select_cell` | Jumps to spreadsheet cell coordinate | `--value` (e.g. `"B5"`) | Uses Name Box on Google Sheets/Excel Online |
| `upload` | Uploads file to `<input type=file>` | `--selector`, `--value` (local path) | Gated on payment pages; falls back to `needs_desktop_assist` for OS dialogs |
| `eval` | Executes JavaScript expression in page | `--value` (script) | Gated by `VOILA_ALLOW_BROWSER_EVAL`; blocks script writing to payment fields |

---

## Payment Guardrails Policy (P0 — Deny by Default)

Voila enforces a strict **Deny by Default** security policy on all commercial transactions and payment operations.

### 1. Hard Restrictions
- **No Checkout Completion**: The agent will NOT click final purchase buttons or complete checkouts.
- **No Card / Bank Entry**: The agent will NOT enter Primary Account Numbers (PAN), CVVs, expiry dates, IBANs, or bank routing numbers.
- **No Silent Purchases**: The agent refuses all auto-buy, subscription renewals, or payment confirmation tasks.
- **Pay Manually Requirement**: All payment steps must be performed directly and manually by the user in their browser.

### 2. Guardrail Heuristics
- **Payment & Checkout URLs**:
  `checkout`, `/cart/checkout`, `/payment`, `/billing`, `/pay/`, `placeorder`,
  `stripe.com`, `paypal.com`, `razorpay`, `paytm`, `squareup`, `adyen`, `braintree`,
  `checkout.shopify`, `payments.amazon`, `buy.google`, `apple.com/shop/buy`.
- **Payment CTAs & Buttons**:
  `"pay now"`, `"place order"`, `"complete purchase"`, `"confirm payment"`,
  `"buy now"`, `"pay with"`, `"submit payment"`, `"authorize payment"`,
  `"add card and pay"`, `"confirm order and pay"`.
- **Payment Fields**:
  `card number`, `cardnumber`, `cc-number`, `pan`,
  `cvv`, `cvc`, `cid`, `security code`,
  `expiry`, `exp-date`, `cc-exp`,
  `iban`, `routing number`, `account number`,
  `otp` (when present on payment or checkout URLs).

### 3. Masking Protection
Any 13-19 digit PAN-like number appearing in tool logs or returns is automatically masked before output:
```text
4111222233334444  ->  ************4444
```

### 4. Desktop Bridge Prohibition
The cross-platform desktop automation bridge **MUST NOT** be used to bypass a `payment_blocked` error. When an action is rejected under `payment_blocked`, `needs_desktop_assist` is strictly suppressed.

---

## Frame-Aware Extraction & Ranking (`extract_interactive`)

1. **Multi-Frame Scanning**:
   - Automatically traverses `page.main_frame` and up to 10 child iframes.
   - Pierces Shadow DOM trees recursively using `TreeWalker`.
2. **Rich Element Metadata**:
   Each extracted element includes:
   - `frame_name` (`"main"` or iframe name) & `frame_url`
   - `role`, `name`, `tag`, `testid`, `placeholder`
   - `suggested_locator`: semantic locator recommendation
   - `disabled`: boolean flag
   - `area`: bounding box area in pixels (`width * height`)
   - `rank_tier`: priority tier (1 to 4)
3. **Deterministic Ranking**:
   Elements are sorted by:
   - **Tier 1**: Explicit `testid` (most resilient)
   - **Tier 2**: Accessible `role` and non-empty `name`
   - **Tier 3**: Visible and enabled controls
   - **Secondary Sort**: Bounding box `area` ascending (prioritizes specific, clickable buttons and inputs over giant wrapping layout containers).

---

## Structured Scrape (`scrape_structured`)

Designed for token-efficient web research without loading excessive HTML:
- `title`: Page document title.
- `url`: Current page URL.
- `meta_description`: Extracted from `<meta name="description">` or `<meta property="og:description">`.
- `main_text`: Bounded excerpt (up to 2000 characters) extracted from `<article>`, `<main>`, or `.content`.
- `tables`: Up to 3 tables parsed into list of row dictionaries (`[{"Feature": "Battery", "Value": "24h"}]`).
- `price_display`: Read-only list of currency and price strings found on page (e.g. `["$49.99", "USD 50"]`).
- **Safety Guarantee**: Explicitly marked `READ ONLY — display text only, not checkout. Never auto-click buy.`

---

## File Downloads (`wait_download`)

- Automatically expects and intercepts browser downloads triggered via button clicks or direct download URLs.
- Saves downloaded files to the dedicated agent downloads folder:
  - Windows: `%LOCALAPPDATA%\Voila\downloads`
  - Fallback: `~/.voila/downloads`
- Returns structured file details: `path`, `size`, `suggested_filename`.
- Blocked if the download trigger or URL matches a payment completion flow.

---

## Semantic Locator Priority

`getByRole` (`role=button[name="..."]`) → `getByLabel` (`label="..."`) → `getByPlaceholder` (`placeholder="..."`) → `getByText` (`text="..."`) → `getByTestId` (`testid="..."`) → CSS selectors.

Brittle absolute XPaths and dynamic CSS classes are avoided.

---

## Environment Variables & Configuration

| Variable | Default | Purpose |
| :--- | :--- | :--- |
| `VOILA_BROWSER_SETTLE_MS` | `150` | Settle delay in milliseconds before snapshot/extract (replaces blind 1000ms sleeps). |
| `VOILA_ALLOW_BROWSER_EVAL` | `1` | Set to `0` to globally disable JavaScript execution via the `eval` action. |
| `VOILA_REQUIRE_OBSERVE` | `0` | When set to `1`, warns if mutating actions (`click`, `type`) occur without prior `extract_interactive`. |
| `VOILA_JOB_ID` / `CONVERSATION_ID` | `default` | Isolates desktop assist circuit breakers across concurrent agent sessions. |
| `VOILA_EDGE_PATH` | (auto-detected) | Custom path to Microsoft Edge or Chromium binary. |
| `VOILA_BROWSER_PROFILE` | `C:\tmp\ai_browser_profile` | Edge user data directory for session persistence. |
