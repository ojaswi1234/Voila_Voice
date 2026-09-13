import urllib.request, urllib.parse, sys, re

query = sys.argv[1] if len(sys.argv) > 1 else ""
if not query:
    print("No query")
    sys.exit(1)

req = urllib.request.Request(
    'https://lite.duckduckgo.com/lite/', 
    data=f'q={urllib.parse.quote(query)}'.encode('utf-8'), 
    headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
)

try:
    html = urllib.request.urlopen(req).read().decode('utf-8')
    
    # Very simple Regex to extract result snippets from DDG Lite
    # <td class='result-snippet'> ... </td>
    snippets = re.findall(r"<td class='result-snippet'>\s*(.*?)\s*</td>", html, re.DOTALL | re.IGNORECASE)
    
    if snippets:
        for idx, s in enumerate(snippets[:5]):
            # Strip remaining HTML tags
            clean_text = re.sub(r'<[^>]+>', '', s).strip()
            print(f"- {clean_text}")
    else:
        print("No snippets found.")
except Exception as e:
    print(f"Error: {e}")
