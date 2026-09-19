"""
================================================================================
Voila Voice CLI - Document Engineering Pipeline
================================================================================
This script handles the heavy lifting for generating beautiful PDFs, Word Docs,
and parsing structured data (CSV/Excel).
Responsibilities:
1. PDF Rendering (`create_pdf`): Uses Headless Chromium (Playwright) to render 
   Markdown + HTML + inline SVG into beautifully themed PDFs.
2. DOCX Generation (`create_docx`): Uses python-docx to generate corporate documents.
3. Data Handling: Reads and writes Excel/CSV files for data analysis tasks.
================================================================================
"""
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
    
    # Clean up AI LaTeX math hallucinations
    if content:
        content = content.replace('$\\rightarrow$', '→')
        content = content.replace('$\\Rightarrow$', '⇒')
        content = content.replace('$\\leftarrow$', '←')
        content = content.replace('$\\Leftarrow$', '⇐')
        content = content.replace('\\rightarrow', '→')
        content = content.replace('\\Rightarrow', '⇒')
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
    json_ir = kwargs.get('json', None)
    
    if json_ir:
        try:
            import json
            from jinja2 import Environment, FileSystemLoader
            from document_ir import normalize_ir
            from diagram_render import render_mermaid_to_png, svg_file_to_png
            
            ir = normalize_ir(json_ir)
            
            # QUALITY GATE: Ensure document has actual substance
            total_text = sum(len(sec.body or '') + len(sec.text or '') for sec in ir.document.sections if sec.type in ('text', 'prose', 'markdown'))
            has_tables = any(sec.type == 'table' for sec in ir.document.sections)
            has_images = any(sec.type in ('diagram', 'image') for sec in ir.document.sections)
            
            if total_text < 150 and not has_tables and not has_images:
                return "ERROR: Document quality gate failed. The document has negligible body text and no tables or diagrams. Do not return an empty or title-only PDF. Retry by including detailed body text, tables of findings, or mermaid diagrams in the sections."

            # Normalize diagrams and parse markdown to HTML
            has_diagrams = False
            for sec in ir.document.sections:
                if sec.type in ('prose', 'text', 'markdown'):
                    # Convert minimal markdown (**bold**, lists) to HTML
                    if sec.body and '<' not in sec.body:
                        sec.body = markdown.markdown(sec.body, extensions=['sane_lists'])
                    if sec.text and '<' not in sec.text:
                        sec.text = markdown.markdown(sec.text, extensions=['sane_lists'])
                elif sec.type == 'diagram':
                    has_diagrams = True
                    if sec.engine == 'mermaid':
                        sec.image_path = render_mermaid_to_png(sec.source, theme=sec.theme or 'default', background=sec.background or 'transparent')
                    elif sec.engine == 'svg' and sec.source.endswith('.svg'):
                        sec.image_path = svg_file_to_png(sec.source)
            
            # Render Jinja
            env = Environment(loader=FileSystemLoader(os.path.join(os.path.dirname(__file__), 'templates', 'report')))
            template = env.get_template('layout.html')
            html_out = template.render(ir=ir)
            
            fd, temp_html = tempfile.mkstemp(suffix=".html")
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(html_out)
                
            if has_diagrams:
                # Use Playwright for blended backgrounds
                with sync_playwright() as p:
                    browser = p.chromium.launch(headless=True)
                    page = browser.new_page()
                    page.goto(f"file:///{temp_html}", wait_until="load")
                    page.pdf(path=path, format="A4", print_background=True)
                    browser.close()
            else:
                # Use WeasyPrint for static themed docs
                try:
                    from weasyprint import HTML
                    base_url = os.path.dirname(os.path.abspath(__file__))
                    HTML(filename=temp_html, base_url=base_url).write_pdf(path)
                except ImportError:
                    # Fallback if weasyprint not installed
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        page = browser.new_page()
                        page.goto(f"file:///{temp_html}", wait_until="load")
                        page.pdf(path=path, format="A4", print_background=True)
                        browser.close()
                        
            os.remove(temp_html)
            return f"Successfully created PDF using Design IR at {path}"
        except Exception as e:
            return f"Error using Design IR: {e}"
            
    content = kwargs.get('content', '')
    source_files = kwargs.get('source_files', [])
    
    # QUALITY GATE for standard fallback
    if len(content) < 150 and not source_files:
        return "ERROR: Document quality gate failed. The content provided is too short. Do not return an empty PDF. Retry by including detailed body text, tables, or sections."
    
    # Clean up AI LaTeX math hallucinations
    if content:
        content = content.replace('$\\rightarrow$', '→')
        content = content.replace('$\\Rightarrow$', '⇒')
        content = content.replace('$\\leftarrow$', '←')
        content = content.replace('$\\Leftarrow$', '⇐')
        content = content.replace('\\rightarrow', '→')
        content = content.replace('\\Rightarrow', '⇒')
        
    watermark = kwargs.get('watermark', '')

    # If source_files are provided, read and concatenate them (for massive 40-page PDFs)
    if source_files:
        combined_content = []
        for file_path in source_files:
            try:
                with open(file_path, 'r', encoding='utf-8') as sf:
                    combined_content.append(sf.read())
                # Clean up the temp file after reading
                os.remove(file_path)
            except Exception as e:
                combined_content.append(f"<!-- Error reading {file_path}: {e} -->")
        
        # Join with page breaks between files
        content = "\n\n<div class='page-break'></div>\n\n".join(combined_content) + "\n\n" + content

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
    # Provide accurate background colors for light themes too
    if theme in ['notebooklm', 'handwritten', 'sketching', 'origami', 'warm_sunset', 'illustrated_light']:
        bg_color = f"rgb({rgb_primary})"
    if theme in ['pixelated', 'asciiart']:
        bg_color = f"rgb({rgb_primary})"
        
    text_color = f"rgb({rgb_text})"
    heading_color = f"rgb({rgb_heading})"
    accent_color = f"rgb({rgb_accent})"
    
    # Base CSS with advanced print layout capabilities
    css = f"""
    @page {{
        size: A4;
        margin: 20mm;
        @bottom-right {{
            content: "Page " counter(page);
            font-size: 10pt;
            color: #888;
        }}
    }}
    
    /* Layout Primitives for the AI to use */
    .page-break {{ page-break-before: always; }}
    .cover-page {{ height: 100vh; display: flex; flex-direction: column; justify-content: center; align-items: center; text-align: center; page-break-after: always; }}
    .grid-2 {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
    .grid-3 {{ display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; }}
    .card {{ background: rgba(0,0,0,0.03); border: 1px solid rgba(0,0,0,0.1); padding: 15px; border-radius: 8px; margin-bottom: 20px; -webkit-box-decoration-break: clone; box-decoration-break: clone; }}
    .callout {{ border-left: 4px solid #58a6ff; padding: 10px 15px; background: rgba(88, 166, 255, 0.1); margin: 20px 0; }}
    
    img {{ max-width: 100%; height: auto; border-radius: 8px; }}
    svg {{ max-width: 100%; height: auto; }}

      /* Enforce strict page-break avoidance to prevent cards/flowcharts from being chopped in half */
      .mermaid-auto-wrapper, .mermaid, img, svg, table, pre, blockquote, .grid-2 > div, .grid-3 > div, li {{ 
          page-break-inside: avoid !important; 
          break-inside: avoid !important; 
      }}
      h1, h2, h3, h4, h5, h6 {{
          page-break-after: avoid !important;
          break-after: avoid !important;
          color: {heading_color} !important; /* Fix white text on white bg issue */
      }}

      /* Fix Tailwind color collision */
      .text-primary {{ color: {heading_color} !important; }}
      .bg-primary {{ background-color: {bg_color} !important; }}
      
      /* Refined link handling: stop random underlining on headings/cards if AI wrapped them in links */
      h1 a, h2 a, h3 a, .card a {{ text-decoration: none !important; color: inherit; }}
      
      /* Override AI Tailwind hallucinations that cause invisible text */
      .text-white {{ color: {heading_color} !important; }}
      .text-gray-50, .text-gray-100 {{ color: {text_color} !important; }}
      .bg-gray-800, .bg-gray-900, .bg-black {{ background-color: rgba(0,0,0,0.05) !important; color: {text_color} !important; }}
      
      /* Fix unnecessary underlining generated by AI */
      * {{ text-decoration: none !important; }}
      a {{ text-decoration: underline !important; color: {accent_color} !important; }}

    """

    # Apply special Google Fonts and Layout styles for creative themes
    if theme == 'notebooklm':
        css += f"""
        @import url('https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,700;1,400&family=Open+Sans:wght@400;600&display=swap');
        body {{ font-family: 'Lora', serif; color: {text_color}; background: {bg_color}; line-height: 1.7; font-size: 11pt; }}
        h1, h2, h3, h4 {{ font-family: 'Open Sans', sans-serif; color: {heading_color}; font-weight: 600; page-break-after: avoid; }}
        h1 {{ font-size: 26pt; padding-bottom: 12px; border-bottom: 1px solid #dadce0; margin-bottom: 24px; }}
        h2 {{ font-size: 18pt; margin-top: 1.5em; }}
        blockquote {{ border-left: 4px solid {accent_color}; margin: 0; padding-left: 16px; font-style: italic; color: #5f6368; background: #f1f3f4; padding: 12px; border-radius: 4px; }}
        pre {{ background: #f8f9fa; border: 1px solid #dadce0; padding: 12px; border-radius: 8px; font-family: 'Courier New', Courier, monospace; overflow-x: auto; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 12px; border: 1px solid #dadce0; text-align: left; }}
        th {{ background: #f1f3f4; font-family: 'Open Sans', sans-serif; color: #202124; }}
        """
    elif theme == 'handwritten':
        css += f"""
        @import url('https://fonts.googleapis.com/css2?family=Patrick+Hand&display=swap');
        body {{ 
            font-family: 'Patrick Hand', cursive; 
            color: #2c3e50; 
            background-color: #fdfaf6;
            background-image: linear-gradient(#e4e4e4 1px, transparent 1px);
            background-size: 100% 32px;
            line-height: 32px; 
            font-size: 16pt; 
            padding-top: 8px;
        }}
        /* Add a vertical red margin line to look like notebook paper */
        body::before {{
            content: '';
            position: fixed;
            top: 0; left: 60px; bottom: 0;
            width: 2px;
            background: rgba(255, 99, 71, 0.4);
            z-index: -1;
        }}
        h1, h2, h3 {{ color: #1a252f; page-break-after: avoid; font-weight: bold; margin-bottom: 0px; }}
        h1 {{ font-size: 34pt; border-bottom: 3px solid rgba(0,0,0,0.1); transform: rotate(-1deg); margin-left: 50px; margin-top: 20px; }}
        h2 {{ font-size: 26pt; transform: rotate(0.5deg); margin-left: 50px; }}
        p, ul, ol, table, .mermaid {{ margin-left: 50px; margin-top: 10px; }}
        blockquote {{ border-left: 3px solid rgba(44, 62, 80, 0.3); padding-left: 15px; font-size: 18pt; color: rgba(44, 62, 80, 0.8); margin-left: 50px; }}
        .mermaid {{
            background: transparent;
            padding: 20px 0;
            border: none;
            box-shadow: none;
            margin-bottom: 20px;
        }}
        svg {{ max-width: 100%; height: auto; }}
        table {{ width: calc(100% - 50px); border-collapse: collapse; margin: 20px 0 20px 50px; }}
        th, td {{ padding: 10px; border: 2px solid rgba(44, 62, 80, 0.4); text-align: left; background: rgba(255,255,255,0.5); }}
        """
    elif theme == 'sketching':
        css += f"""
        @import url('https://fonts.googleapis.com/css2?family=Neucha&display=swap');
        body {{ font-family: 'Neucha', cursive; color: {text_color}; background: {bg_color}; line-height: 1.6; font-size: 14pt; }}
        h1, h2, h3 {{ color: {heading_color}; page-break-after: avoid; }}
        h1 {{ font-size: 28pt; border: 2px solid {accent_color}; padding: 10px; text-align: center; border-radius: 255px 15px 225px 15px/15px 225px 15px 255px; }}
        h2 {{ font-size: 22pt; border-bottom: 2px dashed {accent_color}; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
        th, td {{ padding: 10px; border: 2px solid {accent_color}; border-radius: 255px 15px 225px 15px/15px 225px 15px 255px; }}
        """
    elif theme == 'origami':
        css += f"""
        @import url('https://fonts.googleapis.com/css2?family=Jura:wght@400;700&display=swap');
        body {{ font-family: 'Jura', sans-serif; color: {text_color}; background: {bg_color}; line-height: 1.6; font-size: 11pt; }}
        h1, h2, h3 {{ color: {heading_color}; font-weight: 700; page-break-after: avoid; text-transform: uppercase; letter-spacing: 2px; }}
        h1 {{ font-size: 26pt; border-left: 12px solid {accent_color}; padding-left: 15px; box-shadow: 4px 4px 0px rgba(0,0,0,0.05); }}
        h2 {{ font-size: 18pt; border-bottom: 1px solid {accent_color}; padding-bottom: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; box-shadow: 4px 4px 0px rgba(0,0,0,0.05); }}
        th, td {{ padding: 12px; border: 1px solid #dee2e6; }}
        th {{ background: {accent_color}; color: #fff; text-transform: uppercase; }}
        """
    elif theme == 'pixelated':
        css += f"""
        @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
        body {{ font-family: 'Press Start 2P', cursive; color: {text_color}; background: {bg_color}; line-height: 2.0; font-size: 8pt; }}
        h1, h2, h3 {{ color: {heading_color}; page-break-after: avoid; text-transform: uppercase; }}
        h1 {{ font-size: 16pt; border-bottom: 4px solid {accent_color}; padding-bottom: 10px; margin-bottom: 20px; }}
        h2 {{ font-size: 12pt; margin-top: 2em; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; border: 4px solid {accent_color}; }}
        th, td {{ padding: 10px; border: 2px solid {accent_color}; }}
        th {{ background: {accent_color}; color: {bg_color}; }}
        """
    elif theme == 'asciiart':
        css += f"""
        @import url('https://fonts.googleapis.com/css2?family=Fira+Code&display=swap');
        body {{ font-family: 'Fira Code', monospace; color: {text_color}; background: {bg_color}; line-height: 1.5; font-size: 10pt; }}
        h1, h2, h3 {{ color: {heading_color}; page-break-after: avoid; }}
        h1 {{ font-size: 20pt; border-bottom: 1px dashed {accent_color}; padding-bottom: 10px; margin-bottom: 20px; }}
        h2 {{ font-size: 16pt; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; border: 1px solid {text_color}; }}
        th, td {{ padding: 10px; border: 1px dashed {text_color}; }}
        th {{ background: rgba(88, 166, 255, 0.1); color: {accent_color}; }}
        """
    else:
        # Default modern fallback styling
        css += f"""
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;

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
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>{css}</style>
    <script>
        tailwind.config = {{
            corePlugins: {{
                preflight: false // CRITICAL: Prevent Tailwind from resetting our custom theme fonts and borders!
            }},
            theme: {{
                extend: {{
                    colors: {{
                        primary: 'rgb({rgb_primary})',
                        accent: 'rgb({rgb_accent})',
                        heading: 'rgb({rgb_heading})',
                        text: 'rgb({rgb_text})'
                    }},
                    fontFamily: {{
                        sans: ['inherit'],
                        serif: ['inherit'],
                        mono: ['inherit']
                    }}
                }}
            }}
        }}
    </script>
</head>
<body>
    {watermark_html}
    {html_body}
    <script src="https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.min.js"></script>
    <script>
        document.querySelectorAll("pre code.language-mermaid").forEach(function(el) {{
            var div = document.createElement("div");
            div.className = "mermaid";
            var rawCode = el.textContent.trim();
            var initDirective = '%%{{init: {{"look": "handDrawn", "theme": "base", "themeVariables": {{"background": "transparent", "fontFamily": "Patrick Hand", "primaryColor": "transparent", "primaryBorderColor": "#2c3e50", "lineColor": "#2c3e50", "textColor": "#2c3e50"}}}}}}%%';
            div.textContent = initDirective + String.fromCharCode(10) + rawCode;
            el.parentNode.replaceWith(div);
        }});
        
        
        // ---------------------------------------------------------
        // AUTO-FLOWCHART INTERCEPTOR (ASCII & Unicode to Mermaid DOM Compiler)
        // ---------------------------------------------------------
        document.querySelectorAll("p, li, div").forEach(function(el) {{
            let text = el.innerText || el.textContent;
            if (!text) return;
            
            // Prevent recursive interception - skip if inside mermaid OR if it contains a mermaid diagram
            if (el.closest('.mermaid') || el.closest('.mermaid-auto-wrapper')) return;
            if (el.querySelector && el.querySelector('.mermaid, .mermaid-auto-wrapper, pre')) return;
            if (el.tagName === 'PRE' || el.tagName === 'CODE') return;
            
            // Check for ASCII or Unicode arrows
            if (text.includes("->") || text.includes("<-") || text.includes("--") || text.match(/\\\\[.*\\\\]/) ||
                text.includes("↓") || text.includes("→") || text.includes("←") || text.includes("↑") ||
                text.includes("↔") || text.includes("↕") || text.includes("â†")) {{
                
                if (!text.includes(">") && !text.includes("<") && !text.includes("|") && !text.includes("+--") &&
                    !text.includes("↓") && !text.includes("→") && !text.includes("←") && !text.includes("↑") &&
                    !text.includes("↔") && !text.includes("↕") && !text.includes("â†")) return;
                
                // Collapse all newlines so multiline flowcharts are treated as a single chain
                let collapsedText = text.replace(/\\n/g, ' ');
                let parts = collapsedText.split(/(<--->|<-->|<---|--->|<->|-->|<--|->|<-|↓|→|←|↑|↔|↕|â†“|â†•|â†’)/);
                
                if (parts.length > 1 && parts.length < 50) {{
                    let mermaidCode = `graph TD\n`;
                    let currentPrev = "";
                    let currentEdge = "-->";
                    let nodeCounter = 1;
                    let validNodes = 0;
                    
                    parts.forEach(p => {{
                        p = p.trim();
                        if (!p) return;
                        
                        if (["<--->", "<-->", "<->", "↔", "↕", "â†•"].includes(p)) {{
                            currentEdge = "---";
                        }} else if (["--->", "-->", "->", "→", "↓", "â†“", "â†’"].includes(p)) {{
                            currentEdge = "-->";
                        }} else if (["<---", "<--", "<-", "←", "↑"].includes(p)) {{
                            currentEdge = "---";
                        }} else {{
                            let label = p.replace(/\\[/g, '').replace(/\\]/g, '').replace(/\*/g, '').replace(/\+/g, '').replace(/\|/g, '').replace(/\(/g, '').replace(/\)/g, '').trim();
                            if (!label) return;
                            
                            // Truncate overly long text blocks that aren't real nodes
                            if (label.length > 60) label = label.substring(0, 60) + "...";
                            
                            let nodeId = "node" + nodeCounter;
                            mermaidCode += `${{nodeId}}["${{label}}"]
`;
                            
                            if (currentPrev) {{
                                mermaidCode += `${{currentPrev}} ${{currentEdge}} ${{nodeId}}
`;
                            }}
                            currentPrev = nodeId;
                            nodeCounter++;
                            validNodes++;
                        }}
                    }});

                    if (validNodes > 1) {{
                        let wrapper = document.createElement("div");
                        wrapper.className = "mermaid-auto-wrapper my-8 p-6 flex flex-col items-center border-2 border-dashed border-[var(--color-accent)] rounded-xl bg-transparent";
                        let title = document.createElement("div");
                        title.className = "text-sm font-bold opacity-60 mb-4 uppercase tracking-wider";
                        title.innerText = "System Map";
                        wrapper.appendChild(title);
                        let div = document.createElement("div");
                        div.className = "mermaid w-full flex justify-center";
                        var initDir = '%%{{init: {{\"look\": \"handDrawn\", \"theme\": \"base\", \"themeVariables\": {{\"background\": \"transparent\", \"fontFamily\": \"Patrick Hand\", \"primaryColor\": \"transparent\", \"primaryBorderColor\": \"#2c3e50\", \"lineColor\": \"#2c3e50\", \"textColor\": \"#2c3e50\"}}}}}}%%';
                        div.textContent = initDir + '\\n' + mermaidCode.trim();
                        
                        
                        wrapper.appendChild(title);
                        wrapper.appendChild(div);
                        
                        // Replace the entire container block with the mermaid chart
                        el.parentNode.replaceChild(wrapper, el);
                    }}
                }}
            }}
        }});
        
        mermaid.initialize({{ startOnLoad: false }});
        mermaid.run({{ querySelector: '.mermaid' }}).catch(function(err) {{ console.error('Mermaid error:', err); }});


    </script>
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
            page.goto(f"file:///{temp_html_path}", wait_until="load")
            # CRITICAL: Force the browser to aggressively fetch and wait for all fonts defined in the document
            try:
                page.evaluate("async () => { await document.fonts.ready; if (window.mermaidPromise) { await window.mermaidPromise; } }")
            except Exception:
                pass
            page.wait_for_timeout(4000) # Give Mermaid, Tailwind, and ChartJS time to render
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
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.enum.shapes import MSO_SHAPE
    import os
    import json
    from design_tokens import get_theme
    from document_ir import normalize_ir, Slide
    import ppt_style
    
    path = kwargs.get('path', 'presentation.pptx')
    ir_data = kwargs.get('ir') or kwargs
    ir = normalize_ir(ir_data)
    theme_config = get_theme(ir.theme)
    
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(7.5)
    blank_slide_layout = prs.slide_layouts[6]
    
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
            elif sec.type == 'diagram':
                ir.slides.append(Slide(master='diagram', title=sec.title or 'Diagram', source=sec.source, engine=sec.engine))

    if not ir.slides:
        return "ERROR: Empty deck. Generate real content slides."
        
    def slide_has_content(s):
        if s.master not in ['title_slide', 'section_divider', 'closing']:
            return True
        return bool(s.title or s.body or s.items or s.stats or s.chart_data or s.source)
    
    if not any(slide_has_content(s) for s in ir.slides):
        return "ERROR: Empty deck. Generate real content slides with text, stats, charts, or diagrams."

    for idx, slide_data in enumerate(ir.slides):
        slide = prs.slides.add_slide(blank_slide_layout)
        ppt_style.apply_background(slide, theme_config, prs)
        
        master = slide_data.master
        
        # Helper to add standard title
        def add_title(text):
            tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.5), Inches(9), Inches(1))
            tf = tb.text_frame
            p = tf.paragraphs[0]
            p.text = text
            ppt_style.set_run_font(p, theme_config, "Title")
            p.font.size = Pt(36)
            return tb
            
        if master == 'title_slide':
            title_box = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(8), Inches(1.5))
            tf = title_box.text_frame
            p = tf.paragraphs[0]
            p.text = slide_data.title or "Title"
            ppt_style.set_run_font(p, theme_config, "Title")
            p.font.size = Pt(48)
            p.alignment = PP_ALIGN.CENTER
            
            sub_box = slide.shapes.add_textbox(Inches(1), Inches(4), Inches(8), Inches(1))
            stf = sub_box.text_frame
            sp = stf.paragraphs[0]
            sp.text = slide_data.subtitle or ""
            ppt_style.set_run_font(sp, theme_config, "Subtitle")
            sp.font.size = Pt(24)
            sp.alignment = PP_ALIGN.CENTER
            
        elif master == 'section_divider':
            tb = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(8), Inches(1.5))
            tf = tb.text_frame
            p = tf.paragraphs[0]
            p.text = slide_data.title or "Section"
            ppt_style.set_run_font(p, theme_config, "Title")
            p.font.size = Pt(40)
            p.alignment = PP_ALIGN.CENTER
            
        elif master in ['stats', 'stat_grid', 'metrics']:
            add_title(slide_data.title or "Metrics")
            stats = slide_data.stats or []
            if not stats:
                continue
            cols = min(len(stats), 4)
            if cols == 0:
                cols = 1
            width = 8.0 / cols
            for i, stat in enumerate(stats):
                x = Inches(1 + i * width)
                y = Inches(2.5)
                ppt_style.add_card(slide, x, y, Inches(width - 0.2), Inches(2), theme_config['color_card'], theme_config['color_card_border'])
                
                lb = slide.shapes.add_textbox(x, y + Inches(0.2), Inches(width - 0.2), Inches(0.5))
                lp = lb.text_frame.paragraphs[0]
                lp.text = stat.get('label', '')
                ppt_style.set_run_font(lp, theme_config, "Subtitle")
                lp.font.size = Pt(16)
                lp.alignment = PP_ALIGN.CENTER
                
                vb = slide.shapes.add_textbox(x, y + Inches(0.8), Inches(width - 0.2), Inches(1))
                vp = vb.text_frame.paragraphs[0]
                vp.text = str(stat.get('value', ''))
                ppt_style.set_run_font(vp, theme_config, "Title")
                vp.font.size = Pt(32)
                vp.alignment = PP_ALIGN.CENTER
                
        elif master == 'chart':
            add_title(slide_data.title or "Chart")
            cdata = slide_data.chart_data
            if not cdata:
                continue
            
            chart_data = CategoryChartData()
            # Expecting cdata to be dict with 'categories' and 'series': [{'name': '..', 'values': []}]
            if isinstance(cdata, dict):
                if 'categories' in cdata:
                    chart_data.categories = cdata['categories']
                else:
                    chart_data.categories = ['A', 'B', 'C']
                
                if 'series' in cdata:
                    s_data = cdata['series']
                    if isinstance(s_data, dict):
                        for k, v in s_data.items():
                            try:
                                chart_data.add_series(str(k), v)
                            except: pass
                    elif isinstance(s_data, list):
                        for s in s_data:
                            try:
                                chart_data.add_series(s.get('name', 'Series'), s.get('values', []))
                            except: pass
            else:
                # Mock if invalid format
                chart_data.categories = ['A', 'B', 'C']
                chart_data.add_series('Series 1', (1, 2, 3))
            
            ctype = slide_data.chart_type or 'bar'
            x, y, cx, cy = Inches(1), Inches(2), Inches(8), Inches(4.5)
            if ctype == 'line':
                slide.shapes.add_chart(XL_CHART_TYPE.LINE, x, y, cx, cy, chart_data)
            elif ctype == 'pie':
                slide.shapes.add_chart(XL_CHART_TYPE.PIE, x, y, cx, cy, chart_data)
            else:
                slide.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, x, y, cx, cy, chart_data)
                
        elif master == 'diagram':
            add_title(slide_data.title or "Diagram")
            source = slide_data.source or ""
            engine = slide_data.engine or "mermaid"
            if source:
                success = False
                if engine == 'mermaid':
                    try:
                        import diagram_render
                        png_path = diagram_render.render_mermaid_to_png(source, background='transparent', scale=3.0)
                        slide.shapes.add_picture(png_path, Inches(1), Inches(2), width=Inches(8))
                        success = True
                    except Exception as e:
                        print("Diagram render failed:", e)
                
                if not success:
                    tb = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(4))
                    p = tb.text_frame.paragraphs[0]
                    p.text = "[Diagram rendering unavailable or failed]\n\n" + (source[:500] + '...' if len(source) > 500 else source)
                    ppt_style.set_run_font(p, theme_config, "Body")
                    
        elif master in ['two_column', 'comparison']:
            add_title(slide_data.title or "Comparison")
            ppt_style.add_card(slide, Inches(0.5), Inches(2), Inches(4.25), Inches(4.5), theme_config['color_card'], theme_config['color_card_border'])
            ppt_style.add_card(slide, Inches(5.25), Inches(2), Inches(4.25), Inches(4.5), theme_config['color_card'], theme_config['color_card_border'])
            
            tb1 = slide.shapes.add_textbox(Inches(0.7), Inches(2.2), Inches(3.8), Inches(4.1))
            if slide_data.items and len(slide_data.items) > 0:
                p = tb1.text_frame.paragraphs[0]
                p.text = str(slide_data.items[0])
                ppt_style.set_run_font(p, theme_config, "Body")
                
            tb2 = slide.shapes.add_textbox(Inches(5.45), Inches(2.2), Inches(3.8), Inches(4.1))
            if slide_data.items and len(slide_data.items) > 1:
                p = tb2.text_frame.paragraphs[0]
                p.text = str(slide_data.items[1])
                ppt_style.set_run_font(p, theme_config, "Body")
                
        elif master == 'image_focus':
            add_title(slide_data.title or "Focus")
            ppt_style.add_card(slide, Inches(2), Inches(2), Inches(6), Inches(4), theme_config['color_card'], theme_config['color_card_border'])
            tb = slide.shapes.add_textbox(Inches(2.5), Inches(3.5), Inches(5), Inches(1))
            p = tb.text_frame.paragraphs[0]
            p.text = slide_data.content or "Image Placeholder"
            ppt_style.set_run_font(p, theme_config, "Body")
            p.alignment = PP_ALIGN.CENTER
            
        elif master == 'timeline':
            add_title(slide_data.title or "Timeline")
            items = slide_data.items or []
            if items:
                step = 8.0 / len(items)
                for i, item in enumerate(items):
                    x = Inches(1 + i * step)
                    y = Inches(3.5)
                    slide.shapes.add_shape(MSO_SHAPE.OVAL, x, y, Inches(0.3), Inches(0.3))
                    tb = slide.shapes.add_textbox(x - Inches(0.5), y + Inches(0.5), Inches(1.5), Inches(1))
                    p = tb.text_frame.paragraphs[0]
                    p.text = str(item)
                    ppt_style.set_run_font(p, theme_config, "Body")
                    p.font.size = Pt(12)
        
        elif master == 'closing':
            tb = slide.shapes.add_textbox(Inches(1), Inches(3), Inches(8), Inches(1.5))
            tf = tb.text_frame
            p = tf.paragraphs[0]
            p.text = slide_data.title or "Thank You"
            ppt_style.set_run_font(p, theme_config, "Title")
            p.font.size = Pt(48)
            p.alignment = PP_ALIGN.CENTER
            
        else: # content / agenda
            add_title(slide_data.title or "Overview")
            
            body = slide.shapes.add_textbox(Inches(1), Inches(2), Inches(8), Inches(4.5))
            tf = body.text_frame
            tf.word_wrap = True
            if slide_data.items:
                for item in slide_data.items:
                    p = tf.add_paragraph()
                    p.text = f"• {item}"
                    ppt_style.set_run_font(p, theme_config, "Body")
                    p.font.size = Pt(20)
            elif slide_data.content:
                p = tf.paragraphs[0]
                p.text = slide_data.content
                ppt_style.set_run_font(p, theme_config, "Body")
                p.font.size = Pt(20)
                
        ppt_style.add_footer(slide, ir.meta.title or "Presentation", idx + 1, len(ir.slides), theme_config)

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
