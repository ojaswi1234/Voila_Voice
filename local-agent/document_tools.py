import sys
import json
import csv
import io
import os
import re
import traceback

def _analyze_dataset(headers, rows):
    summary = [f"📊 AI DATASET ANALYSIS (Rows: {len(rows)}, Columns: {len(headers)})", "="*50]
    if not rows: return "No data to analyze."
    
    cols_data = list(zip(*rows))
    for i, header in enumerate(headers):
        if i >= len(cols_data): break
        col_vals = [x for x in cols_data[i] if str(x).strip() != ""]
        if not col_vals:
            summary.append(f"🔹 '{header}': EMPTY COLUMN")
            continue
            
        numeric_vals = []
        for x in col_vals:
            try: numeric_vals.append(float(x))
            except: pass
            
        if len(numeric_vals) > len(col_vals) * 0.5: # Treat as numeric
            avg = sum(numeric_vals)/len(numeric_vals)
            summary.append(f"📈 '{header}' (Numeric) | Mean: {avg:.2f} | Min: {min(numeric_vals)} | Max: {max(numeric_vals)} | Empty: {len(rows)-len(col_vals)}")
        else:
            unique = set(col_vals)
            top_3 = list(unique)[:3]
            summary.append(f"🔠 '{header}' (Categorical) | Unique: {len(unique)} | Empty: {len(rows)-len(col_vals)} | Samples: {top_3}")
    return "\n".join(summary)

# --- ENHANCED CSV TOOLS ---
def read_csv(kwargs):
    path = kwargs.get('path')
    analyze = kwargs.get('analyze', False)
    
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        data = list(reader)
        
    if not data: return "File is empty."
    
    headers = data[0]
    rows = data[1:]
    
    if analyze:
        return _analyze_dataset(headers, rows)
        
    # Standard read
    lines = [','.join(headers)]
    for i, row in enumerate(rows):
        if i >= 100:
            lines.append(f"... (truncated, total rows: {len(rows)})")
            break
        lines.append(','.join(row))
    return '\n'.join(lines)

def create_csv(kwargs):
    path = kwargs.get('path')
    data = kwargs.get('data') 
    if isinstance(data, str):
        try:
            parsed = json.loads(data)
            if isinstance(parsed, list): data = parsed
        except: pass

    if isinstance(data, str):
        with open(path, 'w', encoding='utf-8') as f: f.write(data)
    else:
        if not data: return "No data provided."
        keys = data[0].keys()
        with open(path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=keys)
            writer.writeheader()
            writer.writerows(data)
    return f"Successfully created CSV at {path}"

# --- ENHANCED EXCEL TOOLS ---
def read_excel(kwargs):
    import openpyxl
    path = kwargs.get('path')
    sheet_name = kwargs.get('sheet_name')
    analyze = kwargs.get('analyze', False)
    
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
    
    data = list(ws.iter_rows(values_only=True))
    if not data: return "File is empty."
    
    headers = [str(x) if x is not None else f"Col{i}" for i, x in enumerate(data[0])]
    rows = data[1:]
    
    if analyze:
        return _analyze_dataset(headers, rows)
        
    lines = [','.join(headers)]
    for i, row in enumerate(rows):
        if i >= 100:
            lines.append(f"... (truncated, total rows: {len(rows)})")
            break
        lines.append(','.join([str(x) if x is not None else "" for x in row]))
    return '\n'.join(lines)

