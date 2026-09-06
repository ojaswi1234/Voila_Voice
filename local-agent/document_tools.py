import sys
import json
import csv
import io
import os
import re
import traceback

def read_csv(kwargs):
    path = kwargs.get('path')
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        lines = []
        for i, row in enumerate(reader):
            if i >= 100:
                lines.append("... (truncated at 100 rows)")
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

def read_excel(kwargs):
    import openpyxl
    path = kwargs.get('path')
    sheet_name = kwargs.get('sheet_name')
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
    lines = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= 100:
            lines.append("... (truncated at 100 rows)")
            break
        lines.append(','.join([str(x) if x is not None else "" for x in row]))
    return '\n'.join(lines)

def create_excel(kwargs):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment
    path = kwargs.get('path')
    data = kwargs.get('data')
    wb = openpyxl.Workbook()
    ws = wb.active
    if isinstance(data, str):
        try: data = json.loads(data)
        except: pass

    if data and isinstance(data, list):
        header_fill = PatternFill(start_color="2C3E50", end_color="2C3E50", fill_type="solid")
        header_font = Font(color="FFFFFF", bold=True)
        
        if isinstance(data[0], dict):
            keys = list(data[0].keys())
            ws.append(keys)
            # Style header
            for col in range(1, len(keys)+1):
                cell = ws.cell(row=1, column=col)
                cell.fill = header_fill
                cell.font = header_font
                cell.alignment = Alignment(horizontal="center")
            for row in data:
                ws.append([row.get(k, "") for k in keys])
        elif isinstance(data[0], list):
            for i, row in enumerate(data):
                ws.append(row)
                if i == 0:
                    for col in range(1, len(row)+1):
                        cell = ws.cell(row=1, column=col)
                        cell.fill = header_fill
                        cell.font = header_font
                        
    wb.save(path)
    return f"Successfully created beautifully styled Excel file at {path}"

def modify_excel(kwargs):
    import openpyxl
    path = kwargs.get('path')
    updates = kwargs.get('updates', {}) 
    if isinstance(updates, str): updates = json.loads(updates)
    wb = openpyxl.load_workbook(path)
    ws = wb.active
    for cell, val in updates.items(): ws[cell] = val
    wb.save(path)
    return f"Successfully updated Excel file at {path}"

def read_pdf(kwargs):
    from pypdf import PdfReader
    path = kwargs.get('path')
    reader = PdfReader(path)
    text = ""
    for i, page in enumerate(reader.pages):
        text += page.extract_text() + "\n"
        if len(text) > 15000:
            text = text[:15000] + "\n... (truncated due to length)"
            break
    return text

# --- ENHANCED DOCX CREATION ---
def create_doc(kwargs):
    import docx
    from docx.shared import Pt, RGBColor, Inches
    from docx.enum.text import WD_ALIGN_PARAGRAPH
    
    path = kwargs.get('path')
    content = kwargs.get('content', '') # Expects markdown-like content
    
    doc = docx.Document()
    
    # Define styles
    styles = doc.styles
    
    # Title
    title_style = styles['Title']
    title_style.font.name = 'Calibri Light'
    title_style.font.size = Pt(28)
    title_style.font.color.rgb = RGBColor(44, 62, 80) # Dark blue/gray
    
    # Headings
    h1_style = styles['Heading 1']
    h1_style.font.name = 'Calibri'
    h1_style.font.size = Pt(18)
    h1_style.font.color.rgb = RGBColor(52, 152, 219) # Flat blue
    h1_style.font.bold = True
    
    h2_style = styles['Heading 2']
    h2_style.font.name = 'Calibri'
    h2_style.font.size = Pt(14)
    h2_style.font.color.rgb = RGBColor(41, 128, 185)
    
    # Body
    body_style = styles['Normal']
    body_style.font.name = 'Calibri'
    body_style.font.size = Pt(11)
    body_style.font.color.rgb = RGBColor(51, 51, 51)
    
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            continue
            
        if line.startswith('# '):
            p = doc.add_paragraph(line[2:], style='Title')
            p.alignment = WD_ALIGN_PARAGRAPH.CENTER
        elif line.startswith('## '):
            doc.add_paragraph(line[3:], style='Heading 1')
        elif line.startswith('### '):
            doc.add_paragraph(line[4:], style='Heading 2')
        elif line.startswith('- ') or line.startswith('* '):
            p = doc.add_paragraph(line[2:], style='List Bullet')
        elif re.match(r'^\d+\.\s', line):
            p = doc.add_paragraph(re.sub(r'^\d+\.\s', '', line), style='List Number')
        else:
            # Handle inline bold
            p = doc.add_paragraph(style='Normal')
            parts = re.split(r'(\*\*.*?\*\*)', line)
            for part in parts:
                if part.startswith('**') and part.endswith('**'):
                    run = p.add_run(part[2:-2])
                    run.bold = True
                else:
                    p.add_run(part)
                    
    doc.save(path)
    return f"Successfully created styled DOCX at {path}"

