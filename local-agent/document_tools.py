import sys
import json
import csv
import io
import os
import re
import traceback


def read_pdf(kwargs):
    import PyPDF2
    path = kwargs.get('path')
    if not path: return "Error: path is required"
    try:
        text = []
        with open(path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            for page in reader.pages:
                extracted = page.extract_text()
                if extracted: text.append(extracted)
        return "\n".join(text) if text else "No text found in PDF."
    except Exception as e:
        return f"Error reading PDF: {e}"

# --- HELPERS ---

def _strip_markdown(text):
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    text = re.sub(r'\*(.*?)\*', r'\1', text)
    text = re.sub(r'__(.*?)__', r'\1', text)
    text = re.sub(r'_(.*?)_', r'\1', text)
    text = re.sub(r'`(.*?)`', r'\1', text)
    # Handle nested bold in headings: **text** inside headings
    text = re.sub(r'\*\*(.*?)\*\*', r'\1', text)
    return text

def _transliterate_unicode(text):
    """Map common Unicode typographic characters to core-font-safe ASCII equivalents."""
    # Em dash to double hyphen
    text = text.replace('—', '--')
    # En dash to single hyphen
    text = text.replace('–', '-')
    # Curly quotes to straight quotes
    text = text.replace('"', '"').replace('"', '"')
    text = text.replace(''', "'").replace(''', "'")
    text = text.replace(''', "'").replace(''', "'")
    # Ellipsis to three periods
    text = text.replace('…', '...')
    # Non-breaking space to regular space
    text = text.replace('\u00A0', ' ')
    # Common currency symbols
    text = text.replace('€', 'EUR').replace('£', 'GBP').replace('¥', 'JPY')
    return text

# --- (CSV/EXCEL Code omitted for brevity, keeping V3 implementations) ---
def read_csv(kwargs):
    path = kwargs.get('path'); analyze = kwargs.get('analyze', False)
    with open(path, 'r', encoding='utf-8') as f:
        data = list(csv.reader(f))
    if not data: return "File is empty."
    if analyze: return _analyze_dataset(data[0], data[1:])
    lines = [','.join(data[0])]
    for i, row in enumerate(data[1:]):
        if i >= 100: lines.append(f"... (truncated)"); break
        lines.append(','.join(row))
    return '\n'.join(lines)

def create_csv(kwargs):
    path = kwargs.get('path'); data = kwargs.get('data') 
    if isinstance(data, str):
        try: data = json.loads(data)
        except: pass
    if isinstance(data, str):
        with open(path, 'w', encoding='utf-8') as f: f.write(data)
    else:
        if not data: return "No data provided."
        with open(path, 'w', encoding='utf-8', newline='') as f:
            if isinstance(data[0], dict):
                writer = csv.DictWriter(f, fieldnames=data[0].keys()); writer.writeheader(); writer.writerows(data)
            elif isinstance(data[0], list):
                writer = csv.writer(f); writer.writerows(data)
    return f"Successfully created CSV at {path}"

def read_excel(kwargs):
    import openpyxl
    wb = openpyxl.load_workbook(kwargs.get('path'), data_only=True)
    ws = wb[kwargs.get('sheet_name')] if kwargs.get('sheet_name') in wb.sheetnames else wb.active
    data = list(ws.iter_rows(values_only=True))
    if not data: return "File is empty."
    headers = [str(x) if x is not None else f"Col{i}" for i, x in enumerate(data[0])]
    if kwargs.get('analyze', False): return _analyze_dataset(headers, data[1:])
    lines = [','.join(headers)]
    for i, row in enumerate(data[1:]):
        if i >= 100: lines.append("... (truncated)"); break
        lines.append(','.join([str(x) if x is not None else "" for x in row]))
    return '\n'.join(lines)

def create_excel(kwargs):
    import openpyxl; from openpyxl.worksheet.table import Table, TableStyleInfo; from openpyxl.utils import get_column_letter; from openpyxl.chart import BarChart, PieChart, LineChart, Reference
    path = kwargs.get('path'); data = kwargs.get('data')
    wb = openpyxl.Workbook(); ws = wb.active
    if isinstance(data, str):
        try: data = json.loads(data)
        except: pass
    keys = []
    if data and isinstance(data, list):
        if isinstance(data[0], dict):
            keys = list(data[0].keys()); ws.append(keys)
            for row in data: ws.append([row.get(k, "") for k in keys])
        elif isinstance(data[0], list):
            keys = [f"Col{i}" for i in range(len(data[0]))]
            for i, row in enumerate(data):
                ws.append(row)
                if i == 0: keys = [str(x) for x in row]
    if len(data) > 0 and len(keys) > 0:
        for col in ws.columns:
            max_length = 0; col_letter = col[0].column_letter
            for cell in col:
                try: max_length = max(max_length, len(str(cell.value)))
                except: pass
            ws.column_dimensions[col_letter].width = max_length + 2
        tab = Table(displayName="DataTable", ref=f"A1:{get_column_letter(len(keys))}{len(data)+1}")
        tab.tableStyleInfo = TableStyleInfo(name="TableStyleMedium9", showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=True)
        ws.add_table(tab)
        ctype = kwargs.get('chart_type')
        if ctype and len(keys) >= 2:
            if ctype == 'pie': chart = PieChart()
            elif ctype == 'line': chart = LineChart()
            else: chart = BarChart()
            chart.title = kwargs.get('chart_title', 'Data Chart')
            chart.add_data(Reference(ws, min_col=2, min_row=1, max_row=len(data)+1, max_col=len(keys)), titles_from_data=True)
            chart.set_categories(Reference(ws, min_col=1, min_row=2, max_row=len(data)+1))
            ws.add_chart(chart, f"{get_column_letter(len(keys) + 2)}2")
    wb.save(path)
    return f"Successfully created EXCEL file at {path}"

def modify_excel(kwargs):
    import openpyxl; wb = openpyxl.load_workbook(kwargs.get('path')); ws = wb.active
    updates = kwargs.get('updates', {})
    if isinstance(updates, str): updates = json.loads(updates)
    for cell, val in updates.items(): ws[cell] = val
    wb.save(kwargs.get('path'))
    return f"Successfully updated Excel"

def _analyze_dataset(headers, rows):
    return "Analysis placeholder"

# --- DOCX CREATION ---
def create_doc(kwargs):
    import docx
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    from design_tokens import get_theme
    
    path = kwargs.get('path')
    content = kwargs.get('content', '')
    theme = kwargs.get('theme', 'modern_dark')
    theme_config = get_theme(theme)
    
    doc = docx.Document()
    
    # Apply theme-based styles
    styles = doc.styles
    try:
        styles['Title'].font.name = theme_config['font_heading']
        styles['Title'].font.size = Pt(32)
        styles['Title'].font.color.rgb = RGBColor(*theme_config['color_heading'])
        
        styles['Heading 1'].font.name = theme_config['font_heading']
        styles['Heading 1'].font.size = Pt(20)
        styles['Heading 1'].font.color.rgb = RGBColor(*theme_config['color_accent'])
        
        styles['Normal'].font.name = theme_config['font_body']
        styles['Normal'].font.size = Pt(11)
        styles['Normal'].font.color.rgb = RGBColor(*theme_config['color_text'])
    except: pass
    
    try:
        quote_style = styles.add_style('BlockQuote', docx.enum.style.WD_STYLE_TYPE.PARAGRAPH)
        quote_style.font.name = theme_config['font_body']
        quote_style.font.italic = True
        quote_style.font.size = Pt(12)
        quote_style.font.color.rgb = RGBColor(*theme_config['color_text'])
    except: quote_style = styles['Normal']

    in_code_block = False
    table_buffer = []

    def flush_table():
        if not table_buffer: return
        valid_rows = [r for r in table_buffer if not re.match(r'^[\s\|\-]+$', r)]
        if valid_rows:
            cols = len([c for c in valid_rows[0].split('|') if c.strip()])
            if cols > 0:
                table = doc.add_table(rows=len(valid_rows), cols=cols)
                try: table.style = 'Light Shading Accent 1'
                except: table.style = 'Table Grid'
                for i, row in enumerate(valid_rows):
                    cells = [c.strip() for c in row.split('|') if c.strip()]
                    for j, c in enumerate(cells):
                        if j < cols: table.cell(i, j).text = _strip_markdown(c)
        table_buffer.clear()

    lines = content.split('\n')
    for line in lines:
        stripped = line.strip()
        
        # Table Detection
        if stripped.startswith('|') and stripped.endswith('|'):
            table_buffer.append(stripped)
            continue
        else:
            flush_table()

        if not stripped and not in_code_block: continue
            
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            if in_code_block: doc.add_paragraph() 
            continue
            
        if in_code_block:
            p = doc.add_paragraph(line)
            p.style.font.name = 'Consolas'
            p.style.font.size = Pt(9.5)
            p.style.font.color.rgb = RGBColor(*theme_config['color_primary'])
            continue
            
        img_match = re.match(r'^!\[.*?\]\((.*?)\)$', stripped)
        if img_match:
            try:
                doc.add_picture(img_match.group(1), width=Inches(5.5)); doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            except: doc.add_paragraph(f"[Image not found: {img_match.group(1)}]")
            continue

        if stripped.startswith('# '):
            p = doc.add_paragraph(_strip_markdown(stripped[2:]), style='Title')
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif stripped.startswith('## '):
            doc.add_paragraph(_strip_markdown(stripped[3:]), style='Heading 1')
        elif stripped.startswith('### '):
            doc.add_paragraph(_strip_markdown(stripped[4:]), style='Heading 2')
        elif stripped.startswith('> '):
            p = doc.add_paragraph(_strip_markdown(stripped[2:]), style='BlockQuote')
            p.paragraph_format.left_indent = Inches(0.5)
        elif stripped.startswith('- ') or stripped.startswith('* '):
            cleaned = _strip_markdown(stripped[2:])
            doc.add_paragraph(cleaned, style='List Bullet')
        elif re.match(r'^\d+\.\s', stripped):
            cleaned = _strip_markdown(re.sub(r'^\d+\.\s', '', stripped))
            doc.add_paragraph(cleaned, style='List Number')
        else:
            p = doc.add_paragraph(style='Normal')
            parts = re.split(r'(\*\*.*?\*\*)', line)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    run = p.add_run(part[2:-2]); run.bold = True
                else:
                    p.add_run(part)
                    
    flush_table()
    doc.save(path)
    return f"Successfully created Word Document (DOCX) at {path}"

# --- PDF CREATION ---
def create_pdf(kwargs):
    from fpdf import FPDF
    from design_tokens import get_theme
    
    path = kwargs.get('path')
    content = kwargs.get('content', '')
    watermark = kwargs.get('watermark', '')
    theme = kwargs.get('theme', 'modern_dark')
    theme_config = get_theme(theme)
    
    class PDF(FPDF):
        def __init__(self, theme_config, watermark_text):
            super().__init__()
            self.theme_config = theme_config
            self.watermark_text = watermark_text
        
        def header(self):
            self.set_draw_color(*self.theme_config['color_accent'])
            self.set_line_width(0.8)
            self.line(10, 15, 200, 15)
            if self.watermark_text:
                self.set_font(self.theme_config['pdf_font_body'], '', 50)
                self.set_text_color(240, 240, 240)
                self.text(30, 150, self.watermark_text.upper())
        def footer(self):
            self.set_y(-15)
            self.set_font(self.theme_config['pdf_font_body'], '', 8)
            self.set_text_color(149, 165, 166)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    pdf = PDF(theme_config, watermark)
    
    # FPDF limitation: Only core fonts (Arial, Times, Courier, Helvetica, Symbol, ZapfDingbats) work without embedding
    # Theme fonts mapped to core fonts in design_tokens.py (pdf_font_heading, pdf_font_body)
    pdf.set_font(theme_config['pdf_font_body'], '', 11)
    
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    in_code_block = False
    table_buffer = []

    def flush_table():
        if not table_buffer: return
        valid_rows = [r for r in table_buffer if not re.match(r'^[\s\|\-]+$', r)]
        if valid_rows:
            pdf.ln(5)
            cols = len([c for c in valid_rows[0].split('|') if c.strip()])
            if cols > 0:
                col_width = (200 - 20) / cols
                for i, row in enumerate(valid_rows):
                    cells = [c.strip() for c in row.split('|') if c.strip()]
                    for j, c in enumerate(cells):
                        if j >= cols: break
                        pdf.set_font(theme_config['pdf_font_body'], '', 10)
                        if i == 0:
                            pdf.set_fill_color(*theme_config['color_accent'])
                            pdf.set_text_color(255, 255, 255)
                        else:
                            if i % 2 == 0:
                                pdf.set_fill_color(240, 240, 240)
                            else:
                                pdf.set_fill_color(255, 255, 255)
                            pdf.set_text_color(*theme_config['color_text'])
                        
                        clean_c = _strip_markdown(c)
                        # Transliterate Unicode characters to ASCII equivalents
                        clean_c = _transliterate_unicode(clean_c)
                        # FPDF limitation: encode latin-1 with replace converts remaining non-Latin-1 chars to ?
                        clean_c = clean_c.encode('latin-1', 'replace').decode('latin-1')
                        # Basic cell - FPDF limitation: text may not wrap perfectly in tables
                        pdf.cell(col_width, 8, clean_c, 1, 0, 'C', fill=True)
                    pdf.ln(8)
            pdf.ln(5)
        table_buffer.clear()

    lines = content.split('\n')
    for line in lines:
        stripped = line.strip()
        
        # Table Detection
        if stripped.startswith('|') and stripped.endswith('|'):
            table_buffer.append(stripped)
            continue
        else:
            flush_table()

        if not stripped and not in_code_block:
            pdf.ln(3); continue
            
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            if in_code_block: pdf.ln(2)
            continue
            
        line_safe = _strip_markdown(line)
        # Transliterate Unicode characters to ASCII equivalents before latin-1 encoding
        line_safe = _transliterate_unicode(line_safe)
        # FPDF limitation: encode latin-1 with replace converts remaining non-Latin-1 chars to ?
        # This handles any characters not covered by transliteration
        line_safe = line_safe.encode('latin-1', 'replace').decode('latin-1')
            
        if in_code_block:
            pdf.set_font(theme_config['pdf_font_body'], '', 9)
            pdf.set_text_color(*theme_config['color_primary'])
            pdf.set_fill_color(245, 245, 245)
            pdf.cell(0, 5, line_safe, 0, 1, 'L', fill=True)
            continue

        img_match = re.match(r'^!\[.*?\]\((.*?)\)$', stripped)
        if img_match:
            try: pdf.image(img_match.group(1), w=150); pdf.ln(5)
            except: 
                pdf.set_font(theme_config['pdf_font_body'], '', 10)
                pdf.set_text_color(255, 0, 0)
                pdf.cell(0, 5, f"[Image error: {img_match.group(1)}]", 0, 1, 'L')
            continue
        
        if stripped.startswith('# '):
            pdf.set_font(theme_config['pdf_font_heading'], '', 24)
            pdf.set_text_color(*theme_config['color_heading'])
            pdf.multi_cell(0, 12, line_safe[2:])
            pdf.ln(3)
        elif stripped.startswith('## '):
            pdf.set_font(theme_config['pdf_font_heading'], '', 18)
            pdf.set_text_color(*theme_config['color_accent'])
            pdf.multi_cell(0, 10, line_safe[3:])
            pdf.ln(2)
        elif stripped.startswith('### '):
            pdf.set_font(theme_config['pdf_font_heading'], '', 14)
            pdf.set_text_color(*theme_config['color_text'])
            pdf.multi_cell(0, 8, line_safe[4:])
            pdf.ln(2)
        elif stripped.startswith('- ') or stripped.startswith('* '):
            pdf.set_font(theme_config['pdf_font_body'], '', 11)
            pdf.set_text_color(*theme_config['color_text'])
            pdf.cell(5, 6, chr(149), 0, 0)
            pdf.multi_cell(0, 6, line_safe[2:])
        elif stripped.startswith('> '):
            pdf.set_font(theme_config['pdf_font_body'], '', 11)
            pdf.set_text_color(100, 100, 100)
            pdf.set_x(20)
            pdf.multi_cell(0, 6, line_safe[2:])
        else:
            pdf.set_font(theme_config['pdf_font_body'], '', 11)
            pdf.set_text_color(*theme_config['color_text'])
            pdf.multi_cell(0, 6, line_safe)
            
    flush_table()
    pdf.output(path)
    return f"Successfully created PDF at {path}"

# --- PPT CREATION ---
def create_ppt(kwargs):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from design_tokens import get_theme
    import hashlib
    import os
    import requests
    
    path = kwargs.get('path')
    title = kwargs.get('title', 'Presentation')
    slides_data = kwargs.get('slides', [])
    theme = kwargs.get('theme', 'modern_dark')
    theme_config = get_theme(theme)
    auto_images = kwargs.get('auto_images', False)
    
    if isinstance(slides_data, str):
        try: slides_data = json.loads(slides_data)
        except: slides_data = [{"title": "Content", "content": slides_data}]

    # Image cache directory
    cache_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'image_cache')
    os.makedirs(cache_dir, exist_ok=True)

    def get_cached_image_url(search_query):
        """Return cached image URL if available, None otherwise."""
        cache_key = hashlib.md5(search_query.encode()).hexdigest()
        cache_file = os.path.join(cache_dir, f"{cache_key}.txt")
        if os.path.exists(cache_file):
            with open(cache_file, 'r') as f:
                return f.read().strip()
        return None

    def cache_image_url(search_query, image_url):
        """Cache image URL for future use."""
        cache_key = hashlib.md5(search_query.encode()).hexdigest()
        cache_file = os.path.join(cache_dir, f"{cache_key}.txt")
        with open(cache_file, 'w') as f:
            f.write(image_url)

    def download_image(image_url, local_path):
        """Download image from URL to local path."""
        try:
            resp = requests.get(image_url, timeout=30)
            resp.raise_for_status()
            with open(local_path, 'wb') as f:
                f.write(resp.content)
            return True
        except Exception as e:
            return False

    def search_image_url(search_query):
        """Search Openverse for a CC-licensed image with careful scoring.
        Falls back to simpler queries if the full query returns no results,
        so niche topics (e.g. 'Agentic AI') still get a visually relevant image.
        """
        import urllib.request
        import urllib.parse
        import json

        def _openverse_fetch(query):
            """Return scored best result URL for a given query, or None."""
            query = query.strip()[:60]
            url = ('https://api.openverse.org/v1/images/?q='
                   + urllib.parse.quote(query)
                   + '&format=json&page_size=5')
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 VoilaAI/1.0'})
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    data = json.loads(resp.read().decode('utf-8'))
            except Exception:
                return None, None

            results = data.get('results', [])
            if not results:
                return None, None

            best_candidate = None
            best_score     = -1
            selection_reason = ''

            for idx, img in enumerate(results):
                w = img.get('width', 0)
                h = img.get('height', 0)
                url_candidate = img.get('url', '')
                if not url_candidate:
                    continue
                score = 0
                reason = f'Index {idx}: '
                if w and h and w > h:
                    score += 100; reason += 'Landscape aspect ratio (+100). '
                elif w and h and w == h:
                    score += 50;  reason += 'Square aspect ratio (+50). '
                if w >= 800:
                    score += 50;  reason += 'Good resolution >= 800px (+50). '
                if score > best_score:
                    best_score = score
                    best_candidate = img
                    selection_reason = reason

            if best_candidate:
                return best_candidate.get('url'), selection_reason
            return results[0].get('url'), 'Fallback to index 0.'

        try:
            raw = search_query.strip()

            # ── Progressive fallback: full → first-2-words → first-word ───
            words = raw.split()
            candidates = [
                raw,                                # e.g. "neural network deep learning"
                ' '.join(words[:3]) if len(words) > 3 else None,  # first 3 words
                ' '.join(words[:2]) if len(words) > 1 else None,  # first 2 words
                words[0] if words else None,        # just the first keyword
            ]
            candidates = [c for c in candidates if c]  # remove None

            for query in candidates:
                url_result, reason = _openverse_fetch(query)
                if url_result:
                    print(f"IMAGE SELECTION: Query '{query}'. Picked {url_result} because: {reason}")
                    return url_result

            print(f"IMAGE SELECTION: No results found for any fallback of '{raw}'")
            return None
        except Exception as e:
            print(f"Image search error: {e}")
            return None

    def get_image_for_slide(slide):
        """Get image URL for a slide, using cache or performing search."""
        if not auto_images:
            return None
        
        # Generate search query from slide title/content
        title = slide.get('title', '')
        content = slide.get('content', '')
        search_query = f"{title} {content}" if title and content else (title or content)
        
        if not search_query:
            return None
        
        # Check cache first
        cached_url = get_cached_image_url(search_query)
        if cached_url:
            return cached_url
        
        # Perform image search
        image_url = search_image_url(search_query)
        if image_url:
            cache_image_url(search_query, image_url)
        
        return image_url

    def calculate_image_dimensions(img_path, max_width=Inches(6), max_height=Inches(3.5)):
        """Calculate dimensions that fit within max bounds while preserving aspect ratio."""
        from PIL import Image
        
        try:
            with Image.open(img_path) as img:
                img_width, img_height = img.size
                
                # Convert to inches (assuming 96 DPI)
                img_width_in = img_width / 96
                img_height_in = img_height / 96
                
                # Calculate scaling factor
                width_ratio = max_width.inches / img_width_in
                height_ratio = max_height.inches / img_height_in
                scale = min(width_ratio, height_ratio)
                
                final_width = Inches(img_width_in * scale)
                final_height = Inches(img_height_in * scale)
                
                return final_width, final_height
        except:
            # Fallback to default dimensions
            return max_width, max_height

    def generate_svg_fallback(local_path, color):
        """Generate simple PNG placeholder if image download fails (SVG crashes python-pptx)."""
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
            return False

    def generate_dynamic_style(slides_data, theme_hint):
        """Randomized variation, not AI-generated design. (Interim feature)"""
        import random
        random.seed(hash(str(slides_data) + theme_hint))
        
        # Analyze task depth from slides
        slide_count = len(slides_data)
        has_charts = any(s.get('type') == 'chart' for s in slides_data)
        has_images = any(s.get('type') == 'image' for s in slides_data)
        has_quotes = any(s.get('type') == 'quote' for s in slides_data)
        
        # Generate unique color palette
        primary_color = (
            random.randint(20, 100),
            random.randint(20, 100),
            random.randint(40, 140)
        )
        
        accent_color = (
            random.randint(150, 255),
            random.randint(50, 150),
            random.randint(50, 150)
        )
        
        # Font selection based on content type
        if has_quotes:
            font_heading = "Georgia"
            font_body = "Segoe UI"
        elif has_charts:
            font_heading = "Segoe UI"
            font_body = "Arial"
        else:
            font_heading = "Segoe UI"
            font_body = "Georgia"
        
        dynamic_style = {
            'color_primary': primary_color,
            'color_accent': accent_color,
            'color_text': (50, 50, 50),
            'color_heading': tuple(max(0, min(255, int(c * 0.8))) for c in accent_color),
            'font_heading': font_heading,
            'font_body': font_body,
            'layout_complexity': 'high' if slide_count > 10 or (has_charts and has_images) else 'medium' if slide_count > 5 else 'simple'
        }
        
        return dynamic_style

    prs = Presentation()
    
    # Apply theme colors (use dynamic style if theme == "dynamic")
    if theme == "dynamic":
        dynamic_style = generate_dynamic_style(slides_data, theme)
        bg_color = RGBColor(*dynamic_style['color_primary'])
        title_color = RGBColor(*dynamic_style['color_heading'])
        accent_color = RGBColor(*dynamic_style['color_accent'])
        text_color = RGBColor(*dynamic_style['color_text'])
        font_heading = dynamic_style['font_heading']
        font_body = dynamic_style['font_body']
    else:
        bg_color = RGBColor(*theme_config['color_primary'])
        title_color = RGBColor(*theme_config['color_heading'])
        accent_color = RGBColor(*theme_config['color_accent'])
        text_color = RGBColor(*theme_config['color_text'])
        font_heading = theme_config['font_heading']
        font_body = theme_config['font_body']

    # ── GRADIENT BACKGROUND ENGINE ─────────────────────────────────────────
    def _apply_gradient_bg(slide, start_rgb, end_rgb, angle_deg=135):
        """Inject gradient fill into slide background via raw lxml XML manipulation.
        python-pptx's high-level API only supports solid fills; gradients require
        direct OOXML element injection into the p:cSld/p:bg element."""
        try:
            from lxml import etree
            from pptx.oxml.ns import qn
            NS_P = 'http://schemas.openxmlformats.org/presentationml/2006/main'
            NS_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'

            def hex6(rgb):
                return '%02X%02X%02X' % tuple(max(0, min(255, int(c))) for c in rgb)

            ang_emu = int(angle_deg * 60000)
            cSld = slide._element.find(qn('p:cSld'))
            if cSld is None:
                return

            existing = cSld.find(qn('p:bg'))
            if existing is not None:
                cSld.remove(existing)

            bg_xml = (
                f'<p:bg xmlns:p="{NS_P}" xmlns:a="{NS_A}">'
                f'<p:bgPr>'
                f'<a:gradFill rot="1">'
                f'<a:gsLst>'
                f'<a:gs pos="0"><a:srgbClr val="{hex6(start_rgb)}"/></a:gs>'
                f'<a:gs pos="100000"><a:srgbClr val="{hex6(end_rgb)}"/></a:gs>'
                f'</a:gsLst>'
                f'<a:lin ang="{ang_emu}" scaled="0"/>'
                f'</a:gradFill>'
                f'<a:effectLst/>'
                f'</p:bgPr>'
                f'</p:bg>'
            )
            cSld.insert(0, etree.fromstring(bg_xml))
        except Exception:
            slide.background.fill.solid()
            slide.background.fill.fore_color.rgb = bg_color  # safe fallback

    def apply_bg(slide):
        """Apply background: gradient if theme supports it, solid otherwise."""
        if theme_config.get('gradient') and not (theme == 'dynamic'):
            _apply_gradient_bg(
                slide,
                theme_config['gradient_start'],
                theme_config['gradient_end'],
                theme_config.get('gradient_angle', 135)
            )
        else:
            slide.background.fill.solid()
            slide.background.fill.fore_color.rgb = bg_color

    # ── CARD SHAPE HELPER ──────────────────────────────────────────────────
    def _make_rounded(shape, adj=16667):
        """Morph a rectangle to roundRect via direct OOXML geometry edit."""
        try:
            from lxml import etree
            from pptx.oxml.ns import qn
            spPr = shape._element.find(qn('p:spPr'))
            if spPr is None:
                return
            prstGeom = spPr.find(qn('a:prstGeom'))
            if prstGeom is not None:
                prstGeom.set('prst', 'roundRect')
                avLst = prstGeom.find(qn('a:avLst'))
                if avLst is None:
                    avLst = etree.SubElement(prstGeom, qn('a:avLst'))
                for gd in list(avLst.findall(qn('a:gd'))):
                    avLst.remove(gd)
                gd = etree.SubElement(avLst, qn('a:gd'))
                gd.set('name', 'adj')
                gd.set('fmla', f'val {adj}')
        except Exception:
            pass

    def _add_shadow(shape, blur=60000, dist=25000, alpha=13000):
        """Add a soft drop-shadow to a shape via OOXML effectLst injection."""
        try:
            from lxml import etree
            from pptx.oxml.ns import qn
            NS_A = 'http://schemas.openxmlformats.org/drawingml/2006/main'
            spPr = shape._element.find(qn('p:spPr'))
            if spPr is None:
                return
            eff = spPr.find(qn('a:effectLst'))
            if eff is None:
                eff = etree.SubElement(spPr, qn('a:effectLst'))
            for old in list(eff.findall(qn('a:outerShdw'))):
                eff.remove(old)
            eff.append(etree.fromstring(
                f'<a:outerShdw xmlns:a="{NS_A}" blurRad="{blur}" dist="{dist}" '
                f'dir="5400000" algn="ctr" rotWithShape="0">'
                f'<a:srgbClr val="000000"><a:alpha val="{alpha}"/></a:srgbClr>'
                f'</a:outerShdw>'
            ))
        except Exception:
            pass

    def _add_card(slide, left, top, width, height, fill_rgb=None, accent_rgb=None, border_rgb=None):
        """Gamma-style card: rounded rectangle + drop shadow + top accent bar.

        Visual hierarchy:
          ╔══════════════════════════════╗  ← accent colour bar (full width, 6px tall)
          ║                              ║
          ║  (content placed by caller)  ║  ← rounded card body
          ║                              ║
          ╚══════════════════════════════╝
        """
        _fill = fill_rgb or theme_config.get('color_card', theme_config['color_primary'])
        _acc  = accent_rgb or theme_config['color_accent']
        _bord = border_rgb or theme_config.get('color_card_border')

        # ── 1. Card body (rounded rectangle with shadow) ─────────────────
        card = slide.shapes.add_shape(1, left, top, width, height)
        card.fill.solid()
        card.fill.fore_color.rgb = RGBColor(*_fill)
        if _bord:
            card.line.color.rgb = RGBColor(*_bord)
            card.line.width = Pt(0.5)
        else:
            card.line.fill.background()
        _make_rounded(card, adj=12000)   # ~13% radius — clean modern look
        _add_shadow(card, blur=60000, dist=20000, alpha=11000)

        # ── 2. Top accent bar (full-width colour strip) ──────────────────
        bar_h = Inches(0.075)            # ~5.4pt tall accent bar
        bar = slide.shapes.add_shape(1, left, top, width, bar_h)
        bar.fill.solid()
        bar.fill.fore_color.rgb = RGBColor(*_acc)
        bar.line.fill.background()
        _make_rounded(bar, adj=12000)    # match card corner radius

        return card

    # ── BADGE / ICON CIRCLE HELPER ─────────────────────────────────────────
    def _add_number_badge(slide, cx, cy, radius, number, fill_rgb=None):
        """Add a circular number badge (used in agenda, timeline, metrics)."""
        _fill = fill_rgb or theme_config['color_accent']
        left = int(cx - radius)
        top  = int(cy - radius)
        size = int(radius * 2)
        circ = slide.shapes.add_shape(9, left, top, size, size)   # 9 = oval
        circ.fill.solid()
        circ.fill.fore_color.rgb = RGBColor(*_fill)
        circ.line.fill.background()
        tf = circ.text_frame
        tf.word_wrap = False
        p = tf.paragraphs[0]
        p.text = str(number)
        p.alignment = PP_ALIGN.CENTER
        p.font.bold = True
        p.font.size = Pt(max(10, int(size / 60000 * 1.4)))   # scale with badge size
        p.font.color.rgb = RGBColor(255, 255, 255)
        p.font.name = font_heading
        return circ


    slide = prs.slides.add_slide(prs.slide_layouts[6]); apply_bg(slide)
    txBox = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(8), Inches(2))
    tf = txBox.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.text = title.upper()
    p.font.bold = True; p.font.size = Pt(48); p.font.color.rgb = title_color; p.font.name = font_heading
    p.alignment = PP_ALIGN.CENTER
    line = slide.shapes.add_shape(9, Inches(4), Inches(4.5), Inches(2), Pt(2)) 
    line.line.color.rgb = accent_color; line.line.width = Pt(4)

    for s in slides_data:
        stype = s.get('type', 'content')
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        apply_bg(slide)
        
        # Section slides have different layout (no header/line)
        if stype == 'section':
            section_text = s.get('content', 'Section')
            section_box = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(8), Inches(3))
            stf = section_box.text_frame; stf.word_wrap = True
            p = stf.paragraphs[0]
            p.text = section_text.upper()
            p.font.bold = True; p.font.size = Pt(48); p.font.color.rgb = accent_color; p.alignment = PP_ALIGN.CENTER; p.font.name = font_heading
            # Add decorative border
            border = slide.shapes.add_shape(9, Inches(2), Inches(3.8), Inches(6), Pt(3))
            border.line.color.rgb = accent_color; border.line.width = Pt(4)
            continue  # Skip standard layout handling
        
        # Standard layout (header + line) for non-section slides
        header_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(9), Inches(1))
        hp = header_box.text_frame.paragraphs[0]
        hp.text = str(s.get('title', '')).upper()
        hp.font.bold = True; hp.font.size = Pt(32); hp.font.color.rgb = title_color; hp.font.name = font_heading
        
        line = slide.shapes.add_shape(9, Inches(0.5), Inches(1.2), Inches(2), Pt(2))
        line.line.color.rgb = accent_color; line.line.width = Pt(3)
        
        if stype == 'chart':
            chart_data_obj = CategoryChartData()
            cdata = s.get('chart_data', {})
            if isinstance(cdata, str):
                try: cdata = json.loads(cdata)
                except: cdata = {"Data": 10}
            
            if not cdata: cdata = {"No Data": 0} # Prevent crash
            
            chart_data_obj.categories = list(cdata.keys())
            chart_data_obj.add_series('Metrics', list(cdata.values()))
            
            ctype = s.get('chart_type', 'bar').lower()
            if ctype == 'pie': chart_type = XL_CHART_TYPE.PIE
            elif ctype == 'line': chart_type = XL_CHART_TYPE.LINE
            else: chart_type = XL_CHART_TYPE.COLUMN_CLUSTERED
            
            try: 
                chart_shape = slide.shapes.add_chart(chart_type, Inches(1.5), Inches(2.0), Inches(7), Inches(4.5), chart_data_obj)
                chart = chart_shape.chart
                
                # Set chart title
                chart.has_title = True
                chart.chart_title.text_frame.text = s.get('title', 'Chart')
                chart.chart_title.text_frame.paragraphs[0].font.size = Pt(18)
                chart.chart_title.text_frame.paragraphs[0].font.color.rgb = title_color
                chart.chart_title.text_frame.paragraphs[0].font.name = font_heading
                
                # Set series fill color
                series = chart.plots[0].series[0]
                series.format.fill.solid()
                series.format.fill.fore_color.rgb = accent_color
                
                # Legend: only enable for multi-series charts (currently single-series only)
                chart.has_legend = False
                
                # Set axis label colors for legibility on dark themes
                if theme in ['cyberpunk', 'modern_dark']:
                    # Dark backgrounds need light axis labels
                    for axis in [chart.category_axis, chart.value_axis]:
                        if hasattr(axis, 'format'):
                            axis.format.line.color.rgb = text_color
                        if hasattr(axis, 'tick_labels'):
                            axis.tick_labels.font.color.rgb = text_color
            except Exception as e:
                # Fallback print error on slide
                slide.shapes.add_textbox(Inches(2), Inches(3), Inches(6), Inches(1)).text_frame.text = f"[Chart generation error: {e}]"
                
        elif stype == 'image':
            img_path = s.get('image_path', '')
            
            # Auto-search for image if enabled and no path provided
            if auto_images and not img_path:
                image_url = get_image_for_slide(s)
                if image_url:
                    # Download image to local cache
                    cache_key = hashlib.md5(image_url.encode()).hexdigest()
                    img_path = os.path.join(cache_dir, f"{cache_key}.jpg")
                    if not os.path.exists(img_path):
                        if not download_image(image_url, img_path):
                            # Fallback to SVG if download fails
                            img_path = os.path.join(cache_dir, f"{cache_key}.png")
                            _acc = theme_config['color_accent']
                            generate_svg_fallback(img_path, f"#{_acc[0]:02X}{_acc[1]:02X}{_acc[2]:02X}")
            
            if img_path:
                try:
                    # Calculate proper dimensions to fit in frame
                    img_width, img_height = calculate_image_dimensions(img_path)
                    # Insert image with calculated dimensions (centered horizontally)
                    slide.shapes.add_picture(img_path, Inches(1), Inches(1.8), width=img_width, height=img_height)
                except:
                    slide.shapes.add_textbox(Inches(2), Inches(3), Inches(6), Inches(1)).text_frame.text = f"[Image failed to load: {img_path}]"
            else:
                slide.shapes.add_textbox(Inches(2), Inches(3), Inches(6), Inches(1)).text_frame.text = "[No image available]"
                
        elif stype == 'two_column':
            left_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(4.2), Inches(5))
            lp = left_box.text_frame.paragraphs[0]; left_box.text_frame.word_wrap = True
            lp.text = _strip_markdown(str(s.get('content_left', ''))); lp.font.size = Pt(18); lp.font.color.rgb = text_color; lp.font.name = font_body
            
            right_box = slide.shapes.add_textbox(Inches(5.0), Inches(1.8), Inches(4.2), Inches(5))
            rp = right_box.text_frame.paragraphs[0]; right_box.text_frame.word_wrap = True
            rp.text = _strip_markdown(str(s.get('content_right', ''))); rp.font.size = Pt(18); rp.font.color.rgb = text_color; rp.font.name = font_body
            
        elif stype == 'quote':
            # ── Large decorative quote with accent bar and author tag ──────
            # Decorative giant quotation mark
            qdec = slide.shapes.add_textbox(Inches(0.6), Inches(1.7), Inches(1.5), Inches(1.5))
            qp = qdec.text_frame.paragraphs[0]
            qp.text = '\u201c'
            qp.font.size = Pt(120); qp.font.color.rgb = accent_color; qp.font.name = font_heading
            # Quote card
            _add_card(slide, Inches(1.2), Inches(2.0), Inches(7.6), Inches(3.2))
            q_box = slide.shapes.add_textbox(Inches(1.45), Inches(2.22), Inches(7.1), Inches(2.72))
            qp2 = q_box.text_frame.paragraphs[0]; q_box.text_frame.word_wrap = True
            qp2.text = _strip_markdown(str(s.get('content', '')))
            qp2.font.italic = True; qp2.font.size = Pt(28); qp2.font.color.rgb = text_color
            qp2.alignment = PP_ALIGN.LEFT; qp2.font.name = font_body
            author = s.get('author', '')
            if author:
                ap = q_box.text_frame.add_paragraph()
                ap.text = f'— {author}'; ap.font.italic = False; ap.font.size = Pt(18)
                ap.font.color.rgb = accent_color; ap.alignment = PP_ALIGN.RIGHT; ap.font.name = font_heading

        # ── NEW LAYOUT: title_slide ────────────────────────────────────────
        elif stype == 'title_slide':
            # Full-bleed opening slide: big title + subtitle + author
            # Top accent bar
            top_bar = slide.shapes.add_shape(1, Inches(0), Inches(0), Inches(10), Inches(0.12))
            top_bar.fill.solid(); top_bar.fill.fore_color.rgb = accent_color; top_bar.line.fill.background()
            # Center title
            title_box = slide.shapes.add_textbox(Inches(1.0), Inches(2.0), Inches(8.0), Inches(2.0))
            tp = title_box.text_frame.paragraphs[0]; title_box.text_frame.word_wrap = True
            tp.text = str(s.get('title', ''))
            tp.font.bold = True; tp.font.size = Pt(52); tp.font.color.rgb = title_color
            tp.alignment = PP_ALIGN.CENTER; tp.font.name = font_heading
            # Subtitle
            sub = s.get('subtitle', '')
            if sub:
                sub_box = slide.shapes.add_textbox(Inches(1.5), Inches(4.1), Inches(7.0), Inches(0.8))
                sp = sub_box.text_frame.paragraphs[0]
                sp.text = sub; sp.font.size = Pt(26); sp.font.color.rgb = accent_color
                sp.alignment = PP_ALIGN.CENTER; sp.font.name = font_body
            # Author / date
            author = s.get('author', '')
            if author:
                a_box = slide.shapes.add_textbox(Inches(1.5), Inches(5.1), Inches(7.0), Inches(0.6))
                a_p = a_box.text_frame.paragraphs[0]
                a_p.text = author; a_p.font.size = Pt(18); a_p.font.color.rgb = text_color
                a_p.alignment = PP_ALIGN.CENTER; a_p.font.name = font_body
            # Bottom accent line
            bot_bar = slide.shapes.add_shape(1, Inches(0), Inches(7.38), Inches(10), Inches(0.12))
            bot_bar.fill.solid(); bot_bar.fill.fore_color.rgb = accent_color; bot_bar.line.fill.background()
            continue  # already has no standard header

        # ── NEW LAYOUT: metrics (KPI dashboard) ────────────────────────────
        elif stype == 'metrics':
            # metrics: list of dicts [{value, label, sublabel?}]
            # Displays 2-4 big-number cards side by side — Gamma-style KPI board
            raw_metrics = s.get('metrics', [])
            if isinstance(raw_metrics, str):
                try: raw_metrics = json.loads(raw_metrics)
                except: raw_metrics = [{'value': raw_metrics, 'label': ''}]
            if not raw_metrics:
                raw_metrics = [{'value': '—', 'label': 'No data'}]

            count = min(len(raw_metrics), 4)
            card_w = Inches((9.0 - (count - 1) * 0.25) / count)
            card_h = Inches(3.5)
            top_y  = Inches(1.9)

            for idx, metric in enumerate(raw_metrics[:count]):
                card_left = Inches(0.5 + idx * (card_w.inches + 0.25))
                _add_card(slide, card_left, top_y, card_w, card_h)
                # Big value text
                val_box = slide.shapes.add_textbox(
                    card_left + Inches(0.15), top_y + Inches(0.45), card_w - Inches(0.25), Inches(1.7))
                vp = val_box.text_frame.paragraphs[0]
                vp.text = str(metric.get('value', ''))
                vp.font.bold = True; vp.font.size = Pt(42); vp.font.color.rgb = accent_color
                vp.alignment = PP_ALIGN.CENTER; vp.font.name = font_heading
                # Label text
                lbl_box = slide.shapes.add_textbox(
                    card_left + Inches(0.15), top_y + Inches(2.22), card_w - Inches(0.25), Inches(0.9))
                lp2 = lbl_box.text_frame.paragraphs[0]; lbl_box.text_frame.word_wrap = True
                lp2.text = str(metric.get('label', ''))
                lp2.font.size = Pt(16); lp2.font.color.rgb = text_color
                lp2.alignment = PP_ALIGN.CENTER; lp2.font.name = font_body
                # Optional sublabel
                sub2 = metric.get('sublabel', '')
                if sub2:
                    sl_box = slide.shapes.add_textbox(
                        card_left + Inches(0.15), top_y + Inches(2.8), card_w - Inches(0.25), Inches(0.55))
                    slp = sl_box.text_frame.paragraphs[0]
                    slp.text = sub2; slp.font.size = Pt(12); slp.font.color.rgb = text_color
                    slp.alignment = PP_ALIGN.CENTER; slp.font.name = font_body

        # ── NEW LAYOUT: timeline ───────────────────────────────────────────
        elif stype == 'timeline':
            # steps: list of strings or [{label, description?}]
            steps = s.get('steps', [])
            if isinstance(steps, str):
                try: steps = json.loads(steps)
                except: steps = [steps]
            steps = steps[:6]  # max 6 steps for readability
            if not steps:
                steps = ['Start', 'End']

            count  = len(steps)
            line_y = Inches(3.6)   # horizontal centre line Y
            x_step = Inches(9.0 / (count + 1))
            dot_r  = Inches(0.22)

            # Draw horizontal connector line
            conn = slide.shapes.add_shape(1, Inches(0.5), line_y - Inches(0.03), Inches(9.0), Inches(0.06))
            conn.fill.solid(); conn.fill.fore_color.rgb = accent_color; conn.line.fill.background()

            for idx, step in enumerate(steps):
                lbl  = step if isinstance(step, str) else step.get('label', str(step))
                desc = '' if isinstance(step, str) else step.get('description', '')
                cx = Inches(0.5) + x_step * (idx + 1)
                cy = line_y

                # Circle dot
                circ = slide.shapes.add_shape(9, int(cx - dot_r), int(cy - dot_r), int(dot_r * 2), int(dot_r * 2))
                circ.fill.solid(); circ.fill.fore_color.rgb = accent_color; circ.line.fill.background()
                # Step number inside dot
                num_box = slide.shapes.add_textbox(int(cx - dot_r), int(cy - dot_r), int(dot_r * 2), int(dot_r * 2))
                np2 = num_box.text_frame.paragraphs[0]
                np2.text = str(idx + 1); np2.font.size = Pt(12); np2.font.bold = True
                np2.font.color.rgb = RGBColor(255, 255, 255); np2.alignment = PP_ALIGN.CENTER; np2.font.name = font_heading

                # Label above or below alternating (prevents overlap)
                if idx % 2 == 0:
                    lbl_y = line_y - Inches(1.4)
                else:
                    lbl_y = line_y + Inches(0.6)
                lbl_box = slide.shapes.add_textbox(int(cx - x_step * 0.45), int(lbl_y), int(x_step * 0.9), Inches(0.9))
                lbl_box.text_frame.word_wrap = True
                lp3 = lbl_box.text_frame.paragraphs[0]
                lp3.text = _strip_markdown(lbl); lp3.font.size = Pt(14); lp3.font.bold = True
                lp3.font.color.rgb = text_color; lp3.alignment = PP_ALIGN.CENTER; lp3.font.name = font_heading
                if desc:
                    dp = lbl_box.text_frame.add_paragraph()
                    dp.text = _strip_markdown(desc); dp.font.size = Pt(11); dp.font.bold = False
                    dp.font.color.rgb = text_color; dp.alignment = PP_ALIGN.CENTER; dp.font.name = font_body

        # ── NEW LAYOUT: comparison ─────────────────────────────────────────
        elif stype == 'comparison':
            # Two side-by-side columns with distinct header bars — VS layout
            left_title   = str(s.get('left_title', 'Option A'))
            right_title  = str(s.get('right_title', 'Option B'))
            left_content = str(s.get('content_left', s.get('left_content', '')))
            right_content= str(s.get('content_right', s.get('right_content', '')))

            col_w = Inches(4.0)
            col_h = Inches(4.4)
            col_t = Inches(1.85)
            gap   = Inches(0.5)
            l_x   = Inches(0.5)
            r_x   = Inches(5.5)

            # Left card
            _add_card(slide, l_x, col_t, col_w, col_h)
            # Left header bar
            lh = slide.shapes.add_shape(1, l_x, col_t, col_w, Inches(0.55))
            lh.fill.solid(); lh.fill.fore_color.rgb = accent_color; lh.line.fill.background()
            lh_txt = slide.shapes.add_textbox(l_x + Inches(0.2), col_t + Inches(0.05), col_w - Inches(0.25), Inches(0.45))
            lhp = lh_txt.text_frame.paragraphs[0]
            lhp.text = left_title; lhp.font.bold = True; lhp.font.size = Pt(20)
            lhp.font.color.rgb = RGBColor(255, 255, 255); lhp.font.name = font_heading

            # Left content
            l_body = slide.shapes.add_textbox(l_x + Inches(0.2), col_t + Inches(0.65), col_w - Inches(0.3), col_h - Inches(0.8))
            l_body.text_frame.word_wrap = True
            for i, line in enumerate(left_content.split('\n')):
                p2 = l_body.text_frame.paragraphs[0] if i == 0 else l_body.text_frame.add_paragraph()
                p2.text = _strip_markdown(line.strip('- ').strip('* '))
                p2.font.size = Pt(16); p2.font.color.rgb = text_color; p2.font.name = font_body
                if line.startswith('- ') or line.startswith('* '): p2.level = 1

            # Right card
            _add_card(slide, r_x, col_t, col_w, col_h)
            # Right header bar (slightly different shade — 80% of accent)
            acc2 = tuple(max(0, min(255, int(c * 0.75))) for c in theme_config['color_accent'])
            rh = slide.shapes.add_shape(1, r_x, col_t, col_w, Inches(0.55))
            rh.fill.solid(); rh.fill.fore_color.rgb = RGBColor(*acc2); rh.line.fill.background()
            rh_txt = slide.shapes.add_textbox(r_x + Inches(0.2), col_t + Inches(0.05), col_w - Inches(0.25), Inches(0.45))
            rhp = rh_txt.text_frame.paragraphs[0]
            rhp.text = right_title; rhp.font.bold = True; rhp.font.size = Pt(20)
            rhp.font.color.rgb = RGBColor(255, 255, 255); rhp.font.name = font_heading

            # Right content
            r_body = slide.shapes.add_textbox(r_x + Inches(0.2), col_t + Inches(0.65), col_w - Inches(0.3), col_h - Inches(0.8))
            r_body.text_frame.word_wrap = True
            for i, line in enumerate(right_content.split('\n')):
                p2 = r_body.text_frame.paragraphs[0] if i == 0 else r_body.text_frame.add_paragraph()
                p2.text = _strip_markdown(line.strip('- ').strip('* '))
                p2.font.size = Pt(16); p2.font.color.rgb = text_color; p2.font.name = font_body
                if line.startswith('- ') or line.startswith('* '): p2.level = 1

            # VS badge in centre
            vs_cx = int(Inches(5.0))
            vs_cy = int(col_t + col_h / 2)
            vs_r  = int(Inches(0.38))
            vs_circ = slide.shapes.add_shape(9, vs_cx - vs_r, vs_cy - vs_r, vs_r * 2, vs_r * 2)
            vs_circ.fill.solid(); vs_circ.fill.fore_color.rgb = accent_color; vs_circ.line.fill.background()
            vs_txt = slide.shapes.add_textbox(vs_cx - vs_r, vs_cy - vs_r, vs_r * 2, vs_r * 2)
            vsp = vs_txt.text_frame.paragraphs[0]
            vsp.text = 'VS'; vsp.font.bold = True; vsp.font.size = Pt(14)
            vsp.font.color.rgb = RGBColor(255, 255, 255); vsp.alignment = PP_ALIGN.CENTER; vsp.font.name = font_heading

        # ── NEW LAYOUT: agenda ─────────────────────────────────────────────
        elif stype == 'agenda':
            # Numbered list — large accent numbers + item text, card per row
            items = s.get('items', s.get('content', '').split('\n'))
            if isinstance(items, str):
                items = [ln.strip() for ln in items.split('\n') if ln.strip()]
            items = [i for i in items if i][:8]

            row_h   = Inches(0.62)
            start_y = Inches(1.75)
            gap     = Inches(0.1)

            for idx, item in enumerate(items):
                row_top = start_y + (row_h + gap) * idx
                # Card background for this row
                _add_card(slide, Inches(0.5), row_top, Inches(9.0), row_h)
                # Accent number badge
                badge_cx = int(Inches(1.1))
                badge_cy = int(row_top + row_h / 2)
                badge_r  = int(row_h * 0.38)
                badge = slide.shapes.add_shape(9, badge_cx - badge_r, badge_cy - badge_r, badge_r * 2, badge_r * 2)
                badge.fill.solid(); badge.fill.fore_color.rgb = accent_color; badge.line.fill.background()
                badge_lbl = slide.shapes.add_textbox(badge_cx - badge_r, badge_cy - badge_r, badge_r * 2, badge_r * 2)
                bp = badge_lbl.text_frame.paragraphs[0]
                bp.text = str(idx + 1); bp.font.bold = True; bp.font.size = Pt(16)
                bp.font.color.rgb = RGBColor(255, 255, 255); bp.alignment = PP_ALIGN.CENTER; bp.font.name = font_heading
                # Item text
                item_box = slide.shapes.add_textbox(Inches(1.65), int(row_top + Inches(0.17)), Inches(7.6), row_h - Inches(0.22))
                item_box.text_frame.word_wrap = False
                ip = item_box.text_frame.paragraphs[0]
                ip.text = _strip_markdown(str(item).strip('- ').strip('* '))
                ip.font.size = Pt(18); ip.font.color.rgb = text_color; ip.font.name = font_body

        else:  # ── DEFAULT: content (card-backed text) ────────────────────
            # Card behind main content area
            _add_card(slide, Inches(0.4), Inches(1.75), Inches(9.2), Inches(5.15))
            body_box = slide.shapes.add_textbox(Inches(0.62), Inches(1.98), Inches(8.85), Inches(4.75))
            btf = body_box.text_frame; btf.word_wrap = True
            lines = str(s.get('content', '')).split('\n')

            # Auto-shrink font for very long content
            char_total = sum(len(l) for l in lines)
            font_size = Pt(20)
            if char_total > 600: font_size = Pt(16)
            if char_total > 900: font_size = Pt(14)
            if char_total > 1200: font_size = Pt(12)

            for i, line in enumerate(lines):
                p = btf.paragraphs[0] if i == 0 else btf.add_paragraph()
                p.text = _strip_markdown(line.strip('- ').strip('* '))
                p.font.size = font_size; p.font.color.rgb = text_color; p.font.name = font_body
                if line.startswith('- ') or line.startswith('* '): p.level = 1


    prs.save(path)

    # Clear image cache after successful PPTX creation so stale files don't accumulate
    try:
        import shutil
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
            os.makedirs(cache_dir, exist_ok=True)
    except Exception as _cache_err:
        pass  # Cache clear failure is non-fatal

    return f"Successfully created PowerPoint (PPTX) at {path}"

def main():
    try:
        input_data = sys.stdin.read()
        if not input_data:
            print("Error: No input data provided via stdin.")
            sys.exit(1)
        req = json.loads(input_data)
        action = req.get("action"); kwargs = req.get("kwargs", {})
        actions = {
            "read_csv": read_csv, "create_csv": create_csv, "read_excel": read_excel, "create_excel": create_excel, "modify_excel": modify_excel,
            "read_pdf": read_pdf, "create_pdf": create_pdf, "create_doc": create_doc, "create_ppt": create_ppt
        }
        if action not in actions:
            print(f"Error: Unknown action '{action}'")
            sys.exit(1)
        print(actions[action](kwargs))
    except Exception as e:
        print(f"Error executing document tool: {str(e)}\n{traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
