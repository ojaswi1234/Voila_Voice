# Voila Document Templates Setup

Voila uses a template-first design system for documents. This means the AI will not try to design your documents from scratch. Instead, it uses your existing Google Slides or Google Docs templates.

## Quick Start
1. Create a Google Slide or Google Doc.
2. Design it however you want (add your corporate branding, headers, background colors).
3. Where you want the AI to inject data, type double-brace placeholders, e.g., `{{TITLE}}`, `{{KPI_1_VALUE}}`, `{{BULLET_1}}`.
4. Grab the Document ID from the URL (e.g., `https://docs.google.com/presentation/d/THIS_IS_THE_ID/edit`).
5. Open `local-agent/templates/registry.json` and paste your ID into the `file_id` field for the corresponding template.
6. Make sure you share the document with your Google Cloud Service Account, or configure your local `google_workspace_mcp` with your user credentials.

## Supported MCPs
- **Google Official Workspace MCP** (Recommended)
- **taylorwilsdon/google_workspace_mcp** (Fallback)
- **dguido/google-workspace-mcp** (Fallback)

Set `VOILA_DOCS_MOCK=1` in your environment to test locally without an MCP.