def create_excel(kwargs):
    import openpyxl
    from openpyxl.worksheet.table import Table, TableStyleInfo
    from openpyxl.utils import get_column_letter
    from openpyxl.chart import BarChart, PieChart, LineChart, Reference
    
    path = kwargs.get('path')
    data = kwargs.get('data')
    chart_type = kwargs.get('chart_type')
    chart_title = kwargs.get('chart_title', 'Data Chart')
    
    wb = openpyxl.Workbook(); ws = wb.active
    if isinstance(data, str):
        try: data = json.loads(data)
        except: pass

    keys = []
    if data and isinstance(data, list):
        if isinstance(data[0], dict):
            keys = list(data[0].keys())
            ws.append(keys)
            for row in data: ws.append([row.get(k, "") for k in keys])
        elif isinstance(data[0], list):
            keys = [f"Col{i}" for i in range(len(data[0]))]
            for i, row in enumerate(data):
                ws.append(row)
                if i == 0: keys = [str(x) for x in row]
    
    if len(data) > 0 and len(keys) > 0:
        # Feature 1: Dynamic Auto-Sizing Columns
        for col in ws.columns:
            max_length = 0
            col_letter = col[0].column_letter
            for cell in col:
                try: max_length = max(max_length, len(str(cell.value)))
                except: pass
            ws.column_dimensions[col_letter].width = max_length + 2

        # Feature 2: Convert to Official Excel Table with Filters & Zebra Striping
        tab = Table(displayName="DataTable", ref=f"A1:{get_column_letter(len(keys))}{len(data)+1}")
        style = TableStyleInfo(name="TableStyleMedium9", showFirstColumn=False, showLastColumn=False, showRowStripes=True, showColumnStripes=True)
        tab.tableStyleInfo = style
        ws.add_table(tab)
        
        # Feature 3: Native Embedded Excel Charts
        if chart_type and len(keys) >= 2:
            ctype = chart_type.lower()
            if ctype == 'pie': chart = PieChart()
            elif ctype == 'line': chart = LineChart()
            else: chart = BarChart()
            
            chart.title = chart_title
            # Assume col 1 is categories, cols 2..N are data
            data_ref = Reference(ws, min_col=2, min_row=1, max_row=len(data)+1, max_col=len(keys))
            cats_ref = Reference(ws, min_col=1, min_row=2, max_row=len(data)+1)
            chart.add_data(data_ref, titles_from_data=True)
            chart.set_categories(cats_ref)
            
            # Place chart beautifully to the right
            chart_col = get_column_letter(len(keys) + 2)
            ws.add_chart(chart, f"{chart_col}2")

    wb.save(path)
    return f"Successfully created NEXT-GEN Excel file at {path} with auto-sized columns, Table filters, and embedded charting!"

def modify_excel(kwargs):
    import openpyxl
    path = kwargs.get('path'); updates = kwargs.get('updates', {}) 
    if isinstance(updates, str): updates = json.loads(updates)
    wb = openpyxl.load_workbook(path); ws = wb.active
    for cell, val in updates.items(): ws[cell] = val
    wb.save(path)
    return f"Successfully updated Excel file at {path}"

# --- DOCX, PDF, PPTX (Unchanged V3 implementations compacted) ---
def read_pdf(kwargs):
    from pypdf import PdfReader
    path = kwargs.get('path'); reader = PdfReader(path)
    text = ""
    for i, page in enumerate(reader.pages):
        text += page.extract_text() + "\n"
        if len(text) > 15000:
            text = text[:15000] + "\n... (truncated due to length)"
            break
    return text

def create_doc(kwargs):
    import docx
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    path = kwargs.get('path'); content = kwargs.get('content', '')
    doc = docx.Document(); styles = doc.styles
    title_style = styles['Title']; title_style.font.name = 'Segoe UI Light'; title_style.font.size = Pt(32); title_style.font.color.rgb = RGBColor(30, 61, 89)
    h1_style = styles['Heading 1']; h1_style.font.name = 'Segoe UI'; h1_style.font.size = Pt(20); h1_style.font.color.rgb = RGBColor(255, 110, 64) 
    body_style = styles['Normal']; body_style.font.name = 'Georgia'; body_style.font.size = Pt(11); body_style.font.color.rgb = RGBColor(40, 40, 40)
    try:
        quote_style = styles.add_style('BlockQuote', docx.enum.style.WD_STYLE_TYPE.PARAGRAPH)
        quote_style.font.name = 'Georgia'; quote_style.font.italic = True; quote_style.font.size = Pt(12); quote_style.font.color.rgb = RGBColor(100, 100, 100)
    except: quote_style = styles['Normal']
    in_code_block = False
    for line in content.split('\n'):
        stripped = line.strip()
        if not stripped and not in_code_block: continue
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            if in_code_block: doc.add_paragraph() 
            continue
        if in_code_block:
            p = doc.add_paragraph(line); p.style.font.name = 'Consolas'; p.style.font.size = Pt(9.5); p.style.font.color.rgb = RGBColor(20, 100, 20)
            continue
        img_match = re.match(r'^!\[.*?\]\((.*?)\)$', stripped)
        if img_match:
            try:
                doc.add_picture(img_match.group(1), width=Inches(5.5)); doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
            except: doc.add_paragraph(f"[Image not found: {img_match.group(1)}]")
            continue
        if stripped.startswith('# '): p = doc.add_paragraph(stripped[2:], style='Title'); p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif stripped.startswith('## '): doc.add_paragraph(stripped[3:], style='Heading 1')
        elif stripped.startswith('### '): doc.add_paragraph(stripped[4:], style='Heading 2')
        elif stripped.startswith('> '): p = doc.add_paragraph(stripped[2:], style='BlockQuote'); p.paragraph_format.left_indent = Inches(0.5)
        elif stripped.startswith('- ') or stripped.startswith('* '): doc.add_paragraph(stripped[2:], style='List Bullet')
        else:
            p = doc.add_paragraph(style='Normal'); parts = re.split(r'(\*\*.*?\*\*)', line)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    run = p.add_run(part[2:-2]); run.bold = True
                else: p.add_run(part)
    doc.save(path)
    return f"Successfully created ultra-styled DOCX at {path}"

