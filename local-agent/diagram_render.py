import os
import tempfile
import uuid
from playwright.sync_api import sync_playwright

def render_mermaid_to_png(source: str, theme: str = "default", background: str = "transparent", scale: float = 2.0) -> str:
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.jsdelivr.net/npm/mermaid@10.9.1/dist/mermaid.min.js"></script>
        <style>
            body {{ margin: 0; padding: 20px; background: {background}; display: inline-block; }}
            .mermaid {{ display: inline-block; }}
        </style>
    </head>
    <body>
        <div class="mermaid">
            %%{{init: {{'theme': '{theme}', 'htmlLabels': false}}}}%%
{source}
        </div>
        <script>
            mermaid.initialize({{ startOnLoad: true }});
        </script>
    </body>
    </html>
    """
    
    fd, temp_html = tempfile.mkstemp(suffix=".html")
    with os.fdopen(fd, 'w', encoding='utf-8') as f:
        f.write(html)
        
    out_png = os.path.abspath(os.path.join(tempfile.gettempdir(), f"diagram_{uuid.uuid4().hex[:8]}.png"))
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(device_scale_factor=scale)
        page.goto(f"file://{temp_html}", wait_until="networkidle")
        page.wait_for_selector('svg', timeout=10000)
        element = page.locator('.mermaid')
        element.screenshot(path=out_png, omit_background=(background == "transparent"))
        browser.close()
        
    os.remove(temp_html)
    return out_png

def svg_file_to_png(svg_path: str, scale: float = 2.0) -> str:
    out_png = os.path.abspath(os.path.join(tempfile.gettempdir(), f"svg_{uuid.uuid4().hex[:8]}.png"))
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(device_scale_factor=scale)
        page.goto(f"file://{os.path.abspath(svg_path)}", wait_until="networkidle")
        page.screenshot(path=out_png, omit_background=True)
        browser.close()
    return out_png
