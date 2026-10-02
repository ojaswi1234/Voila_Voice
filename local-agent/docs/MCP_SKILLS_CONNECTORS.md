# Voila Voice - MCP, Skills & Connectors

This guide explains how to use the new extensible tool layers in Voila Voice.

## 1. Model Context Protocol (MCP)

The MCP layer allows Voila to interact with external systems using standard JSON-RPC servers. 

### Adding an MCP Server
You can register an MCP server in `mcp_servers.json` or by using the agent's `mcp_add_server` tool.
The format of the JSON is:
`+` `"id"`: Unique server name (e.g. `github`, `fs`).
`+` `"command"`: The binary to run (e.g. `npx`, `python`).
`+` `"args"`: Array of arguments (e.g. `["-y", "@modelcontextprotocol/server-github"]`).
`+` `"enabled"`: Boolean.

When a server is enabled, its tools are exposed to the LLM with the namespace `mcp__<id>__<toolname>`.

### Listing Tools
Use the `mcp_list_tools` tool to list all dynamically loaded MCP tools, or ask the agent what tools are available.

## 2. Connectors

Connectors are pre-configured services (like Gmail, GitHub, Canvas) in `connectors/catalog.json`.

### How to use:
1. Call `connectors_list` to see available connectors.
2. Call `connectors_connect(id, token)` to securely authenticate. The token will be securely passed via env vars and never logged.
3. The connector will automatically enable its corresponding MCP server.

## 3. Skills Marketplace

Skills are natural language agent instructions (`SKILL.md`) that guide the agent.

1. **Search**: Use `skills_market_search(query)` to find skills from GitHub repositories.
2. **Install**: Use `skills_market_install(id, source)` to download a skill. It saves into `skills/installed/<id>/SKILL.md`.
3. **List**: Use `skills_market_list_installed()` to see what's loaded.

## 4. Agent Guidance: OS Tools vs MCP vs Connectors

- **OS Tools**: Use for native filesystem, terminal execution, and local Python scripts (fastest, most permissive).
- **MCP**: Use for structured APIs where safety, tool schema enforcement, or community-built adapters (e.g. SQL, complex IDE extensions) are needed.
- **Connectors**: Use exclusively for third-party cloud integrations (Gmail, GitHub) to manage authentication securely.
