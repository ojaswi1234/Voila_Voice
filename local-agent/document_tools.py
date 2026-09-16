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

    latex_content = kwargs.get('latex')
    if latex_content:
        # Auto-inject theme colors and better formatting into LaTeX preamble
        color_defs = """
\\usepackage{xcolor}
\\usepackage{titlesec}
\\usepackage{geometry}
\\geometry{a4paper, margin=1in}
\\definecolor{themePrimary}{RGB}{theme_config['color_primary'][0], theme_config['color_primary'][1], theme_config['color_primary'][2]}
\\definecolor{themeAccent}{RGB}{theme_config['color_accent'][0], theme_config['color_accent'][1], theme_config['color_accent'][2]}
\\definecolor{themeHeading}{RGB}{theme_config['color_heading'][0], theme_config['color_heading'][1], theme_config['color_heading'][2]}
\\definecolor{themeText}{RGB}{theme_config['color_text'][0], theme_config['color_text'][1], theme_config['color_text'][2]}
\\pagecolor{themePrimary}
\\color{themeText}
\\titleformat{\\section}{\\normalfont\\Large\\bfseries\\color{themeHeading}}{\\thesection}{1em}{}[\\color{themeAccent}\\titlerule]
"""
        # Fix f-string brackets safely
        color_defs = color_defs.replace("theme_config['color_primary'][0]", str(theme_config['color_primary'][0]))
        color_defs = color_defs.replace("theme_config['color_primary'][1]", str(theme_config['color_primary'][1]))
        color_defs = color_defs.replace("theme_config['color_primary'][2]", str(theme_config['color_primary'][2]))
        color_defs = color_defs.replace("theme_config['color_accent'][0]", str(theme_config['color_accent'][0]))
        color_defs = color_defs.replace("theme_config['color_accent'][1]", str(theme_config['color_accent'][1]))
        color_defs = color_defs.replace("theme_config['color_accent'][2]", str(theme_config['color_accent'][2]))
        color_defs = color_defs.replace("theme_config['color_heading'][0]", str(theme_config['color_heading'][0]))
        color_defs = color_defs.replace("theme_config['color_heading'][1]", str(theme_config['color_heading'][1]))
        color_defs = color_defs.replace("theme_config['color_heading'][2]", str(theme_config['color_heading'][2]))
        color_defs = color_defs.replace("theme_config['color_text'][0]", str(theme_config['color_text'][0]))
        color_defs = color_defs.replace("theme_config['color_text'][1]", str(theme_config['color_text'][1]))
        color_defs = color_defs.replace("theme_config['color_text'][2]", str(theme_config['color_text'][2]))

        if '\\begin{document}' in latex_content and '\\definecolor{themePrimary}' not in latex_content:
            latex_content = latex_content.replace('\\begin{document}', color_defs + '\n\\begin{document}')
        
        import subprocess, tempfile, shutil, os
        temp_dir = tempfile.mkdtemp()
        tex_path = os.path.join(temp_dir, 'doc.tex')
        with open(tex_path, 'w', encoding='utf-8') as f:
            f.write(latex_content)
        try:
            result = subprocess.run(['pdflatex', '-interaction=nonstopmode', '-output-directory', temp_dir, tex_path], capture_output=True, text=True)
            pdf_path = os.path.join(temp_dir, 'doc.pdf')
            if os.path.exists(pdf_path):
                shutil.copy(pdf_path, path)
                shutil.rmtree(temp_dir, ignore_errors=True)
                return f"Successfully created beautifully formatted PDF via LaTeX at {path}"
            else:
                shutil.rmtree(temp_dir, ignore_errors=True)
                return f"LaTeX compilation failed (no PDF output). Output:\n{result.stdout[-1000:]}\n\nCRITICAL: Fix your LaTeX syntax and try again, or leave 'latex' blank and put the full document in Markdown format into the 'content' parameter to use the FPDF engine."
        except Exception as e:
            shutil.rmtree(temp_dir, ignore_errors=True)
            return f"Failed to run pdflatex (is MiKTeX/TeXLive installed?). Error: {str(e)}\n\nCRITICAL: LaTeX is NOT installed on this system! You MUST retry using the 'create_pdf' tool, but LEAVE 'latex' BLANK and put the ENTIRE exhaustive document (using Markdown) into the 'content' parameter so the FPDF fallback engine can render it!"

    
    doc = docx.Document()
    
    # Apply theme-based styles
    styles = doc.styles
    def ensure_dark(color):
        if sum(color) > 382: return (max(0, 255-color[0]-50), max(0, 255-color[1]-50), max(0, 255-color[2]-50))
        return color

    try:

        styles['Title'].font.name = theme_config['font_heading']
        styles['Title'].font.size = Pt(32)
        styles['Title'].font.color.rgb = RGBColor(*ensure_dark(theme_config['color_heading']))
        
        styles['Heading 1'].font.name = theme_config['font_heading']
        styles['Heading 1'].font.size = Pt(20)
        styles['Heading 1'].font.color.rgb = RGBColor(*ensure_dark(theme_config['color_accent']))
        
        styles['Normal'].font.name = theme_config['font_body']
        styles['Normal'].font.size = Pt(11)
        styles['Normal'].font.color.rgb = RGBColor(*ensure_dark(theme_config['color_text']))
    except: pass
    
    try:
        quote_style = styles.add_style('BlockQuote', docx.enum.style.WD_STYLE_TYPE.PARAGRAPH)
        quote_style.font.name = theme_config['font_body']
        quote_style.font.italic = True
        quote_style.font.size = Pt(12)
        quote_style.font.color.rgb = RGBColor(*ensure_dark(theme_config['color_text']))
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
            p.style.font.color.rgb = RGBColor(*ensure_dark(theme_config['color_primary']))
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
    from design_tokens import get_theme
    import markdown
    from playwright.sync_api import sync_playwright
    import os
    import tempfile
    
    path = kwargs.get('path')
    content = kwargs.get('content', '')
    watermark = kwargs.get('watermark', '')
    theme = kwargs.get('theme', 'modern_dark')
    theme_config = get_theme(theme)

    # Allow users to pass HTML directly, but fallback to rendering Markdown to HTML
    if '<html' in content.lower() or '<body' in content.lower():
        html_body = content
    else:
        # Convert Markdown to HTML (supporting tables and fenced code)
        html_body = markdown.markdown(content, extensions=['tables', 'fenced_code', 'sane_lists'])

    # CSS for the PDF (implementing the Playwright Print CSS Architecture)
    rgb_primary = f"{theme_config['color_primary'][0]}, {theme_config['color_primary'][1]}, {theme_config['color_primary'][2]}"
    rgb_accent = f"{theme_config['color_accent'][0]}, {theme_config['color_accent'][1]}, {theme_config['color_accent'][2]}"
    rgb_text = f"{theme_config['color_text'][0]}, {theme_config['color_text'][1]}, {theme_config['color_text'][2]}"
    rgb_heading = f"{theme_config['color_heading'][0]}, {theme_config['color_heading'][1]}, {theme_config['color_heading'][2]}"
    
    bg_color = f"rgb({rgb_primary})" if theme == 'modern_dark' else "#ffffff"
    text_color = f"rgb({rgb_text})"
    heading_color = f"rgb({rgb_heading})"
    accent_color = f"rgb({rgb_accent})"
    
    css = f"""
    @page {{
        size: A4;
        margin: 20mm;
    }}
    body {{
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        color: {text_color};
        background-color: {bg_color};
        line-height: 1.6;
        font-size: 11pt;
    }}
    h1, h2, h3, h4, h5, h6 {{
        color: {heading_color};
        font-family: 'Georgia', serif;
        page-break-after: avoid;
    }}
    h1 {{
        font-size: 24pt;
        border-bottom: 2px solid {accent_color};
        padding-bottom: 8px;
    }}
    h2 {{
        font-size: 18pt;
        color: {accent_color};
        margin-top: 1.5em;
    }}
    p {{
        margin-bottom: 1em;
    }}
    pre, code {{
        font-family: Consolas, Monaco, 'Andale Mono', 'Ubuntu Mono', monospace;
        background-color: rgba({rgb_text}, 0.05);
        border-radius: 4px;
    }}
    pre {{
        padding: 12px;
        page-break-inside: avoid;
        overflow-x: auto;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        margin: 20px 0;
        page-break-inside: avoid;
    }}
    th, td {{
        padding: 10px;
        border: 1px solid rgba({rgb_text}, 0.2);
        text-align: left;
    }}
    th {{
        background-color: {accent_color};
        color: #ffffff;
    }}
    tr:nth-child(even) {{
        background-color: rgba({rgb_text}, 0.02);
    }}
    img {{
        max-width: 100%;
        height: auto;
        border-radius: 6px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        page-break-inside: avoid;
    }}
    blockquote {{
        border-left: 4px solid {accent_color};
        margin: 0;
        padding-left: 16px;
        font-style: italic;
        color: rgba({rgb_text}, 0.8);
    }}
    .watermark {{
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%) rotate(-45deg);
        font-size: 80pt;
        color: rgba({rgb_text}, 0.05);
        z-index: -1000;
        pointer-events: none;
        white-space: nowrap;
    }}
    """

    watermark_html = f'<div class="watermark">{watermark}</div>' if watermark else ''

    full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <style>{css}</style>
