import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    content = f.read()

new_image = '''		} else if searchType == "image" {
			escapedQuery := url.QueryEscape(query)
			openverseURL := "https://api.openverse.org/v1/images/?q=" + escapedQuery + "&format=json&page_size=5"
			
			req, _ := http.NewRequest("GET", openverseURL, nil)
			req.Header.Set("User-Agent", "Mozilla/5.0 VoilaAI/1.0")
			
			client := &http.Client{Timeout: 10 * time.Second}
			resp, err := client.Do(req)
			if err != nil { return "error: failed to fetch image: " + err.Error() }
			defer resp.Body.Close()
			
			var result struct {
				Results []struct {
					URL    string `json:"url"`
					Width  int    `json:"width"`
					Height int    `json:"height"`
				} `json:"results"`
			}
			if err := json.NewDecoder(resp.Body).Decode(&result); err != nil { return "error: invalid json from Openverse" }
			if len(result.Results) == 0 { return "error: no images found" }
			
			bestURL := result.Results[0].URL
			bestScore := -1
			for _, img := range result.Results {
				score := 0
				if img.Width > img.Height { score += 100 }
				if img.Width == img.Height { score += 50 }
				if img.Width >= 800 { score += 50 }
				if score > bestScore { bestScore = score; bestURL = img.URL }
			}
			return "image_url: " + bestURL
		}'''

content = re.sub(r'\} else if searchType == "image" \{.*?(?=\} else if searchType == "auto_images" |\} else \{|\}\n\t\t\n\t\t// Original text search)', new_image + '\n', content, flags=re.DOTALL)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(content)
