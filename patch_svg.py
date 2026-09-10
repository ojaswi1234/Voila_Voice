import re

with open('local-agent/document_tools.py', 'r', encoding='utf-8') as f:
    content = f.read()

new_png = '''    def generate_svg_fallback(local_path, color):
        \"\"\"Generate simple PNG placeholder if image download fails (SVG crashes python-pptx).\"\"\"
        try:
            from PIL import Image, ImageDraw
            img = Image.new('RGB', (800, 600), color=color if isinstance(color, str) else 'gray')
            d = ImageDraw.Draw(img)
            d.line([(0,0), (800,600)], fill='white', width=5)
            d.line([(0,600), (800,0)], fill='white', width=5)
            d.text((350, 280), "Image Unavailable", fill='white')
            # If path ends in .svg, change to .png
            if local_path.endswith('.svg'):
                local_path = local_path[:-4] + '.png'
            img.save(local_path, 'PNG')
            return True
        except Exception as e:
            print(f"Fallback PNG generation failed: {e}")
            return False'''

content = re.sub(r'    def generate_svg_fallback\(local_path, color\):.*?(?=    def generate_dynamic_style)', new_png + '\n\n', content, flags=re.DOTALL)

# We also need to fix where it calls generate_svg_fallback to use .png instead of .svg
content = re.sub(r'local_path = os\.path\.join\(cache_dir, f\"\{cache_key\}\.svg\"\)', 'local_path = os.path.join(cache_dir, f"{cache_key}.png")', content)

with open('local-agent/document_tools.py', 'w', encoding='utf-8') as f:
    f.write(content)
