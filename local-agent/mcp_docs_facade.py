import os
import json
import sys
import datetime
import shutil

ARTIFACTS_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'artifacts', 'documents'))
REGISTRY_PATH = os.path.join(os.path.dirname(__file__), 'templates', 'registry.json')
INDEX_PATH = os.path.join(ARTIFACTS_DIR, 'index.json')

def load_registry():
    if not os.path.exists(REGISTRY_PATH):
        return {}
    with open(REGISTRY_PATH, 'r') as f:
        return json.load(f)

def load_index():
    if not os.path.exists(INDEX_PATH):
        return []
    with open(INDEX_PATH, 'r') as f:
        return json.load(f)

def save_index(index):
    os.makedirs(ARTIFACTS_DIR, exist_ok=True)
    with open(INDEX_PATH, 'w') as f:
        json.dump(index, f, indent=2)

def handle_list():
    reg = load_registry()
    print(json.dumps([{"id": k, **v} for k, v in reg.items()]))

def handle_get(template_id):
    reg = load_registry()
    if template_id not in reg:
        print(json.dumps({"error": f"Template {template_id} not found"}))
        return
    print(json.dumps(reg[template_id]))

def handle_create(payload):
    template_id = payload.get("template_id", "")
    title = payload.get("title", "Untitled")
    fills = payload.get("fills", {})
    exports = payload.get("export", ["pdf"])
    
    reg = load_registry()
    if template_id not in reg:
        print(json.dumps({"error": f'Template "{template_id}" not found in registry'}))
        return
    
    template = reg[template_id]
    provider = template.get("provider", "mock")
    doc_type = template.get("type", "pdf")

    # LOCAL provider: generate real documents using document_tools
    if provider == "local":
        try:
            import document_tools
            import time
            
            os.makedirs(ARTIFACTS_DIR, exist_ok=True)
            timestamp = int(time.time())
            safe_title = "".join(c if c.isalnum() or c in " _-" else "_" for c in title)[:50]
            target_path = os.path.join(ARTIFACTS_DIR, f"{timestamp}_{safe_title}.{doc_type}")
            
            if doc_type == "pdf":
                # Build Markdown content from fills for document_tools Playwright pipeline
                content_lines = [f"# {fills.get('title', title)}", ""]
                meta = []
                if "author" in fills:
                    meta.append(f"**Author:** {fills['author']}")
                if "date" in fills:
                    meta.append(f"**Date:** {fills['date']}")
                if meta:
                    content_lines.append(" | ".join(meta))
                    content_lines.append("")

                if "company" in fills:
                    content_lines.append(f"**Company:** {fills['company']}")
                if "quarter" in fills or "year" in fills:
                    content_lines.append(f"**Period:** {fills.get('quarter', '')} {fills.get('year', '')}")
                if "summary" in fills:
                    content_lines.append(f"\n## Executive Summary\n{fills['summary']}\n")
                if "highlights" in fills:
                    content_lines.append("\n## Key Highlights\n")
                    hl = fills["highlights"]
                    if isinstance(hl, list):
                        for h in hl:
                            content_lines.append(f"- {h}")
                    else:
                        content_lines.append(str(hl))
                if "metrics" in fills:
                    content_lines.append("\n## Performance Metrics\n")
                    metrics = fills["metrics"]
                    if isinstance(metrics, dict):
                        content_lines.append("| Metric | Value |")
                        content_lines.append("|---|---|")
                        for k, v in metrics.items():
                            content_lines.append(f"| {k} | {v} |")
                    else:
                        content_lines.append(str(metrics))

                if "meeting_title" in fills:
                    content_lines.append(f"## Meeting: {fills['meeting_title']}")
                if "attendees" in fills:
                    content_lines.append("\n### Attendees\n")
                    att = fills["attendees"]
                    if isinstance(att, list):
                        for a in att:
                            content_lines.append(f"- {a}")
                    else:
                        content_lines.append(str(att))
                if "agenda" in fills:
                    content_lines.append("\n### Agenda\n")
                    ag = fills["agenda"]
                    if isinstance(ag, list):
                        for item in ag:
                            content_lines.append(f"- {item}")
                    else:
                        content_lines.append(str(ag))
                if "action_items" in fills:
                    content_lines.append("\n### Action Items\n")
                    ai = fills["action_items"]
                    if isinstance(ai, list) and ai and isinstance(ai[0], dict):
                        content_lines.append("| Owner | Task | Due |")
                        content_lines.append("|---|---|---|")
                        for item in ai:
                            content_lines.append(f"| {item.get('owner', '')} | {item.get('task', '')} | {item.get('due', '')} |")
                    elif isinstance(ai, list):
                        for item in ai:
                            content_lines.append(f"- {item}")
                    else:
                        content_lines.append(str(ai))

                if "sections" in fills:
                    secs = fills["sections"]
                    if isinstance(secs, list):
                        for sec in secs:
                            if isinstance(sec, dict):
                                heading = sec.get("heading") or sec.get("title") or "Section"
                                body = sec.get("body") or sec.get("content") or ""
                                content_lines.append(f"\n## {heading}\n{body}\n")
                            else:
                                content_lines.append(f"\n{sec}\n")

                md_content = "\n".join(content_lines).strip()
                if len(md_content) < 160:
                    md_content += f"\n\n### Report Details\nThis document was generated automatically by Voila Voice AI document pipeline using template '{template_id}' at {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}."

                # Build PDF kwargs from fills
                pdf_kwargs = {
                    "title": fills.get("title", title),
                    "author": fills.get("author", "Voila AI"),
                    "sections": fills.get("sections", [{"heading": "Content", "body": str(fills)}]),
                    "output_dir": ARTIFACTS_DIR,
                    "filename": f"{timestamp}_{safe_title}.pdf",
                    "path": target_path,
                    "content": md_content
                }
                result = document_tools.create_pdf(pdf_kwargs)
                
            elif doc_type == "pptx":
                raw_slides = fills.get("slides", [{"title": "Introduction", "bullets": [str(fills)]}])
                slides_data = []
                for s in raw_slides:
                    if isinstance(s, dict):
                        bullets = s.get("bullets") or s.get("items") or []
                        slides_data.append({
                            "title": s.get("title", "Slide"),
                            "bullets": bullets,
                            "items": bullets
                        })
                    else:
                        slides_data.append({"title": "Slide", "bullets": [str(s)], "items": [str(s)]})

                # Build PPT kwargs from fills
                ppt_kwargs = {
                    "title": fills.get("title", title),
                    "author": fills.get("author", "Voila AI"),
                    "slides": slides_data,
                    "output_dir": ARTIFACTS_DIR,
                    "filename": f"{timestamp}_{safe_title}.pptx",
                    "path": target_path
                }
                result = document_tools.create_ppt(ppt_kwargs)
            else:
                result = f"Unsupported type: {doc_type}"
            
            # Quality gate: check file exists and is non-empty
            actual_file = target_path if os.path.exists(target_path) else (result if isinstance(result, str) and os.path.exists(result) else None)
            if actual_file and os.path.getsize(actual_file) > 100:
                idx = load_index()
                doc_entry = {
                    "id": f"doc_{timestamp}",
                    "template_id": template_id,
                    "title": title,
                    "created_at": datetime.datetime.now().isoformat(),
                    "paths": [actual_file]
                }
                idx.insert(0, doc_entry)
                save_index(idx)

                print(json.dumps({
                    "local_paths": [actual_file],
                    "template_id": template_id,
                    "title": title,
                    "provider": "local"
                }))
            else:
                print(json.dumps({"error": f"Quality gate failed: output was empty or missing. Result: {result}"}))
            return
            
        except Exception as e:
            print(json.dumps({"error": f"Local template generation failed: {e}"}))
            return
    
    # Non-local provider: fall through to existing mock/MCP logic
    mock_mode = os.environ.get("VOILA_DOCS_MOCK") == "1"
    
    # Auto-fill generated at
    if "GENERATED_AT" in reg[template_id].get("placeholders", []):
        fills["GENERATED_AT"] = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M")
    safe_title = "".join([c if c.isalnum() else "_" for c in title])
    
    local_paths = []
    
    if mock_mode:
        for ext in exports:
            filename = f"{timestamp}_{safe_title}.{ext}"
            filepath = os.path.join(ARTIFACTS_DIR, filename)
            
            # Create a mock file
            with open(filepath, 'w', encoding='utf-8') as f:
                f.write(f"MOCK DOCUMENT: {title}\n")
                f.write(f"Template: {template_id}\n")
                f.write(f"Provider: {reg[template_id].get('provider')}\n")
                f.write("\nFILLED DATA:\n")
                for k, v in fills.items():
                    f.write(f"{k}: {v}\n")
                    
            local_paths.append(filepath)
    else:
        # TODO: Implement actual MCP bridge here (call Google Workspace MCP)
        print(json.dumps({"error": "Real MCP not implemented yet. Use set VOILA_DOCS_MOCK=1"}))
        return
        
    # Register in index
    idx = load_index()
    doc_entry = {
        "id": f"doc_{int(datetime.datetime.now().timestamp())}",
        "template_id": template_id,
        "title": title,
        "created_at": datetime.datetime.now().isoformat(),
        "paths": local_paths
    }
    idx.insert(0, doc_entry)
    save_index(idx)
    
    print(json.dumps({
        "local_paths": local_paths,
        "presentation_id": "MOCK_PRESENTATION_ID" if mock_mode else None
    }))

def handle_list_recent():
    print(json.dumps(load_index()))

def handle_open_local(path):
    if sys.platform == "win32":
        os.startfile(path)
    elif sys.platform == "darwin":
        os.system(f"open '{path}'")
    else:
        os.system(f"xdg-open '{path}'")
    print(json.dumps({"status": "opened"}))

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Missing action"}))
        sys.exit(1)
        
    action = sys.argv[1]
    
    if action == "list":
        handle_list()
    elif action == "get":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Missing template_id"}))
            sys.exit(1)
        handle_get(sys.argv[2])
    elif action == "create":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Missing payload"}))
            sys.exit(1)
        handle_create(json.loads(sys.argv[2]))
    elif action == "list_recent":
        handle_list_recent()
    elif action == "open_local":
        if len(sys.argv) < 3:
            print(json.dumps({"error": "Missing path"}))
            sys.exit(1)
        handle_open_local(sys.argv[2])
    else:
        print(json.dumps({"error": "Unknown action"}))
