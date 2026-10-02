# Voila Voice - MCP, Skills, and Connectors

## 1. Model Context Protocol (MCP) Host
Voila Voice acts as an MCP Host, allowing it to connect to any standard JSON-RPC stdio MCP server.

### Configuration (`mcp_servers.json`)
Servers are configured via `mcp_servers.json` or by using the `mcp_add_server` tool.
*   **Security (Allowlist):** For filesystem-based servers (like `@modelcontextprotocol/server-filesystem`), you **must** configure `allowed_paths`. The host will reject path arguments outside these directories.
*   **Truncation:** Tool outputs are capped at 64KB.

### Available Meta Tools
*   `mcp_list_servers` / `mcp_list_tools`
*   `mcp_add_server` / `mcp_remove_server`
*   `mcp_enable_server` / `mcp_disable_server`
*   `mcp_reload`

**Note on Graphify:** While a Graphify DAG is running, configuration mutation tools (add/remove/enable server, install skills) are blocked to prevent nodes from fighting over global state. The MCP host is a process-global singleton.

---

## 2. Connectors
Connectors provide a fast, seamless way to add powerful MCP servers without manual JSON configuration. 
Tools: `connectors_list`, `connectors_connect`, `connectors_status`, `connectors_disconnect`

Available Free Open-Source Connectors:
1.  **filesystem_project**: Local filesystem access (Requires `npx`). Must specify `allowed_paths`.
2.  **github**: GitHub integration via `@modelcontextprotocol/server-github` (Requires `npx` and a GitHub PAT).
3.  **gmail**: Local-first Gmail integration via `@mcp-z/mcp-gmail` (Requires `npx` and Google Cloud OAuth).
4.  **youtube**: YouTube transcript retrieval via `@umbertotancorre/youtube-mcp` (Requires `npx`).
5.  **canvas_lms**: Canvas LMS integration via `@r-huijts/canvas-mcp` (Requires `npx` and Canvas Token).

**Security:** Connectors securely map tokens to the required environment variables (e.g., `GITHUB_PERSONAL_ACCESS_TOKEN`). Tokens are never written to the debug logs or audit logs.

---

## 3. Skills Marketplace
The marketplace allows the agent to search GitHub for pre-vetted agent workflows (`SKILL.md` files) and install them locally.

Tools: `skills_market_search`, `skills_market_info`, `skills_market_install`, `skills_market_uninstall`, `skills_market_list_installed`

*   **Quarantine:** Skills are installed to `skills/installed/<id>/SKILL.md`. Path traversal is strictly blocked.
*   **Safety:** `skills_market_install` only downloads the markdown file. It never executes arbitrary `install.sh` scripts.
*   **Validation:** A downloaded skill must contain a valid `# ` markdown header to be accepted.

---

## 4. Agent Guidance
*   **Browser / Desktop OS interaction:** The native `browser_automation`, `desktop_automation`, and `run_terminal` tools are deeply integrated and remain the preferred method for OS control. Do not try to rebuild them with MCP.
*   **External APIs / Third-Party Platforms:** Use Connectors or MCP servers to talk directly to external APIs like GitHub, Gmail, or Slack.
*   **Policy Hook:** Destructive commands (e.g., tools with `delete`, `drop`, `remove` in their name) executed via MCP will trigger the existing `requireSecurityApproval` UI hook for user confirmation.
*   **Audit Logging:** All MCP tool calls, skill installations, and connector auth events are logged to `security_audit.jsonl`.
