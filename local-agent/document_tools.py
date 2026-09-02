import sys
import json
import csv
import io
import os
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
    data = kwargs.get('data') # string or list of dicts
    if isinstance(data, str):
        with open(path, 'w', encoding='utf-8') as f:
            f.write(data)
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
    if sheet_name and sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    else:
        ws = wb.active
    
    lines = []
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i >= 100:
            lines.append("... (truncated at 100 rows)")
            break
        lines.append(','.join([str(x) if x is not None else "" for x in row]))
    return '\n'.join(lines)

def create_excel(kwargs):
    import openpyxl
    path = kwargs.get('path')
    data = kwargs.get('data') # list of dicts or list of lists
    wb = openpyxl.Workbook()
    ws = wb.active
    
    if isinstance(data, str):
        try:
            data = json.loads(data)
        except:
            pass

    if data and isinstance(data, list):
        if isinstance(data[0], dict):
            keys = list(data[0].keys())
            ws.append(keys)
            for row in data:
                ws.append([row.get(k, "") for k in keys])
        elif isinstance(data[0], list):
            for row in data:
                ws.append(row)
    wb.save(path)
    return f"Successfully created Excel file at {path}"

def modify_excel(kwargs):
    import openpyxl
    path = kwargs.get('path')
    sheet_name = kwargs.get('sheet_name')
    updates = kwargs.get('updates', {}) # dict of "A1": "Value"
    
    if isinstance(updates, str):
        updates = json.loads(updates)

    wb = openpyxl.load_workbook(path)
    if sheet_name and sheet_name in wb.sheetnames:
        ws = wb[sheet_name]
    else:
        ws = wb.active
        
    for cell, val in updates.items():
        ws[cell] = val
        
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

def create_pdf(kwargs):
    from fpdf import FPDF
    path = kwargs.get('path')
    content = kwargs.get('content', '')
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Helvetica", size=12)
    
    # Simple multi_cell for text handling
    # Convert unicode safely
    content = content.encode('latin-1', 'replace').decode('latin-1')
    pdf.multi_cell(0, 10, content)
    pdf.output(path)
    return f"Successfully created PDF at {path}"

def create_ppt(kwargs):
    from pptx import Presentation
    from pptx.util import Inches
    
    path = kwargs.get('path')
    title = kwargs.get('title', 'Presentation')
    slides_data = kwargs.get('slides', []) # [{"title": "t", "content": "c"}]
    
    prs = Presentation()
    
    # Title Slide
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)
    slide.shapes.title.text = title
    
    # Content slides
    bullet_slide_layout = prs.slide_layouts[1]
    
    if isinstance(slides_data, str):
        try:
            slides_data = json.loads(slides_data)
        except:
            slides_data = [{"title": "Content", "content": slides_data}]
            
    for s in slides_data:
        slide = prs.slides.add_slide(bullet_slide_layout)
        shapes = slide.shapes
        if shapes.title and 'title' in s:
            shapes.title.text = str(s['title'])
        if shapes.placeholders and len(shapes.placeholders) > 1 and 'content' in s:
            body_shape = shapes.placeholders[1]
            tf = body_shape.text_frame
            tf.text = str(s['content'])
            
    prs.save(path)
    return f"Successfully created PPT at {path}"

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