def create_pdf(kwargs):
    from fpdf import FPDF
    path = kwargs.get('path'); content = kwargs.get('content', ''); watermark = kwargs.get('watermark', '')
    class PDF(FPDF):
        def header(self):
            self.set_draw_color(255, 110, 64); self.set_line_width(0.8); self.line(10, 15, 200, 15)
            if watermark:
                self.set_font('Arial', 'B', 50); self.set_text_color(240, 240, 240); self.text(30, 150, watermark.upper())
        def footer(self):
            self.set_y(-15); self.set_font('Arial', 'I', 8); self.set_text_color(149, 165, 166); self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')
    pdf = PDF(); pdf.add_page(); pdf.set_auto_page_break(auto=True, margin=15)
    in_code_block = False
    for line in content.split('\n'):
        stripped = line.strip()
        if not stripped and not in_code_block: pdf.ln(5); continue
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            if in_code_block: pdf.ln(2)
            continue
        line_safe = line.encode('latin-1', 'replace').decode('latin-1')
        if in_code_block:
            pdf.set_font("Courier", '', 9); pdf.set_text_color(40, 100, 40); pdf.set_fill_color(245, 245, 245)
            pdf.cell(0, 5, line_safe, 0, 1, 'L', fill=True)
            continue
        img_match = re.match(r'^!\[.*?\]\((.*?)\)$', stripped)
        if img_match:
            try: pdf.image(img_match.group(1), w=150); pdf.ln(5)
            except: pdf.set_font("Arial", 'I', 10); pdf.set_text_color(255, 0, 0); pdf.cell(0, 5, f"[Image error: {img_match.group(1)}]", 0, 1, 'L')
            continue
        if stripped.startswith('# '): pdf.set_font("Arial", 'B', 24); pdf.set_text_color(30, 61, 89); pdf.cell(0, 15, stripped[2:], 0, 1, 'C'); pdf.ln(5)
        elif stripped.startswith('## '): pdf.set_font("Arial", 'B', 18); pdf.set_text_color(255, 110, 64); pdf.cell(0, 10, stripped[3:], 0, 1, 'L')
        elif stripped.startswith('- ') or stripped.startswith('* '): pdf.set_font("Arial", '', 11); pdf.set_text_color(40, 40, 40); pdf.cell(5, 6, chr(149), 0, 0); pdf.multi_cell(0, 6, stripped[2:])
        elif stripped.startswith('> '): pdf.set_font("Arial", 'I', 11); pdf.set_text_color(100, 100, 100); pdf.set_x(20); pdf.multi_cell(0, 6, stripped[2:])
        else: pdf.set_font("Arial", '', 11); pdf.set_text_color(40, 40, 40); pdf.multi_cell(0, 6, line_safe)
    pdf.output(path)
    return f"Successfully created WATERMARKED and formatted PDF at {path}"

