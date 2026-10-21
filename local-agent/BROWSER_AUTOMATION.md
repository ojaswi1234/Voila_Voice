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

3. **Loop Detection Signature**:
   `extract_interactive` generates a 16-character MD5 `signature` based on the page URL and interactive tree summary. Agents compare signatures across turns to immediately detect dead-end cycles.

4. **Observe Contract**:
   `goto` returns `"extract_hint": true`, ensuring agents observe the page state via `extract_interactive` before dispatching clicks or typing into unconfirmed DOM locations.

5. **CDP Resilience**:
   Detects whether Edge CDP (`port 9222`) is online with clear structured error `cdp_unavailable` and recovery instructions if the browser debugging daemon is unreachable.

6. **Bridge Coordination & Bounded Circuit Breaker**:
   - `bridge_constructor.py` acts as an orchestrator when DOM interactions are obstructed by OS-level native dialogs or canvas overlays.
   - **Circuit Breaker**: Capped at a strict maximum of **2 desktop assists** per session task (`MAX_DESKTOP_ASSISTS = 2`). If exceeded, `circuit_breaker_tripped` is raised to prevent runaway physical mouse hijacking.
   - Every desktop assist verifies that the DOM state actually changed before releasing control back to the browser agent.