# --- ENHANCED PDF CREATION ---
def create_pdf(kwargs):
    from fpdf import FPDF
    path = kwargs.get('path')
    content = kwargs.get('content', '')
    
    class PDF(FPDF):
        def header(self):
            # Subtle header line
            self.set_draw_color(189, 195, 199)
            self.line(10, 15, 200, 15)
            
        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.set_text_color(149, 165, 166)
            self.cell(0, 10, f'Page {self.page_no()}', 0, 0, 'C')

    pdf = PDF()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)
    
    lines = content.split('\n')
    for line in lines:
        line = line.strip()
        if not line:
            pdf.ln(5)
            continue
            
        line = line.encode('latin-1', 'replace').decode('latin-1')
        
        if line.startswith('# '):
            pdf.set_font("Arial", 'B', 24)
            pdf.set_text_color(44, 62, 80)
            pdf.cell(0, 15, line[2:], 0, 1, 'C')
            pdf.ln(5)
        elif line.startswith('## '):
            pdf.set_font("Arial", 'B', 16)
            pdf.set_text_color(52, 152, 219)
            pdf.cell(0, 10, line[3:], 0, 1, 'L')
        elif line.startswith('### '):
            pdf.set_font("Arial", 'B', 12)
            pdf.set_text_color(41, 128, 185)
            pdf.cell(0, 8, line[4:], 0, 1, 'L')
        elif line.startswith('- ') or line.startswith('* '):
            pdf.set_font("Arial", '', 11)
            pdf.set_text_color(51, 51, 51)
            pdf.cell(5, 6, "-", 0, 0)
            pdf.multi_cell(0, 6, line[2:])
        else:
            pdf.set_font("Arial", '', 11)
            pdf.set_text_color(51, 51, 51)
            pdf.multi_cell(0, 6, line)
            
    pdf.output(path)
    return f"Successfully created beautifully formatted PDF at {path}"