def create_ppt(kwargs):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    path = kwargs.get('path'); title = kwargs.get('title', 'Presentation'); slides_data = kwargs.get('slides', []); theme = kwargs.get('theme', 'modern_dark') 
    if isinstance(slides_data, str):
        try: slides_data = json.loads(slides_data)
        except: slides_data = [{"title": "Content", "content": slides_data}]
    prs = Presentation()
    if theme == 'cyberpunk': bg_color = RGBColor(13, 2, 8); title_color = RGBColor(0, 255, 204); accent_color = RGBColor(255, 0, 85); text_color = RGBColor(220, 220, 220)
    elif theme == 'corporate_blue': bg_color = RGBColor(240, 244, 248); title_color = RGBColor(16, 42, 67); accent_color = RGBColor(36, 59, 83); text_color = RGBColor(51, 78, 104)
    elif theme == 'minimalist': bg_color = RGBColor(255, 255, 255); title_color = RGBColor(0, 0, 0); accent_color = RGBColor(200, 200, 200); text_color = RGBColor(100, 100, 100)
    else: bg_color = RGBColor(30, 30, 36); title_color = RGBColor(255, 255, 255); accent_color = RGBColor(255, 110, 64); text_color = RGBColor(200, 200, 200)

    def apply_bg(slide): slide.background.fill.solid(); slide.background.fill.fore_color.rgb = bg_color
    slide = prs.slides.add_slide(prs.slide_layouts[6]); apply_bg(slide)
    txBox = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(8), Inches(2)); tf = txBox.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; p.text = title.upper(); p.font.bold = True; p.font.size = Pt(48); p.font.color.rgb = title_color; p.font.name = "Montserrat"; p.alignment = PP_ALIGN.CENTER
    line = slide.shapes.add_shape(9, Inches(4), Inches(4.5), Inches(2), Pt(2)); line.line.color.rgb = accent_color; line.line.width = Pt(4)

    for s in slides_data:
        stype = s.get('type', 'content'); slide = prs.slides.add_slide(prs.slide_layouts[6]); apply_bg(slide)
        header_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(9), Inches(1))
        hp = header_box.text_frame.paragraphs[0]; hp.text = str(s.get('title', '')).upper(); hp.font.bold = True; hp.font.size = Pt(32); hp.font.color.rgb = title_color; hp.font.name = "Montserrat"
        line = slide.shapes.add_shape(9, Inches(0.5), Inches(1.2), Inches(2), Pt(2)); line.line.color.rgb = accent_color; line.line.width = Pt(3)
        if stype == 'chart':
            chart_data_obj = CategoryChartData(); cdata = s.get('chart_data', {})
            chart_data_obj.categories = list(cdata.keys()); chart_data_obj.add_series('Metrics', list(cdata.values()))
            ctype = s.get('chart_type', 'bar').lower()
            if ctype == 'pie': chart_type = XL_CHART_TYPE.PIE
            elif ctype == 'line': chart_type = XL_CHART_TYPE.LINE
            else: chart_type = XL_CHART_TYPE.COLUMN_CLUSTERED
            try: slide.shapes.add_chart(chart_type, Inches(1.5), Inches(2.0), Inches(7), Inches(4.5), chart_data_obj)
            except Exception as e: print(f"Chart error: {e}")
        elif stype == 'image':
            img_path = s.get('image_path', '')
            try: slide.shapes.add_picture(img_path, Inches(2), Inches(1.8), height=Inches(5))
            except:
                body_box = slide.shapes.add_textbox(Inches(2), Inches(3), Inches(6), Inches(1))
                body_box.text_frame.text = f"[Image not found: {img_path}]"; body_box.text_frame.paragraphs[0].font.color.rgb = RGBColor(255, 0, 0)
        elif stype == 'two_column':
            left_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(4.2), Inches(5)); lp = left_box.text_frame.paragraphs[0]; left_box.text_frame.word_wrap = True; lp.text = str(s.get('content_left', '')); lp.font.size = Pt(18); lp.font.color.rgb = text_color
            right_box = slide.shapes.add_textbox(Inches(5.0), Inches(1.8), Inches(4.2), Inches(5)); rp = right_box.text_frame.paragraphs[0]; right_box.text_frame.word_wrap = True; rp.text = str(s.get('content_right', '')); rp.font.size = Pt(18); rp.font.color.rgb = text_color
        elif stype == 'quote':
            q_box = slide.shapes.add_textbox(Inches(1.5), Inches(2.5), Inches(7), Inches(3)); qp = q_box.text_frame.paragraphs[0]; q_box.text_frame.word_wrap = True; qp.text = f'"{str(s.get("content", ""))}"'; qp.font.italic = True; qp.font.size = Pt(36); qp.font.color.rgb = accent_color; qp.alignment = PP_ALIGN.CENTER
            author = s.get("author", "")
            if author: ap = q_box.text_frame.add_paragraph(); ap.text = f"— {author}"; ap.font.italic = False; ap.font.size = Pt(22); ap.font.color.rgb = text_color; ap.alignment = PP_ALIGN.RIGHT
        else:
            body_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(9), Inches(5)); btf = body_box.text_frame; btf.word_wrap = True
            for i, l in enumerate(str(s.get('content', '')).split('\n')):
                p = btf.paragraphs[0] if i == 0 else btf.add_paragraph(); p.text = l.strip('- ').strip('* '); p.font.size = Pt(20); p.font.color.rgb = text_color
                if l.startswith('- ') or l.startswith('* '): p.level = 1
    prs.save(path)
    return f"Successfully created DYNAMIC PPT at {path} using {theme} theme!"

def main():
    try:
        input_data = sys.stdin.read()
        if not input_data:
            print("Error: No input data provided via stdin.")
            sys.exit(1)
        req = json.loads(input_data)
        action = req.get("action"); kwargs = req.get("kwargs", {})
        actions = {
            "read_csv": read_csv, "create_csv": create_csv,
            "read_excel": read_excel, "create_excel": create_excel, "modify_excel": modify_excel,
            "read_pdf": read_pdf, "create_pdf": create_pdf,
            "create_doc": create_doc, "create_ppt": create_ppt
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
