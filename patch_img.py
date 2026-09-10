import re

with open('local-agent/document_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_func = '''    def search_image_url(search_query):
        \"\"\"Search for image URL using Picsum (no API key required).\"\"\"
        try:
            # Use Picsum.photos for random images (seeded by query for consistency)
            seed = search_query.replace(' ', '')[:10]  # Use first 10 chars as seed
            image_url = f"https://picsum.photos/seed/{seed}/800/600"
            return image_url
        except Exception as e:
            return None'''

new_func = '''    def search_image_url(search_query):
        \"\"\"Search for image URL using Openverse API with careful selection.\"\"\"
        import urllib.request
        import urllib.parse
        import json
        try:
            # Clean and truncate query for safety
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
                
            # Careful selection step: fetch 3-5 candidates per query, pick the best.
            # We want landscape images (width > height) if possible.
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
                
                # Reward Landscape Aspect Ratio for PPTX
                if w and h and w > h:
                    score += 100
                    reason += "Landscape aspect ratio (+100). "
                elif w and h and w == h:
                    score += 50
                    reason += "Square aspect ratio (+50). "
                    
                # Reward high resolution but not insanely huge
                if w >= 800:
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
        except Exception as e:
            print(f"Image search error: {e}")
            return None'''

if old_func in content:
    content = content.replace(old_func, new_func)
    with open('local-agent/document_tools.py', 'w', encoding='utf-8') as f:
        f.write(content)
    print('document_tools.py image search patched')
else:
    print('Could not find old_func in document_tools.py')