</head>
<body>
    {watermark_html}
    {html_body}
</body>
</html>
"""

    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix='.html', mode='w', encoding='utf-8') as f:
            f.write(full_html)
            temp_html_path = f.name
            
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(f"file://{temp_html_path}", wait_until="networkidle")
            page.pdf(
                path=path,
                format="A4",
                print_background=True,
                margin={"top": "20mm", "bottom": "20mm", "left": "20mm", "right": "20mm"}
            )
            browser.close()
            
        os.unlink(temp_html_path)
        return f"Successfully created beautifully formatted PDF via Playwright HTML rendering at {path}"
    except Exception as e:
        return f"Failed to generate PDF via Playwright: {str(e)}"

# --- PPT CREATION ---
def create_ppt(kwargs):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.enum.text import PP_ALIGN
    from pptx.dml.color import RGBColor
    import os
    import json
    from design_tokens import get_theme
    from document_ir import normalize_ir, Slide
    
    path = kwargs.get('path', 'presentation.pptx')
    ir_data = kwargs.get('ir') or kwargs
    ir = normalize_ir(ir_data)
    theme_config = get_theme(ir.theme)
    
    prs = Presentation()
    # Simple blank slide layout
    blank_slide_layout = prs.slide_layouts[6]
    
    color_primary = RGBColor(*theme_config['color_primary'])
    color_accent = RGBColor(*theme_config['color_accent'])
    color_text = RGBColor(*theme_config['color_text'])
    color_heading = RGBColor(*theme_config['color_heading'])

    if not ir.slides and ir.document and ir.document.sections:
        for sec in ir.document.sections:
            if sec.type == 'heading':
                ir.slides.append(Slide(master='title_slide', title=sec.text))
            elif sec.type == 'table' or sec.type == 'stat_row':
                stats = []
                if sec.type == 'stat_row':
                    stats = sec.items
                ir.slides.append(Slide(master='stats', title=sec.title or 'Stats', stats=stats))
            elif sec.type == 'prose' or sec.type == 'bullets':
                ir.slides.append(Slide(master='content', title=sec.title or 'Content', content=sec.body, items=sec.items))

    
    for slide_data in ir.slides:
        slide = prs.slides.add_slide(blank_slide_layout)
        
        # Background
        bg = slide.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
        bg.fill.solid()
        bg.fill.fore_color.rgb = color_primary
        bg.line.fill.background()
        
        master = slide_data.master
        
        if master == 'title_slide':
            title_box = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(1))
            tf = title_box.text_frame
            tf.text = slide_data.title
            tf.paragraphs[0].font.size = Pt(44)
            tf.paragraphs[0].font.color.rgb = color_heading
            
            sub_box = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(8), Inches(1))
            stf = sub_box.text_frame
            stf.text = slide_data.subtitle
            stf.paragraphs[0].font.size = Pt(24)
            stf.paragraphs[0].font.color.rgb = color_accent
            
        elif master == 'stat_grid' or master == 'stats':
            title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(1))
            tf = title_box.text_frame
            tf.text = slide_data.title
            tf.paragraphs[0].font.size = Pt(32)
            tf.paragraphs[0].font.color.rgb = color_heading
            
            stats = slide_data.stats
            for i, stat in enumerate(stats):
                x = Inches(0.5 + (i * 3))
                y = Inches(2)
                card = slide.shapes.add_shape(1, x, y, Inches(2.5), Inches(1.5))
                card.fill.solid()
                card.fill.fore_color.rgb = RGBColor(*theme_config['color_card'])
                
                label_box = slide.shapes.add_textbox(x, y, Inches(2.5), Inches(0.5))
                label_box.text_frame.text = stat.get('label', '')
                label_box.text_frame.paragraphs[0].font.color.rgb = color_accent
                
                val_box = slide.shapes.add_textbox(x, y + Inches(0.5), Inches(2.5), Inches(1))
                val_box.text_frame.text = str(stat.get('value', ''))
                val_box.text_frame.paragraphs[0].font.size = Pt(32)
                val_box.text_frame.paragraphs[0].font.color.rgb = color_heading
                
        elif master == 'chart':
            title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(1))
            tf = title_box.text_frame
            tf.text = slide_data.title
            tf.paragraphs[0].font.size = Pt(32)
            tf.paragraphs[0].font.color.rgb = color_heading
            
            # Use a table as a mock chart since pptx charts require extra imports and data shaping
            # but for PPTX text extraction, standard shapes work
            body = slide.shapes.add_textbox(Inches(0.5), Inches(2), Inches(9), Inches(3))
            body.text_frame.text = json.dumps(slide_data.chart_data)
            
        else: # content / agenda
            title_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(1))
            tf = title_box.text_frame
            tf.text = slide_data.title
            tf.paragraphs[0].font.size = Pt(32)
            tf.paragraphs[0].font.color.rgb = color_heading
            
            body = slide.shapes.add_textbox(Inches(0.5), Inches(1.5), Inches(9), Inches(5))
            if slide_data.items:
                body.text_frame.text = "\n".join(slide_data.items)
            elif slide_data.content:
                body.text_frame.text = slide_data.content
            body.text_frame.paragraphs[0].font.color.rgb = color_text

    prs.save(path)
    return f"Successfully created PowerPoint (PPTX) at {path}"

def create_docx(kwargs):
    from docx import Document
    from docx.shared import Pt, RGBColor
    import os
    from design_tokens import get_theme
    from document_ir import normalize_ir, Slide
    
    path = kwargs.get('path', 'document.docx')
    ir_data = kwargs.get('ir') or kwargs
    ir = normalize_ir(ir_data)
    theme_config = get_theme(ir.theme)
    
    doc = Document()
    
    title = doc.add_heading(ir.meta.title, 0)
    
    for sec in ir.document.sections:
        if sec.type == 'heading':
            doc.add_heading(sec.text, level=sec.level or 1)
        elif sec.type == 'prose':
            if sec.title:
                doc.add_heading(sec.title, level=2)
            doc.add_paragraph(sec.body)
        elif sec.type == 'table':
            if sec.title:
                doc.add_heading(sec.title, level=2)
            table = doc.add_table(rows=1, cols=len(sec.columns))
            hdr_cells = table.rows[0].cells
            for i, col in enumerate(sec.columns):
                hdr_cells[i].text = str(col)
            for row in sec.rows:
                row_cells = table.add_row().cells
                for i, cell in enumerate(row):
                    if i < len(row_cells):
                        row_cells[i].text = str(cell)
        elif sec.type == 'stat_row':
            p = doc.add_paragraph()
            for item in sec.items:
                p.add_run(f"{item.get('label', '')}: ").bold = True
                p.add_run(f"{item.get('value', '')}   ")
        elif sec.type == 'bullets':
            for item in sec.items:
                doc.add_paragraph(str(item), style='List Bullet')
                
    doc.save(path)
    return f"Successfully created Word Document (DOCX) at {path}"


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
            "read_pdf": read_pdf, "create_pdf": create_pdf, "create_doc": create_doc, "create_ppt": create_ppt, "create_docx": create_docx
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