# --- ENHANCED PPT CREATION ---
def create_ppt(kwargs):
    from pptx import Presentation
    from pptx.util import Inches, Pt
    from pptx.dml.color import RGBColor
    from pptx.enum.text import PP_ALIGN
    
    path = kwargs.get('path')
    title = kwargs.get('title', 'Presentation')
    slides_data = kwargs.get('slides', [])
    theme = kwargs.get('theme', 'modern_dark') # modern_dark, corporate_blue, creative
    
    if isinstance(slides_data, str):
        try: slides_data = json.loads(slides_data)
        except: slides_data = [{"title": "Content", "content": slides_data}]
            
    prs = Presentation()
    
    # Theme colors
    if theme == 'corporate_blue':
        bg_color = RGBColor(240, 244, 248)
        title_color = RGBColor(16, 42, 67)
        accent_color = RGBColor(36, 59, 83)
        text_color = RGBColor(51, 78, 104)
    elif theme == 'creative':
        bg_color = RGBColor(255, 250, 240)
        title_color = RGBColor(217, 68, 82)
        accent_color = RGBColor(242, 166, 90)
        text_color = RGBColor(64, 64, 64)
    else: # modern_dark (default)
        bg_color = RGBColor(30, 30, 36)
        title_color = RGBColor(255, 255, 255)
        accent_color = RGBColor(0, 210, 211)
        text_color = RGBColor(200, 200, 200)

    def apply_bg(slide):
        background = slide.background
        fill = background.fill
        fill.solid()
        fill.fore_color.rgb = bg_color

    # Slide 0: Title Slide
    slide = prs.slides.add_slide(prs.slide_layouts[6]) # Blank layout
    apply_bg(slide)
    
    # Title Box
    txBox = slide.shapes.add_textbox(Inches(1), Inches(2.5), Inches(8), Inches(2))
    tf = txBox.text_frame
    tf.word_wrap = True
    p = tf.paragraphs[0]
    p.text = title.upper()
    p.font.bold = True
    p.font.size = Pt(44)
    p.font.color.rgb = title_color
    p.font.name = "Segoe UI"
    p.alignment = PP_ALIGN.CENTER
    
    # Accent Line
    line = slide.shapes.add_shape(9, Inches(4.5), Inches(4.5), Inches(1), Pt(2)) # 9 is line
    line.line.color.rgb = accent_color
    line.line.width = Pt(3)

    for s in slides_data:
        stype = s.get('type', 'content')
        slide = prs.slides.add_slide(prs.slide_layouts[6])
        apply_bg(slide)
        
        # Header Box
        header_box = slide.shapes.add_textbox(Inches(0.5), Inches(0.4), Inches(9), Inches(1))
        hf = header_box.text_frame
        hp = hf.paragraphs[0]
        hp.text = str(s.get('title', '')).upper()
        hp.font.bold = True
        hp.font.size = Pt(28)
        hp.font.color.rgb = title_color
        hp.font.name = "Segoe UI"
        
        # Accent Line under header
        line = slide.shapes.add_shape(9, Inches(0.5), Inches(1.2), Inches(2), Pt(2))
        line.line.color.rgb = accent_color
        line.line.width = Pt(2)
        
        if stype == 'two_column':
            # Left Column
            left_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(4.2), Inches(5))
            ltf = left_box.text_frame
            ltf.word_wrap = True
            lp = ltf.paragraphs[0]
            lp.text = str(s.get('content_left', ''))
            lp.font.size = Pt(18)
            lp.font.color.rgb = text_color
            
            # Right Column
            right_box = slide.shapes.add_textbox(Inches(5.0), Inches(1.8), Inches(4.2), Inches(5))
            rtf = right_box.text_frame
            rtf.word_wrap = True
            rp = rtf.paragraphs[0]
            rp.text = str(s.get('content_right', ''))
            rp.font.size = Pt(18)
            rp.font.color.rgb = text_color
            
        elif stype == 'quote':
            q_box = slide.shapes.add_textbox(Inches(1.5), Inches(2.5), Inches(7), Inches(3))
            qtf = q_box.text_frame
            qtf.word_wrap = True
            qp = qtf.paragraphs[0]
            qp.text = f'"{str(s.get("content", ""))}"'
            qp.font.italic = True
            qp.font.size = Pt(32)
            qp.font.color.rgb = accent_color
            qp.alignment = PP_ALIGN.CENTER
            
            author = s.get("author", "")
            if author:
                ap = qtf.add_paragraph()
                ap.text = f"— {author}"
                ap.font.italic = False
                ap.font.size = Pt(20)
                ap.font.color.rgb = text_color
                ap.alignment = PP_ALIGN.RIGHT
                
        else: # content
            body_box = slide.shapes.add_textbox(Inches(0.5), Inches(1.8), Inches(9), Inches(5))
            btf = body_box.text_frame
            btf.word_wrap = True
            lines = str(s.get('content', '')).split('\n')
            for i, line in enumerate(lines):
                if i == 0:
                    p = btf.paragraphs[0]
                else:
                    p = btf.add_paragraph()
                p.text = line.strip('- ').strip('* ')
                p.font.size = Pt(20)
                p.font.color.rgb = text_color
                if line.startswith('- ') or line.startswith('* '):
                    p.level = 1
                
    prs.save(path)
    return f"Successfully created STUNNING PPT at {path} using {theme} theme!"

def main():
    try:
        input_data = sys.stdin.read()
        if not input_data:
            print("Error: No input data provided via stdin.")
            sys.exit(1)
            
        req = json.loads(input_data)
        action = req.get("action")
        kwargs = req.get("kwargs", {})
        
        actions = {
            "read_csv": read_csv,
            "create_csv": create_csv,
            "read_excel": read_excel,
            "create_excel": create_excel,
            "modify_excel": modify_excel,
            "read_pdf": read_pdf,
            "create_pdf": create_pdf,
            "create_doc": create_doc,
            "create_ppt": create_ppt
        }
        
        if action not in actions:
            print(f"Error: Unknown action '{action}'")
            sys.exit(1)
            
        result = actions[action](kwargs)
        print(result)
        
    except Exception as e:
        print(f"Error executing document tool: {str(e)}\n{traceback.format_exc()}")
        sys.exit(1)

if __name__ == "__main__":
    main()
