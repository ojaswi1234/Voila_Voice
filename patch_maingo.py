import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    content = f.read()

# Update tool description
content = content.replace(
    '\"description\": \"Search type: \'text\' (default, DuckDuckGo text search) or \'image\' (Picsum random image search)\"',
    '\"description\": \"Search type: \'text\' (default, DuckDuckGo text search) or \'image\' (Openverse CC image search)\"'
)

content = content.replace(
    '\"description\": \"If true, AI will automatically search for and download relevant images for content/image slides using web_research\"',
    '\"description\": \"If true, AI will automatically search for and download relevant images using Openverse API for content/image slides\"'
)

# Replace the web_research image branch
old_image = '''		} else if searchType == "image" {
			// Use Picsum.photos (no API key required, reliable public service)
			seed := strings.ReplaceAll(query, " ", "")
			if len(seed) > 10 {
				seed = seed[:10]
			}
			imageSearchURL := "https://picsum.photos/seed/" + seed + "/800x600"
			resp, err := http.Get(imageSearchURL)
			if err != nil {
				return "error: failed to generate image: " + err.Error()
			}
			defer resp.Body.Close()
			
			// Picsum returns 200 with image directly
			return "image_url: " + imageSearchURL
		}'''

new_image = '''		} else if searchType == "image" {
			// Bug #X Fix: Replace Picsum with actual Openverse content-matching API
			escapedQuery := url.QueryEscape(query)
			openverseURL := "https://api.openverse.org/v1/images/?q=" + escapedQuery + "&format=json&page_size=5"
			
			// Custom client with user-agent
			req, _ := http.NewRequest("GET", openverseURL, nil)
			req.Header.Set("User-Agent", "Mozilla/5.0 VoilaAI/1.0")
			
			client := &http.Client{Timeout: 10 * time.Second}
			resp, err := client.Do(req)
			
			if err != nil {
				return "error: failed to fetch image: " + err.Error()
			}
			defer resp.Body.Close()
			
			var result struct {
				Results []struct {
					URL    string json:"url"
					Width  int    json:"width"
					Height int    json:"height"
				} json:"results"
			}
			if err := json.NewDecoder(resp.Body).Decode(&result); err != nil {
				return "error: invalid json from Openverse: " + err.Error()
			}
			
			if len(result.Results) == 0 {
				return "error: no images found for query"
			}
			
			bestURL := result.Results[0].URL
			bestScore := -1
			for _, img := range result.Results {
				score := 0
				if img.Width > img.Height { score += 100 }
				if img.Width == img.Height { score += 50 }
				if img.Width >= 800 { score += 50 }
				if score > bestScore {
					bestScore = score
					bestURL = img.URL
				}
			}
			
			return "image_url: " + bestURL
		}'''

if old_image in content:
    content = content.replace(old_image, new_image)
    with open('local-agent/main.go', 'w', encoding='utf-8') as f:
        f.write(content)
    print('main.go image search patched')
else:
    print('Could not find old_image in main.go')
