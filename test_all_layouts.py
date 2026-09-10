import sys, os
sys.path.append('local-agent')
import document_tools, pptx

# Full demo deck — every layout type, across 2 new themes
TEST_SLIDES = [
    {"type": "title_slide", "title": "2026 Product Review", "subtitle": "Annual Summary", "author": "Voila AI Team"},
    {"type": "agenda", "title": "Agenda", "items": ["Market Overview", "Product Updates", "Financial Metrics", "Roadmap", "Next Steps"]},
    {"type": "metrics", "title": "Q4 at a Glance", "metrics": [
        {"value": "$2.4M", "label": "Revenue", "sublabel": "+18% QoQ"},
        {"value": "94%", "label": "Retention"},
        {"value": "1,847", "label": "New Users"},
    ]},
    {"type": "timeline", "title": "Product Roadmap", "steps": [
        {"label": "Q1", "description": "Research & Discovery"},
        {"label": "Q2", "description": "Alpha Build"},
        {"label": "Q3", "description": "Beta Launch"},
        {"label": "Q4", "description": "GA Release"},
    ]},
    {"type": "comparison", "title": "Before vs After", "left_title": "Before Voila", "right_title": "After Voila",
     "content_left": "- Manual process\n- 5 hours/week\n- Error-prone\n- No visibility",
     "content_right": "- Fully automated\n- 15 min/week\n- Zero errors\n- Real-time dashboard"},
    {"type": "chart", "title": "Revenue Growth", "chart_type": "bar",
     "chart_data": {"Q1 2026": 180000, "Q2 2026": 210000, "Q3 2026": 240000, "Q4 2026": 290000}},
    {"type": "quote", "content": "Voila changed how our team works — we ship 3x faster.", "author": "CTO, TechCorp"},
    {"type": "content", "title": "Key Takeaways", "content": "- Revenue up 33% YoY\n- Churn reduced to 6%\n- NPS score: 72\n- 5 enterprise contracts signed"},
    {"type": "section", "content": "Thank You"},
    {"type": "title_slide", "title": "Questions?", "subtitle": "hello@voila.ai"},
]

import json
slides_json = json.dumps(TEST_SLIDES)

results = []
for theme in ["illustrated_light", "warm_sunset", "ocean_depth", "forest_sage", "modern_dark", "cyberpunk"]:
    path = f"test_theme_{theme}.pptx"
    result = document_tools.create_ppt({
        "path": path,
        "title": "2026 Product Review",
        "slides": TEST_SLIDES,
        "theme": theme,
        "auto_images": False
    })
    
    # Inspect slide count and shape count
    prs = pptx.Presentation(path)
    shape_counts = [len(s.shapes) for s in prs.slides]
    results.append(f"Theme={theme:20s} | Slides={len(prs.slides):2d} | ShapeCounts={shape_counts} | {result}")

for r in results:
    print(r)
