# Browser Automation Tool — Voila Local Agent

Drives Chromium / Microsoft Edge via Chrome DevTools Protocol (CDP) and Playwright.  
Focuses on semantic locators, actionability auto-waits, file uploads, dialog policies, and bounded cross-platform desktop bridge fallback.

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

# Wait for element or state
python browser_tools.py --action wait_for --selector 'text="Welcome"' --wait_time 5000

# Upload file via filechooser / set_input_files
python browser_tools.py --action upload --selector 'input[type=file]' --value 'C:\path\to\doc.pdf'
```

---

## Architectural Principles

1. **Semantic Locator Priority**:
   `getByRole` (`role=button[name="..."]`) → `getByLabel` (`label="..."`) → `getByPlaceholder` (`placeholder="..."`) → `getByText` (`text="..."`) → `getByTestId` (`testid="..."`) → CSS selectors.
   Brittle full XPaths and dynamic class strings are avoided.

2. **Actionability Auto-Wait**:
   Every action (`click`, `type`, `fill_form`) leans on Playwright's auto-wait mechanisms (verifying element is visible, stable, enabled, and receiving pointer events).
   Forced clicks (`force=True`) and direct JavaScript evaluations (`el.click()`) are only attempted as fallbacks when sticky headers or non-standard DOM overlays obscure the target.

3. **Loop Detection Signature & Noise Filtering**:
   `extract_interactive` generates a 16-character MD5 `signature` based on the sanitized page URL (stripping query string and fragment churn) and sorted stable element tuples `(role, name[:40], testid, href_clean)`.
   Dynamic noise elements matching timestamps, clocks, counters, or spinners are filtered out by regex (`r"time|clock|counter|spinner|timestamp|\b\d{1,2}:\d{2}\b"`), preventing false state divergence and loops.

4. **Observe Contract & Settle Configuration**:
   - `goto` returns `"extract_hint": true`, ensuring agents observe the page state via `extract_interactive` before dispatching clicks or typing into unconfirmed DOM locations.
   - Supports `--wait-networkidle` on `goto` for single-page applications requiring full network quiescence.
   - DOM settle delay is governed by `VOILA_BROWSER_SETTLE_MS` (default 150ms, replacing blind 1000ms waits).

5. **Action Diagnostics**:
   - `click` reports `click_path` (`"normal"`, `"force"`, or `"js"`) to give agents full transparency into how the element was activated.
   - Long selectors (>80 characters) or deep CSS with multiple `nth-child` clauses trigger `warning="brittle_selector_warning"`.
   - File upload returns `error="needs_desktop_assist"` when OS-level native file dialogs intercept the automation flow.

6. **CDP Resilience**:
   Detects whether Edge CDP (`port 9222`) is online with clear structured error `cdp_unavailable` and recovery instructions if the browser debugging daemon is unreachable.

7. **Bridge Coordination & Per-Job Circuit Breaker**:
   - `bridge_constructor.py` acts as an orchestrator when DOM interactions are obstructed by OS-level native dialogs or canvas overlays.
   - **Circuit Breaker**: Capped at a strict maximum of **2 desktop assists** per session task (`MAX_DESKTOP_ASSISTS = 2`), keyed by `VOILA_JOB_ID` or `CONVERSATION_ID`. Exposes `reset_assists` action for manual or programmatic quota renewal.
   - Every desktop assist verifies that the DOM state actually changed before releasing control back to the browser agent.
