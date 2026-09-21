import re
from pathlib import Path

path = Path(r"C:\Users\ojasw\Desktop\Voila_Voice\local-agent\main.go")
content = path.read_text(encoding="utf-8")

# B2: Replace CRITICAL SYSTEM NOTE
new_note = (
    "CRITICAL SYSTEM NOTE: You are running inside an isolated background sandbox (` + \"`exebox`\" + ` desktop). "
    "To open ANY GUI application, URL, or file so it is visible to the user on their main desktop, you MUST use WMI to break out of the sandbox. "
    "Use exactly this command format: ` + \"`Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList 'explorer.exe \\\"<URL_OR_PATH>\\\"'`\" + ` (for URLs/files) or "
    "` + \"`Invoke-WmiMethod -Class Win32_Process -Name Create -ArgumentList '<APP_EXE>'`\" + ` (for apps). "
    "DO NOT use Start-Process, as it will spawn invisibly in the sandbox! "
    "To perform browser automation, you MUST use the browser_automation tool — do NOT launch Edge via WMI/shell with about:blank, and do NOT call browser_tools.py via a hardcoded path. "
    "Workflow: (1) Choose browser_automation action=goto (navigate current tab) OR action=new_tab (open new tab) based on whether the current tab must be preserved. Use new_tab when user says 'in another tab', 'keep this page', 'compare A and B', or for independent URLs. (2) Use list_tabs/switch_tab when working across tabs. (3) snapshot/extract_links/click/type/press on the active tab. (4) close_tab when done with an extra tab if useful. Never use about:blank. Every tool result includes ok/url/title — if ok is false, explain the error to the user. Never stop after only opening a blank browser."
)

pattern = r"CRITICAL SYSTEM NOTE: You are running inside an isolated background sandbox.*?(?=\n\n|\n`|\n\r?\n|$)"
content = re.sub(pattern, new_note, content, flags=re.DOTALL)

# B3: pushTokenUsage wss->https, ws->http
push_token_search = "backendURL := strings.TrimSuffix\\(connData.BackendURL, \"/\"\\)\\s+targetURL := backendURL \\+ \"/webhook/token-usage\""
push_token_replace = (
    "backendURL := strings.TrimSuffix(connData.BackendURL, \"/\")\n\t"
    "backendURL = strings.Replace(backendURL, \"wss://\", \"https://\", 1)\n\t"
    "backendURL = strings.Replace(backendURL, \"ws://\", \"http://\", 1)\n\t"
    "targetURL := backendURL + \"/webhook/token-usage\""
)
content = re.sub(push_token_search, push_token_replace, content)

push_token_ngrok_search = r"req\.Header\.Set\(\"Content-Type\", \"application/json\"\)"
push_token_ngrok_replace = (
    "req.Header.Set(\"Content-Type\", \"application/json\")\n\t"
    "if strings.Contains(targetURL, \"ngrok\") {\n\t\t"
    "req.Header.Set(\"ngrok-skip-browser-warning\", \"true\")\n\t"
    "}"
)
content = re.sub(push_token_ngrok_search, push_token_ngrok_replace, content, count=1)

# B4: postWebhookResult wss->https, ws->http
post_web_search = r"backendURL = strings\.Replace\(backendURL, \"ws://\", \"http://\", 1\)"
post_web_replace = (
    "backendURL = strings.Replace(backendURL, \"wss://\", \"https://\", 1)\n\t"
    "backendURL = strings.Replace(backendURL, \"ws://\", \"http://\", 1)"
)
content = re.sub(post_web_search, post_web_replace, content)

# B5: startScheduleTicker playbook firing
schedule_search = r"if s\.PlaybookID != \"\" \{\s+prompt = \"run_playbook: \" \+ s\.PlaybookID\s+\}"
schedule_replace = ""
content = re.sub(schedule_search, schedule_replace, content)

execute_search = r"result, _, _ := executeCommand\(context\.Background\(\), p, \"LOCAL\", convID, \"flash\"\)\s+postWebhookResult\(connData, \"schedule\", convID, result, \"\", nil\)"
execute_replace = (
    "jobID := convID\n\t\t\t\t\t\tvar result string\n\t\t\t\t\t\tvar cmdErr error\n\t\t\t\t\t\t"
    "if s.PlaybookID != \"\" {\n\t\t\t\t\t\t\t"
    "argsJSON := []byte(fmt.Sprintf(`{\"id\": \"%s\"}`, s.PlaybookID))\n\t\t\t\t\t\t\t"
    "result = executeToolInner(context.Background(), \"run_playbook\", argsJSON, nil)\n\t\t\t\t\t\t"
    "} else if p != \"\" {\n\t\t\t\t\t\t\t"
    "result, _, cmdErr = executeCommand(context.Background(), p, \"LOCAL\", convID, \"flash\")\n\t\t\t\t\t\t"
    "}\n\t\t\t\t\t\t"
    "postWebhookResult(connData, \"schedule\", convID, result, jobID, cmdErr)"
)
content = re.sub(execute_search, execute_replace, content)

path.write_text(content, encoding="utf-8")
print("Done patching.")
