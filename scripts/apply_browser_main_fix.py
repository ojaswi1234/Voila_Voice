#!/usr/bin/env python3
"""One-shot patch for local-agent/main.go browser prompts and executeTool."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
path = ROOT / "local-agent" / "main.go"
text = path.read_text(encoding="utf-8")

old1 = (
    "To perform browser automation, you MUST first launch a visible browser using "
    "Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList "
    "'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe "
    "--remote-debugging-port=9222 --user-data-dir=C:\\tmp\\ai_browser_profile \"about:blank\"'. "
    "Then, control it by running python C:\\Users\\ojasw\\Desktop\\voice-cli-system\\local-agent\\browser_tools.py "
    "with args --action [goto|click|type|scrape|extract_links|snapshot] --url <url> --selector <css> --value <text>."
)
old2 = (
    "To perform browser automation, you MUST first launch a visible browser using "
    "Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList "
    "'C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe "
    "--remote-debugging-port=9222 --user-data-dir=C:\\tmp\\ai_browser_profile \"about:blank\"'. "
    "Then, control it by running python C:\\Users\\ojasw\\Desktop\\voice-cli-system\\local-agent\\browser_tools.py "
    "with args --action [goto|click|type|scrape|extract_links|snapshot] --url <url> --selector <css> --value <text>."
)
# Also match single-backslash variants in source
old_variants = []
for o in (old1, old2):
    old_variants.append(o)
    old_variants.append(o.replace("\\\\", "\\"))

new = (
    "To perform browser automation, you MUST use the browser_automation tool — "
    "do NOT launch Edge via WMI/shell with about:blank, and do NOT call browser_tools.py via a hardcoded path. "
    "Workflow: (1) browser_automation action=goto url=https://full-target-url (never about:blank); "
    "the tool attaches to Edge CDP :9222 or starts one visible Edge itself. "
    "(2) Use snapshot or extract_links if you need selectors. "
    "(3) action=click/type/press as needed. "
    "(4) Continue tool calls until the user task is finished OR return a clear error string. "
    "Every tool result includes ok/url/title — if ok is false, explain the error to the user. "
    "Never stop after only opening a blank browser."
)

count = 0
for o in old_variants:
    if o in text:
        text = text.replace(o, new)
        count += 1

old_desc = "Control a visible, headful browser. Use this to interact with a page. For simple information lookup, prefer web_research to save tokens. They can be used together."
new_desc = (
    "Control a visible Edge browser via CDP. ALWAYS start with action=goto and the full https URL "
    "(never about:blank). Then click/type using CSS selectors; call snapshot if unsure. "
    "Chain multiple browser_automation calls until the task is done. "
    "Returns JSON with ok, url, title, error. For simple lookups prefer web_research."
)
if old_desc in text:
    text = text.replace(old_desc, new_desc)
    count += 1

text2 = text.replace("follow up with automate_0", "follow up with browser_automation")
if text2 != text:
    count += 1
    text = text2

# executeTool hardening: if still using simple path-only resolution, leave note
if "browser_tools.py not found" not in text:
    print("NOTE: executeTool path hardening may need manual apply from PR description")

path.write_text(text, encoding="utf-8")
print(f"patched {path} replacements~={count}")
print("remaining about:blank profile launch:", 'ai_browser_profile "about:blank"' in text)
"""
Run from repo root: python scripts/apply_browser_main_fix.py
Then rebuild local agent.
"""
