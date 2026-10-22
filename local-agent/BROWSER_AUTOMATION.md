# Browser Automation Tool — Voila Local Agent

Drives Chromium / Microsoft Edge via Chrome DevTools Protocol (CDP) and Playwright.  
Focuses on semantic locators, actionability auto-waits, smart multi-control form filling, spreadsheet data entry, table extraction, and bounded desktop bridge fallback.

---

## Quick Start

```bash
# Check CDP health
python browser_tools.py --action health

# Navigate to URL (returns extract_hint=true)
python browser_tools.py --action goto --url "https://example.com"

# Extract interactive elements with suggested locators & DOM signature hash
python browser_tools.py --action extract_interactive

# Click using accessible locator
python browser_tools.py --action click --selector 'role=button[name="Submit"]'

# Smart multi-control form filling
python browser_tools.py --action fill_form --value '{"First Name": "Jane", "Email": "jane@example.com", "Country": "Canada", "Subscribe": true}'

# Bulk tabular data entry into Google Sheets / Excel Online / Airtable / Datagrids
python browser_tools.py --action enter_table_data --value '[["Product", "Price", "Qty"], ["Widget A", "19.99", "5"], ["Widget B", "29.99", "2"]]'

# Extract table data into JSON and Markdown
python browser_tools.py --action extract_table --selector "table.data-table"

# Select or jump to a spreadsheet cell (e.g. "B5" in Google Sheets via Name Box)
python browser_tools.py --action select_cell --value "B5"

# Upload file via filechooser / set_input_files
python browser_tools.py --action upload --selector 'input[type=file]' --value 'C:\path\to\doc.pdf'
```

---

## Architectural Principles & Advanced Capabilities

### 1. Smart Form Filling Engine (`fill_form` & `type`)
- **Intelligent Label & Input Mapping (`_resolve_form_field`)**:
  - Resolves standard `<label for="id">` attributes to their associated `<input>` or `<textarea>`.
  - Resolves `<label>` tags wrapping inputs `<label>Name <input/></label>` to their inner interactive elements.
  - Resolves labels immediately preceding form elements in the DOM.
- **Multi-Control Support**:
  - **Native `<select>`**: Matches by option text label, value, or index.
  - **Checkboxes & Custom ARIA Switches**: Handles `<input type="checkbox">` as well as custom `[role="checkbox"]` and `[role="switch"]` widgets based on `aria-checked`.
  - **Custom Dropdowns & Comboboxes**: Interacts with Radix UI, MUI, React-Select, and Ant Design `[role="combobox"]` by clicking the trigger, opening the option list, and selecting the matching option.
  - **ContentEditable & Rich Text Editors**: Targets Notion, Google Docs, Slack, and Jira rich text fields using `document.execCommand('insertText')` with full focus retention.
  - **Date, Time, & Range Controls**: Injects values and dispatches synthetic `input` and `change` events.
  - **Verification Post-fill**: Clears inputs before typing, asserts `input_value()`, and returns detailed per-field results `{field: {method: "...", value: "...", verified: true}}`.
  - **Auto-Submission**: Supports `"submit": true` or `"submit_selector": "..."` to automatically find and submit the form.

---

### 2. Spreadsheet & Grid Data Entry (`enter_table_data`)
- **Universal Spreadsheet Support**: Designed for Google Sheets, Microsoft Excel Online, Airtable, Notion Tables, Handsontable, and AG Grid.
- **Flexible Data Ingestion**: Accepts 2D arrays (`[["A", "B"], ["C", "D"]]`), lists of dictionaries (`[{"Col1": "Val1", "Col2": "Val2"}]`), or raw TSV/CSV text strings.
- **Dual Entry Modes**:
  - **`clipboard` (Bulk TSV Paste — Default for Spreadsheets)**: Formats data into a Tab-Separated Values matrix and dispatches a synthetic `Ctrl+V` paste into the selected cell. This mimics native human paste behavior, instantly populating dozens or hundreds of rows without keystroke lag.
  - **`keyboard` (Sequential Tab/Enter Navigation)**: Focuses the starting cell, types values, presses `Tab` between columns, and presses `Enter` between rows.
- **Cell Jumping (`select_cell`)**: On Google Sheets, automatically uses the Name Box (`input#t-name-box`) to jump directly to any cell coordinate (e.g., `"C10"`).

---

### 3. Structured Table Extraction (`extract_table`)
- Automatically parses HTML `<table>`, `[role="table"]`, and `[role="grid"]` elements.
- Extracts headers from `<th>` and `[role="columnheader"]`.
- Extracts rows from `<tbody>` and `[role="row"]`.
- Returns structured JSON records (`data`), a raw 2D array (`matrix`), and a ready-to-display GitHub-flavored Markdown table (`markdown`).

---

### 4. Semantic Locator Priority
`getByRole` (`role=button[name="..."]`) → `getByLabel` (`label="..."`) → `getByPlaceholder` (`placeholder="..."`) → `getByText` (`text="..."`) → `getByTestId` (`testid="..."`) → CSS selectors.

---

### 5. Loop Detection Signature & Noise Filtering
`extract_interactive` generates a 16-character MD5 `signature` based on the sanitized page URL and sorted stable element tuples `(role, name[:40], testid, href_clean)`.
Dynamic noise elements matching timestamps, clocks, counters, spinners, tickers, live counters, or relative times ("seconds ago") are filtered out by regex:
`r"time|clock|counter|spinner|timestamp|ticker|live count|seconds ago|\b\d{1,2}:\d{2}(?::\d{2})?\b"`.

---

### 6. Action Diagnostics & Auto-Wait
- Leans on Playwright actionability auto-waits (visible, stable, enabled, receiving events).
- `click` reports `click_path` (`"normal"`, `"force"`, or `"js"`).
- Deep CSS selectors with multiple `nth-child` or `nth-of-type` clauses trigger `warning="brittle_selector_warning"`.

---

### 7. Bridge Coordination & Per-Job Circuit Breaker
- **Circuit Breaker**: Capped at a strict maximum of **2 desktop assists** per task (`MAX_DESKTOP_ASSISTS = 2`).
- **Job Isolation**: Isolated per `VOILA_JOB_ID` or `CONVERSATION_ID`, with auto-reset when the job ID changes (`bridge_last_job_id.txt`).
