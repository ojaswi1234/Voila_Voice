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
    template_id = payload.get("template_id")
    title = payload.get("title", "Untitled")
    fills = payload.get("fills", {})
    exports = payload.get("export", ["pdf"])
    
    reg = load_registry()
    if template_id not in reg:
        print(json.dumps({"error": f"Template {template_id} not found"}))
        return
    
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
