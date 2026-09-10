import urllib.request
import urllib.parse
import json

def search_image_url(search_query):
    query = search_query.strip()
    if len(query) > 50:
        query = query[:50]
        
    url = 'https://api.openverse.org/v1/images/?q=' + urllib.parse.quote(query) + '&format=json&page_size=5'
    req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 VoilaAI/1.0'})
    
    with urllib.request.urlopen(req, timeout=10) as response:
        data = json.loads(response.read().decode('utf-8'))
        
    results = data.get('results', [])
    if not results:
        return None
        
    best_candidate = None
    best_score = -1
    selection_reason = ""
    
    for idx, img in enumerate(results):
        w = img.get('width', 0)
        h = img.get('height', 0)
        url_candidate = img.get('url', '')
        if not url_candidate:
            continue
            
        score = 0
        reason = f"Index {idx}: "
        
        if w and h and w > h:
            score += 100
            reason += "Landscape aspect ratio (+100). "
        elif w and h and w == h:
            score += 50
            reason += "Square aspect ratio (+50). "
            
        if w and w >= 800:
            score += 50
            reason += "Good resolution >= 800px (+50). "
        
        if score > best_score:
            best_score = score
            best_candidate = img
            selection_reason = reason
            
    if best_candidate:
        print(f"IMAGE SELECTION: Query '{query}'. Picked candidate {best_candidate.get('url')} because: {selection_reason}")
        return best_candidate.get('url')
        
    print(f"IMAGE SELECTION: Query '{query}'. Fallback to index 0.")
    return results[0].get('url')

queries = ['docker container architecture', 'birthday cake recipe', 'mountain landscape sunset']
for q in queries:
    print(f'=== Testing Query: {q} ===')
    url = search_image_url(q)
    print(f'Result: {url}\n')
