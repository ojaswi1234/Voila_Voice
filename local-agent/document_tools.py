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
                self.set_font('Arial', '', 50)
                self.set_text_color(240, 240, 240)
                self.text(30, 150, self.watermark_text.upper())
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', '', 8)
            self.set_text_color(149, 165, 166)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    pdf = PDF(theme_config, watermark)
    
    # Use Arial for stability (FPDF has known issues with some TTF fonts)
    # Note: Limited Unicode support compared to DejaVu, but more reliable
    pdf.set_font('Arial', '', 11)
    
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
                        pdf.set_font('Arial', '', 10)
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
                        # FPDF limitation: encode latin-1 with replace converts non-Latin-1 chars to ?
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
        # FPDF limitation: encode latin-1 with replace converts non-Latin-1 chars to ?
        # This is a known limitation of FPDF without proper Unicode font support
        line_safe = line_safe.encode('latin-1', 'replace').decode('latin-1')
            
        if in_code_block:
            pdf.set_font('Arial', '', 9)
            pdf.set_text_color(*theme_config['color_primary'])
            pdf.set_fill_color(245, 245, 245)
            pdf.cell(0, 5, line_safe, 0, 1, 'L', fill=True)
            continue

        img_match = re.match(r'^!\[.*?\]\((.*?)\)$', stripped)
        if img_match:
            try: pdf.image(img_match.group(1), w=150); pdf.ln(5)
            except: 
                pdf.set_font('Arial', '', 10)
                pdf.set_text_color(255, 0, 0)
                pdf.cell(0, 5, f"[Image error: {img_match.group(1)}]", 0, 1, 'L')
            continue
        
        if stripped.startswith('# '):
            pdf.set_font('Arial', '', 24)
            pdf.set_text_color(*theme_config['color_heading'])
            pdf.multi_cell(0, 12, line_safe[2:])
            pdf.ln(3)
        elif stripped.startswith('## '):
            pdf.set_font('Arial', '', 18)
            pdf.set_text_color(*theme_config['color_accent'])
            pdf.multi_cell(0, 10, line_safe[3:])
            pdf.ln(2)
        elif stripped.startswith('### '):
            pdf.set_font('Arial', '', 14)
            pdf.set_text_color(*theme_config['color_text'])
            pdf.multi_cell(0, 8, line_safe[4:])
            pdf.ln(2)
        elif stripped.startswith('- ') or stripped.startswith('* '):
            pdf.set_font('Arial', '', 11)
            pdf.set_text_color(*theme_config['color_text'])
            pdf.cell(5, 6, chr(149), 0, 0)
            pdf.multi_cell(0, 6, line_safe[2:])
        elif stripped.startswith('> '):
            pdf.set_font('Arial', '', 11)
            pdf.set_text_color(100, 100, 100)
            pdf.set_x(20)
            pdf.multi_cell(0, 6, line_safe[2:])
        else:
            pdf.set_font('Arial', '', 11)
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
    
    path = kwargs.get('path')
    title = kwargs.get('title', 'Presentation')
    slides_data = kwargs.get('slides', [])
    theme = kwargs.get('theme', 'modern_dark')
    theme_config = get_theme(theme)
    
    if isinstance(slides_data, str):
        try: slides_data = json.loads(slides_data)
        except: slides_data = [{"title": "Content", "content": slides_data}]

    prs = Presentation()
    
    # Apply theme colors
    bg_color = RGBColor(*theme_config['color_primary'])
    title_color = RGBColor(*theme_config['color_heading'])
    accent_color = RGBColor(*theme_config['color_accent'])
    text_color = RGBColor(*theme_config['color_text'])

    def apply_bg(slide): slide.background.fill.solid(); slide.background.fill.fore_color.rgb = bg_color

    slide = prs.slides.add_slide(prs.slide_layouts[6]); apply_bg(slide)
    txBox = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(8), Inches(2))
    tf = txBox.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.text = title.upper()
    p.font.bold = True; p.font.size = Pt(48); p.font.color.rgb = title_color; p.font.name = theme_config['font_heading']
    p.alignment = PP_ALIGN.CENTER
    line = slide.shapes.add_shape(9, Inches(4), Inches(4.5), Inches(2), Pt(2)) 
    line.line.color.rgb = accent_color; line.line.width = Pt(4)

    for s in slides_data:
        stype = s.get('type', 'content')
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        apply_bg(slide)
        
        header_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(9), Inches(1))
        hp = header_box.text_frame.paragraphs[0]
        hp.text = str(s.get('title', '')).upper()
        hp.font.bold = True; hp.font.size = Pt(32); hp.font.color.rgb = title_color; hp.font.name = theme_config['font_heading']
        
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
            
            try: slide.shapes.add_chart(chart_type, Inches(1.5), Inches(2.0), Inches(7), Inches(4.5), chart_data_obj)
            except Exception as e:
                # Fallback print error on slide
                slide.shapes.add_textbox(Inches(2), Inches(3), Inches(6), Inches(1)).text_frame.text = f"[Chart generation error: {e}]"
                
        elif stype == 'image':
            img_path = s.get('image_path', '')
            try: slide.shapes.add_picture(img_path, Inches(2), Inches(1.8), height=Inches(5))
            except: slide.shapes.add_textbox(Inches(2), Inches(3), Inches(6), Inches(1)).text_frame.text = f"[Image not found: {img_path}]"
                
        elif stype == 'two_column':
            left_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(4.2), Inches(5))
            lp = left_box.text_frame.paragraphs[0]; left_box.text_frame.word_wrap = True
            lp.text = _strip_markdown(str(s.get('content_left', ''))); lp.font.size = Pt(18); lp.font.color.rgb = text_color; lp.font.name = theme_config['font_body']
            
            right_box = slide.shapes.add_textbox(Inches(5.0), Inches(1.8), Inches(4.2), Inches(5))
            rp = right_box.text_frame.paragraphs[0]; right_box.text_frame.word_wrap = True
            rp.text = _strip_markdown(str(s.get('content_right', ''))); rp.font.size = Pt(18); rp.font.color.rgb = text_color; rp.font.name = theme_config['font_body']
            
        elif stype == 'quote':
            q_box = slide.shapes.add_textbox(Inches(1.5), Inches(2.5), Inches(7), Inches(3))
            qp = q_box.text_frame.paragraphs[0]; q_box.text_frame.word_wrap = True
            qp.text = f'"{_strip_markdown(str(s.get("content", "")))}"'
            qp.font.italic = True; qp.font.size = Pt(36); qp.font.color.rgb = accent_color; qp.alignment = PP_ALIGN.CENTER; qp.font.name = theme_config['font_body']
            
            author = s.get("author", "")
            if author:
                ap = q_box.text_frame.add_paragraph()
                ap.text = f"— {author}"; ap.font.italic = False; ap.font.size = Pt(22); ap.font.color.rgb = text_color; ap.alignment = PP_ALIGN.RIGHT; ap.font.name = theme_config['font_body']
                
        else: # content
            body_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(9), Inches(5))
            btf = body_box.text_frame; btf.word_wrap = True
            lines = str(s.get('content', '')).split('\n')
            
            # Auto-shrink logic for long content
            content_height = 0
            for line in lines:
                content_height += len(line) // 50  # Approximate lines per line of text
            
            font_size = Pt(20)
            if content_height > 15:  # More than ~15 lines
                font_size = Pt(16)
            if content_height > 20:  # More than ~20 lines
                font_size = Pt(14)
            if content_height > 25:  # More than ~25 lines
                font_size = Pt(12)  # Floor at 12pt
            
            for i, line in enumerate(lines):
                p = btf.paragraphs[0] if i == 0 else btf.add_paragraph()
                p.text = _strip_markdown(line.strip('- ').strip('* '))
                p.font.size = font_size; p.font.color.rgb = text_color; p.font.name = theme_config['font_body']
                if line.startswith('- ') or line.startswith('* '): p.level = 1
                
    prs.save(path)
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
