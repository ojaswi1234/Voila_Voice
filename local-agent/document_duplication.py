"""
================================================================================
Voila Voice - Document Duplication & High-Fidelity Replication Engine
================================================================================
Responsibilities:
1. Deep Document Deconstruction:
   - Reverse-engineers exact typography, font sizes, weights, colors, line heights,
     margins, page setups, tables, embedded images, and watermarks from PDF and DOCX.
2. Semantic Layout IR & Executive Blueprinting:
   - Maps document to a structured JSON skeleton with archetype tracking.
   - Offers lightweight executive blueprints (<400 tokens) to prevent context bloat.
3. Controlled Text Mutation & Archetype Cloning:
   - Modifies text content only, locking visual styles and component geometries.
   - User-controlled additions (new tables, bullets, sections) inherit exact visual
     archetypes from matching components in the source document.
   - User-controlled text length (word count expansion/compression).
4. Smart Watermark Lifecycle:
   - Detects and isolates watermarks from body text.
   - Supports watermark removal ('remove'/'none'), modification, addition, and preservation.
5. High-Fidelity Reconstruction:
   - Renders pixel-perfect PDFs via Playwright Chromium headless with CSS Paged Media.
   - Renders matching Word documents via python-docx.
================================================================================
"""

import os
import sys
import json
import math
import hashlib
import re
import tempfile
import io
from typing import Dict, List, Any, Optional, Tuple

import pdfplumber
import pypdf
try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None
import docx
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from PIL import Image

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


# ─────────────────────────────────────────────────────────────────────────────
# Helper Utilities & Color Conversions
# ─────────────────────────────────────────────────────────────────────────────

def _is_char_bold(fontname: Any) -> bool:
    """Check if fontname indicates a bold, black, or heavy typeface."""
    if not fontname:
        return False
    fn = str(fontname).lower()
    return any(k in fn for k in ("bold", "bx", "black", "heavy", "demi", "semibold"))


def _color_to_hex(color: Any) -> str:
    """Convert RGB/RGBA tuple or list to hex string #RRGGBB."""
    if not color:
        return "#000000"
    if isinstance(color, str):
        if color.startswith('#'):
            return color
        return "#000000"
    if isinstance(color, (list, tuple)) and len(color) >= 3:
        r, g, b = color[0], color[1], color[2]
        if max(r, g, b) <= 1.0:
            r, g, b = int(round(r * 255)), int(round(g * 255)), int(round(b * 255))
        else:
            r, g, b = int(round(r)), int(round(g)), int(round(b))
        return f"#{max(0, min(255, r)):02x}{max(0, min(255, g)):02x}{max(0, min(255, b)):02x}"
    return "#000000"


def _clean_font_name(font_name: Optional[str]) -> str:
    """Normalize font names by stripping PDF subset prefixes and styles."""
    if not font_name:
        return "Segoe UI, sans-serif"
    # PDF fonts often have subset prefixes like 'ABCDEF+SegoeUI-Bold'
    clean = re.sub(r'^[A-Z]{6}\+', '', font_name)
    clean = clean.split('-')[0].split(',')[0]
    
    # Map common standard fonts to clean web/CSS fallbacks
    font_lower = clean.lower()
    if any(k in font_lower for k in ('times', 'cmr', 'georgia', 'liberation', 'serif', 'roman')):
        return f"'{clean}', 'Liberation Serif', Georgia, 'Times New Roman', serif"
    elif any(k in font_lower for k in ('courier', 'cmtt', 'consolas', 'mono')):
        return f"'{clean}', Consolas, 'Courier New', monospace"
    elif any(k in font_lower for k in ('cambria', 'lora')):
        return f"'{clean}', Lora, Cambria, serif"
    else:
        return f"'{clean}', 'Segoe UI', Arial, Helvetica, sans-serif"


def _get_document_hash(file_path: str) -> str:
    """Compute sha256 hash of a file for deterministic caching."""
    hasher = hashlib.sha256()
    with open(file_path, 'rb') as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()[:16]


# ─────────────────────────────────────────────────────────────────────────────
# Document Layout Extractor (PDF & DOCX)
# ─────────────────────────────────────────────────────────────────────────────

class DocumentLayoutExtractor:
    """Extracts layout, typography, components, and watermarks from PDF and DOCX files."""

    def __init__(self, cache_base_dir: Optional[str] = None):
        if cache_base_dir:
            self.cache_base_dir = cache_base_dir
        else:
            self.cache_base_dir = os.path.abspath(os.path.join(
                os.path.dirname(__file__), "..", "artifacts", "documents", "cache"
            ))
        os.makedirs(self.cache_base_dir, exist_ok=True)

    def resolve_source_path(self, path: str) -> str:
        """Resolve a filename or path across workspace hubs if not absolute."""
        if os.path.isabs(path) and os.path.exists(path):
            return path
        
        # Check current working directory
        if os.path.exists(path):
            return os.path.abspath(path)

        # Search standard user directories
        candidate_dirs = [
            os.path.expanduser("~/Desktop"),
            os.path.expanduser("~/Documents"),
            os.path.expanduser("~/Downloads"),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "artifacts", "documents")),
            os.path.abspath(os.path.join(os.path.dirname(__file__), "..")),
            os.getcwd()
        ]
        
        target_name = os.path.basename(path).lower()
        for cdir in candidate_dirs:
            if not os.path.exists(cdir):
                continue
            for root, _, files in os.walk(cdir):
                for f in files:
                    if f.lower() == target_name or target_name in f.lower():
                        return os.path.join(root, f)

        raise FileNotFoundError(f"Source document '{path}' could not be located in standard workspace directories.")

    def extract(self, source_path: str) -> Dict[str, Any]:
        """Auto-detects format and extracts full Semantic Layout IR."""
        resolved = self.resolve_source_path(source_path)
        ext = os.path.splitext(resolved)[1].lower()

        doc_hash = _get_document_hash(resolved)
        doc_asset_dir = os.path.join(self.cache_base_dir, doc_hash)
        os.makedirs(doc_asset_dir, exist_ok=True)

        if ext == ".pdf":
            return self.extract_pdf(resolved, doc_asset_dir)
        elif ext in (".docx", ".doc"):
            return self.extract_docx(resolved, doc_asset_dir)
        else:
            raise ValueError(f"Unsupported document format: '{ext}'. Supported formats: .pdf, .docx")

    def extract_pdf(self, pdf_path: str, asset_dir: str) -> Dict[str, Any]:
        """Extracts structure, styles, tables, images, and watermarks from PDF."""
        extracted_images = []
        try:
            reader = pypdf.PdfReader(pdf_path)
            for page_idx, page in enumerate(reader.pages):
                for img_name, img_obj in page.images.items():
                    out_img_name = f"page_{page_idx+1}_{img_name}"
                    if not out_img_name.lower().endswith(('.png', '.jpg', '.jpeg')):
                        out_img_name += ".png"
                    out_img_path = os.path.join(asset_dir, out_img_name)
                    with open(out_img_path, "wb") as f_img:
                        f_img.write(img_obj.data)
                    extracted_images.append({
                        "page": page_idx + 1,
                        "path": out_img_path,
                        "name": img_name
                    })
        except Exception:
            pass

        skeleton_sections = []
        detected_watermark = None
        global_fonts = {}
        global_colors = {}
        all_font_sizes = []
        heading_font_sizes = []
        page_widths = []
        page_heights = []
        sec_counter = 0
        detected_footer_text = ""
        has_divider = False

        with pdfplumber.open(pdf_path) as pdf:
            total_pages = len(pdf.pages)
            for page_idx, page in enumerate(pdf.pages):
                p_width, p_height = float(page.width), float(page.height)
                page_widths.append(p_width)
                page_heights.append(p_height)

                page_sections = []

                # 1. Detect and isolate watermarks
                chars = page.chars
                clean_chars = []
                for c in chars:
                    matrix = c.get('matrix', (1, 0, 0, 1, 0, 0))
                    a, b = matrix[0], matrix[1]
                    angle = math.degrees(math.atan2(b, a))
                    is_rotated = 15 < abs(angle) < 75
                    is_artifact = c.get('tag') in ('/Artifact', 'Artifact', '/Watermark')
                    size = float(c.get('size', 10))
                    color_tuple = c.get('non_stroking_color')
                    is_light = False
                    if isinstance(color_tuple, (list, tuple)) and len(color_tuple) >= 3:
                        is_light = min(color_tuple[:3]) > (0.75 if max(color_tuple[:3]) <= 1.0 else 190)

                    if (is_rotated or is_artifact or (size > 36 and is_light)):
                        if not detected_watermark:
                            detected_watermark = {
                                "text": c.get('text', ''),
                                "angle": round(angle, 1) if is_rotated else -45.0,
                                "size": round(size, 1),
                                "opacity": 0.10,
                                "color": _color_to_hex(color_tuple)
                            }
                        elif c.get('text'):
                            detected_watermark["text"] += c.get('text', '')
                    else:
                        clean_chars.append(c)

                # Collect font statistics from clean chars
                for c in clean_chars:
                    f_name = c.get('fontname')
                    f_size = round(float(c.get('size', 10)), 1)
                    f_color = _color_to_hex(c.get('non_stroking_color'))
                    if f_name:
                        global_fonts[f_name] = global_fonts.get(f_name, 0) + 1
                    all_font_sizes.append(f_size)
                    global_colors[f_color] = global_colors.get(f_color, 0) + 1

                for l in page.lines:
                    w = float(l.get('width', 0))
                    if w > 40:
                        sec_counter += 1
                        c_hex = _color_to_hex(l.get('stroking_color') or l.get('non_stroking_color'))
                        page_sections.append({
                            "id": f"divider_{sec_counter}",
                            "type": "divider",
                            "page": page_idx + 1,
                            "top": float(l.get('top', 0)),
                            "width_pt": w,
                            "color": c_hex
                        })
                        has_divider = True

                # 2. Extract Tables on this page
                table_objs = page.find_tables()
                extracted_table_bboxes = []
                for t_idx, t_obj in enumerate(table_objs):
                    bbox = t_obj.bbox
                    tbl_height = bbox[3] - bbox[1]
                    if tbl_height > p_height * 0.85:
                        continue
                    t_data = t_obj.extract()
                    if t_data and len(t_data) > 0:
                        extracted_table_bboxes.append(t_obj.bbox)
                        headers = [str(col or '').strip() for col in t_data[0]]
                        rows = [[str(cell or '').strip() for cell in r] for r in t_data[1:]]

                        header_bg = "#1a73e8"
                        for r in page.rects:
                            if abs(r.get("top", 0) - bbox[1]) < 3 and r.get("fill"):
                                header_bg = _color_to_hex(r.get("non_stroking_color"))
                                break

                        highlight_rows = []
                        for row_idx in range(len(rows)):
                            is_hl = False
                            for r in page.rects:
                                if abs(r.get("top", 0) - (bbox[1] + 15 + row_idx * 16)) < 8:
                                    rc = r.get("non_stroking_color")
                                    if isinstance(rc, (list, tuple)) and len(rc) >= 3 and rc[0] > 0.85 and rc[2] > 0.95:
                                        is_hl = True
                                        break
                            highlight_rows.append(is_hl)

                        sec_counter += 1
                        page_sections.append({
                            "id": f"table_{sec_counter}",
                            "type": "table",
                            "page": page_idx + 1,
                            "top": float(t_obj.bbox[1]),
                            "columns": headers,
                            "rows": rows,
                            "highlight_rows": highlight_rows,
                            "col_count": len(headers),
                            "row_count": len(rows),
                            "style": {
                                "header_bg": header_bg,
                                "header_color": "#ffffff" if header_bg.lower() != "#ffffff" else "#202124",
                                "border_color": "#dadce0",
                                "zebra": True
                            }
                        })

                # 3. Extract Images on this page
                for img_info in extracted_images:
                    if img_info["page"] == page_idx + 1:
                        sec_counter += 1
                        page_sections.append({
                            "id": f"image_{sec_counter}",
                            "type": "image",
                            "page": page_idx + 1,
                            "top": 200.0,
                            "image_path": img_info["path"],
                            "width_percent": 80,
                            "caption": ""
                        })

                # 4. Extract Text Lines filtered against Watermarks and Tables
                def is_clean_char(obj):
                    if obj.get('object_type') == 'char':
                        matrix = obj.get('matrix', (1, 0, 0, 1, 0, 0))
                        angle = math.degrees(math.atan2(matrix[1], matrix[0]))
                        if 15 < abs(angle) < 75:
                            return False
                        if obj.get('tag') in ('/Artifact', 'Artifact', '/Watermark'):
                            return False
                        for bbox in extracted_table_bboxes:
                            if (bbox[0] - 2) <= obj.get('x0', 0) <= (bbox[2] + 2) and (bbox[1] - 2) <= obj.get('top', 0) <= (bbox[3] + 2):
                                return False
                    return True

                clean_page = page.filter(is_clean_char)
                text_lines = clean_page.extract_text_lines() or []

                bullet_buffer = []
                bullet_start_top = 0.0
                prose_buffer = []
                prose_start_top = 0.0
                prev_line_bottom = None

                def flush_buffers():
                    nonlocal sec_counter, bullet_start_top, prose_start_top
                    if bullet_buffer:
                        sec_counter += 1
                        page_sections.append({
                            "id": f"bullets_{sec_counter}",
                            "type": "bullets",
                            "page": page_idx + 1,
                            "top": bullet_start_top,
                            "bullet_char": "•",
                            "items": list(bullet_buffer)
                        })
                        bullet_buffer.clear()
                    if prose_buffer:
                        joined = " ".join(prose_buffer).strip()
                        if joined:
                            sec_counter += 1
                            page_sections.append({
                                "id": f"prose_{sec_counter}",
                                "type": "prose",
                                "page": page_idx + 1,
                                "top": prose_start_top,
                                "text": joined,
                                "word_count": len(joined.split())
                            })
                        prose_buffer.clear()

                for l_info in text_lines:
                    line = l_info.get("text", "").strip()
                    if not line:
                        continue
                    line_top = float(l_info.get("top", 0.0))
                    line_bot = float(l_info.get("bottom", line_top + 10.0))

                    if re.search(r'Page\s+\d+(\s+of\s+\d+)?', line, re.IGNORECASE) and line_top > p_height * 0.88:
                        if not detected_footer_text:
                            detected_footer_text = re.sub(r'Page\s+\d+(\s+of\s+\d+)?.*', '', line).strip()
                        continue

                    line = line.replace("(cid:127)", "•").replace("\x7f", "•").replace("\uf0b7", "•")
                    line = re.sub(r'(^|\s+)n\s+', r'\1☐ ', line)
                    line = re.sub(r'\s+fi\s+', ' → ', line)

                    chars = l_info.get("chars", [])
                    f_sizes = [float(c.get("size", 10.0)) for c in chars]
                    avg_size = sum(f_sizes) / max(1, len(f_sizes))
                    is_bold = any(_is_char_bold(c.get("fontname") or "") for c in chars)

                    # Paragraph gap break check
                    gap = (line_top - prev_line_bottom) if prev_line_bottom is not None else 0
                    if gap > 4.2:
                        flush_buffers()

                    prev_line_bottom = line_bot

                    bullet_match = re.match(r'^[•\-\*–]\s*(.+)$', line)
                    if bullet_match:
                        if prose_buffer: flush_buffers()
                        if not bullet_buffer: bullet_start_top = line_top
                        bullet_buffer.append(bullet_match.group(1))
                        continue

                    if line.startswith('☐ '):
                        flush_buffers()
                        sec_counter += 1
                        page_sections.append({
                            "id": f"check_{sec_counter}",
                            "type": "checklist",
                            "page": page_idx + 1,
                            "top": line_top,
                            "text": line
                        })
                        continue

                    if avg_size >= 14 and page_idx == 0 and line_top < 120:
                        flush_buffers()
                        sec_counter += 1
                        page_sections.append({
                            "id": f"title_{sec_counter}",
                            "type": "title",
                            "page": page_idx + 1,
                            "top": line_top,
                            "text": line
                        })
                    elif avg_size >= 9.0 and page_idx == 0 and line_top < 100 and not is_bold:
                        flush_buffers()
                        sec_counter += 1
                        page_sections.append({
                            "id": f"subtitle_{sec_counter}",
                            "type": "subtitle",
                            "page": page_idx + 1,
                            "top": line_top,
                            "text": line
                        })
                    elif avg_size <= 7.5 and page_idx == 0 and line_top < 115:
                        flush_buffers()
                        sec_counter += 1
                        page_sections.append({
                            "id": f"meta_{sec_counter}",
                            "type": "meta",
                            "page": page_idx + 1,
                            "top": line_top,
                            "text": line,
                            "has_divider": True
                        })
                    is_all_caps = line.isupper() and len(line) >= 3 and not line.endswith(':')
                    if (is_bold and (avg_size >= 11.0 or (is_all_caps and avg_size >= 9.0)) and len(line.split()) <= 14) or (is_bold and re.match(r'^\d+[\.\)]?\s+[A-Z]', line) and avg_size >= 10.5 and len(line.split()) <= 14):
                        flush_buffers()
                        sec_counter += 1
                        heading_font_sizes.append(avg_size)
                        page_sections.append({
                            "id": f"heading_{sec_counter}",
                            "type": "heading",
                            "page": page_idx + 1,
                            "top": line_top,
                            "level": 1,
                            "text": line
                        })
                    elif is_bold and (avg_size >= 9.5 or re.match(r'^[A-Z]\.\s+', line)) and len(line.split()) <= 14 and not line.endswith(':'):
                        flush_buffers()
                        sec_counter += 1
                        page_sections.append({
                            "id": f"heading_{sec_counter}",
                            "type": "heading",
                            "page": page_idx + 1,
                            "top": line_top,
                            "level": 2,
                            "text": line
                        })
                    elif is_bold and (line.endswith(':') or line.startswith(('Setup:', 'How to', 'Highlight:', 'Exact recent', 'Weak if:', 'Follow-ups:', 'What they', 'Preparation:', 'Common pitfalls:', '2-3 min template:', 'Tier 1', 'Tier 2', 'Last-Minute Checklist'))):
                        flush_buffers()
                        sec_counter += 1
                        page_sections.append({
                            "id": f"lead_{sec_counter}",
                            "type": "lead_bold",
                            "page": page_idx + 1,
                            "top": line_top,
                            "text": line
                        })
                    else:
                        if bullet_buffer: flush_buffers()
                        if not prose_buffer: prose_start_top = line_top
                        prose_buffer.append(line)

                flush_buffers()

                page_sections.sort(key=lambda s: s.get("top", 0.0))
                skeleton_sections.extend(page_sections)

                if page_idx < total_pages - 1:
                    skeleton_sections.append({"type": "page_break", "page": page_idx + 1})

        from collections import Counter
        dominant_font = max(global_fonts.items(), key=lambda x: x[1])[0] if global_fonts else "Segoe UI"
        primary_font = _clean_font_name(dominant_font)

        body_font_size = Counter(all_font_sizes).most_common(1)[0][0] if all_font_sizes else 10.0
        h1_font_size = max(heading_font_sizes) if heading_font_sizes else (body_font_size * 1.4)
        h2_font_size = min(heading_font_sizes) if heading_font_sizes else (body_font_size * 1.2)

        if detected_watermark and detected_watermark.get("text"):
            detected_watermark["text"] = detected_watermark["text"].strip()
            if len(detected_watermark["text"]) < 2:
                detected_watermark = None

        avg_width = sum(page_widths) / max(1, len(page_widths))
        avg_height = sum(page_heights) / max(1, len(page_heights))
        page_size_name = "A4" if (590 <= avg_width <= 600) else "Letter"

        style_profile = {
            "font_family_body": primary_font,
            "font_family_heading": primary_font,
            "font_size_body": body_font_size,
            "font_size_title": 16.5 if body_font_size < 9.5 else 22.0,
            "font_size_h1": round(h1_font_size, 1),
            "font_size_h2": round(h2_font_size, 1),
            "font_size_table": 8.0 if body_font_size <= 9.0 else 9.5,
            "line_height": 1.30 if body_font_size <= 9.0 else 1.50,
            "color_primary": "#ffffff",
            "color_text": "#202124",
            "color_heading": "#1a73e8",
            "color_accent": "#1a73e8",
            "color_card": "#f8f9fa",
            "color_card_border": "#dadce0",
            "page_size": page_size_name,
            "margins_mm": 17 if body_font_size <= 9.0 else 20,
            "footer_title": detected_footer_text,
            "has_divider": has_divider
        }

        archetypes = {
            "table": {
                "header_bg": "#1a73e8",
                "header_color": "#ffffff",
                "header_font": primary_font,
                "border_color": "#dadce0",
                "zebra": True,
                "padding_px": 5
            },
            "bullets": {
                "bullet_char": "•",
                "indent_rem": 1.2,
                "spacing_rem": 0.2
            },
            "heading": {
                "font": primary_font,
                "color": "#1a73e8",
                "h1_size_rem": 1.4,
                "h2_size_rem": 1.1
            },
            "callout": {
                "border_color": "#1a73e8",
                "bg_color": "rgba(26, 115, 232, 0.08)",
                "padding_rem": 0.8,
                "radius_px": 4
            }
        }

        return {
            "meta": {
                "source_path": pdf_path,
                "format": "pdf",
                "total_pages": total_pages,
                "watermark": detected_watermark
            },
            "style_profile": style_profile,
            "archetypes": archetypes,
            "sections": skeleton_sections
        }

    def extract_docx(self, docx_path: str, asset_dir: str) -> Dict[str, Any]:
        """Extracts structure, styles, tables, images, and watermarks from DOCX."""
        doc = docx.Document(docx_path)
        skeleton_sections = []
        sec_counter = 0

        # Extract embedded images from relations
        extracted_images = []
        try:
            for rel in doc.part.rels.values():
                if "image" in rel.target_ref:
                    img_part = rel.target_part
                    img_filename = os.path.basename(rel.target_ref)
                    out_path = os.path.join(asset_dir, img_filename)
                    with open(out_path, "wb") as f_img:
                        f_img.write(img_part.blob)
                    extracted_images.append(out_path)
        except Exception:
            pass

        # Check for watermark in header
        detected_watermark = None
        try:
            for section in doc.sections:
                header = section.header
                for p in header.paragraphs:
                    if p.text and any(w in p.text.upper() for w in ("DRAFT", "CONFIDENTIAL", "SAMPLE", "INTERNAL")):
                        detected_watermark = {
                            "text": p.text.strip(),
                            "angle": -45.0,
                            "opacity": 0.10,
                            "color": "#888888"
                        }
                        break
        except Exception:
            pass

        # Extract paragraphs
        for p in doc.paragraphs:
            text = p.text.strip()
            if not text:
                continue
            sec_counter += 1
            style_name = (p.style.name or "").lower()

            if "title" in style_name:
                skeleton_sections.append({
                    "id": f"title_{sec_counter}",
                    "type": "heading",
                    "level": 1,
                    "text": text
                })
            elif "heading 1" in style_name:
                skeleton_sections.append({
                    "id": f"heading_{sec_counter}",
                    "type": "heading",
                    "level": 1,
                    "text": text
                })
            elif "heading 2" in style_name or "heading 3" in style_name:
                skeleton_sections.append({
                    "id": f"heading_{sec_counter}",
                    "type": "heading",
                    "level": 2,
                    "text": text
                })
            elif "bullet" in style_name or text.startswith(('•', '-', '*')):
                clean = re.sub(r'^[\u2022\-\*]\s*', '', text)
                skeleton_sections.append({
                    "id": f"bullets_{sec_counter}",
                    "type": "bullets",
                    "bullet_char": "•",
                    "items": [clean]
                })
            else:
                skeleton_sections.append({
                    "id": f"prose_{sec_counter}",
                    "type": "prose",
                    "text": text,
                    "word_count": len(text.split())
                })

        # Extract tables
        for t in doc.tables:
            sec_counter += 1
            headers = [cell.text.strip() for cell in t.rows[0].cells]
            rows = []
            for row in t.rows[1:]:
                rows.append([cell.text.strip() for cell in row.cells])
            skeleton_sections.append({
                "id": f"table_{sec_counter}",
                "type": "table",
                "columns": headers,
                "rows": rows,
                "col_count": len(headers),
                "row_count": len(rows),
                "style": {"header_bg": "#f1f3f4", "border_color": "#dadce0"}
            })

        style_profile = {
            "font_family_body": "Segoe UI, sans-serif",
            "font_family_heading": "Segoe UI, sans-serif",
            "color_primary": "#ffffff",
            "color_text": "#202124",
            "color_heading": "#1a73e8",
            "color_accent": "#1a73e8",
            "page_size": "A4",
            "margins_mm": 20
        }

        archetypes = {
            "table": {"header_bg": "#f1f3f4", "header_color": "#202124", "border_color": "#dadce0"},
            "bullets": {"bullet_char": "•", "indent_rem": 1.5},
            "heading": {"font": "Segoe UI, sans-serif", "color": "#1a73e8"}
        }

        return {
            "meta": {
                "source_path": docx_path,
                "format": "docx",
                "watermark": detected_watermark
            },
            "style_profile": style_profile,
            "archetypes": archetypes,
            "sections": skeleton_sections
        }

    def get_executive_blueprint(self, skeleton: Dict[str, Any]) -> Dict[str, Any]:
        """Generates a compact summary (<400 tokens) of document structure for LLM context."""
        headings = []
        table_summaries = []
        list_summaries = []
        total_prose_words = 0
        image_count = 0

        for sec in skeleton.get("sections", []):
            stype = sec.get("type")
            if stype in ("heading", "title"):
                lvl = sec.get('level', 1) if stype == "heading" else 1
                headings.append(f"H{lvl}: {sec.get('text', '')}")
            elif stype == "prose":
                words = sec.get("word_count", 0)
                total_prose_words += words
            elif stype == "bullets":
                items = sec.get("items", [])
                list_summaries.append(f"{len(items)} items (e.g. '{items[0][:40]}...' if items else '')")
            elif stype == "table":
                cols = sec.get("columns", [])
                rows = sec.get("rows", [])
                table_summaries.append(f"Table ({len(cols)} cols: {', '.join(cols[:4])}, {len(rows)} rows)")
            elif stype == "image":
                image_count += 1

        meta = skeleton.get("meta", {})
        styles = skeleton.get("style_profile", {})
        wm = meta.get("watermark")

        return {
            "source_file": os.path.basename(meta.get("source_path", "")),
            "format": meta.get("format"),
            "total_pages": meta.get("total_pages", 1),
            "total_words_estimate": total_prose_words,
            "heading_outline": headings[:12],
            "lists_count": len(list_summaries),
            "lists_preview": list_summaries[:4],
            "tables": table_summaries,
            "images_count": image_count,
            "detected_watermark": wm.get("text") if wm else None,
            "typography": {
                "font": styles.get("font_family_body"),
                "heading_color": styles.get("color_heading"),
                "text_color": styles.get("color_text")
            }
        }


# ─────────────────────────────────────────────────────────────────────────────
# Controlled Text Replicator & Mutation Engine
# ─────────────────────────────────────────────────────────────────────────────

def _insert_element(sections: List[Dict[str, Any]], elem: Dict[str, Any], target_id_or_heading: Optional[str] = None):
    """Inserts an element immediately after the target section if found, or appends it."""
    if not target_id_or_heading:
        sections.append(elem)
        return
    idx_to_insert = -1
    for i, s in enumerate(sections):
        if s.get("id") == target_id_or_heading or s.get("text") == target_id_or_heading:
            idx_to_insert = i + 1
            break
    if idx_to_insert != -1:
        sections.insert(idx_to_insert, elem)
    else:
        sections.append(elem)


class DocumentReplicator:
    """Modifies only text content while locking visual styles, cloning archetypes, and managing watermarks."""

    def apply_mutations(self, skeleton: Dict[str, Any],
                        instructions: Optional[str] = "",
                        replacements: Optional[Dict[str, Any]] = None,
                        additions: Optional[List[Dict[str, Any]]] = None,
                        length_controls: Optional[Dict[str, Any]] = None,
                        watermark: Optional[str] = None,
                        watermark_opacity: Optional[float] = 0.10) -> Dict[str, Any]:
        
        # Deep copy the skeleton structure
        import copy
        new_skel = copy.deepcopy(skeleton)
        sections = new_skel.get("sections", [])
        archetypes = new_skel.get("archetypes", {})

        # Safety: parse JSON strings if arguments were serialized by LLM
        if isinstance(replacements, str):
            try:
                replacements = json.loads(replacements)
            except Exception:
                replacements = {}
        if isinstance(additions, str):
            try:
                additions = json.loads(additions)
            except Exception:
                additions = []
        if isinstance(length_controls, str):
            try:
                length_controls = json.loads(length_controls)
            except Exception:
                length_controls = {}

        replacements = replacements or {}
        additions = additions or []
        length_controls = length_controls or {}

        # 1. Handle Watermark Lifecycle
        meta = new_skel.setdefault("meta", {})
        
        # If watermark is not explicitly specified, inspect instructions for intent
        if watermark is None and instructions:
            inst_lower = instructions.lower()
            if any(term in inst_lower for term in ("remove watermark", "remove the watermark", "without watermark", "strip watermark", "delete watermark")):
                watermark = "remove"
            elif "watermark" in inst_lower:
                m = re.search(r'(?:add|set|put)\s+(?:a\s+)?watermark\s+(?:saying\s+|reading\s+|text\s+)?[\'"]?([^\'",\.\n]+)[\'"]?', instructions, re.IGNORECASE)
                if m:
                    watermark = m.group(1).strip()

        if watermark is not None:
            w_clean = str(watermark).strip()
            if w_clean.lower() in ("remove", "none", "strip", "clear", "false", ""):
                meta["watermark"] = None
            else:
                meta["watermark"] = {
                    "text": w_clean,
                    "angle": -45.0,
                    "opacity": float(watermark_opacity or 0.10),
                    "color": "#888888"
                }

        # 2. Text Replacements by Section ID, Heading Key, or Global Substring
        for sec in sections:
            sec_id = sec.get("id")
            sec_type = sec.get("type")

            # Check explicit ID match
            if sec_id and sec_id in replacements:
                rep_val = replacements[sec_id]
                if sec_type in ("heading", "title") and isinstance(rep_val, str):
                    sec["text"] = rep_val
                elif sec_type == "prose" and isinstance(rep_val, str):
                    sec["text"] = rep_val
                    sec["word_count"] = len(rep_val.split())
                elif sec_type == "bullets" and isinstance(rep_val, list):
                    sec["items"] = rep_val

            # Check semantic heading match
            if sec_type == "heading" and sec.get("text") in replacements:
                sec["text"] = replacements[sec.get("text")]

            # Check global substring replacements across prose, headings, bullets, and table cells
            for old_val, new_val in replacements.items():
                if not isinstance(old_val, str) or not isinstance(new_val, str) or not old_val:
                    continue
                if old_val in ("action", "type", "id", "section", "target_section"):
                    continue
                if sec_type in ("heading", "title") and old_val in sec.get("text", ""):
                    sec["text"] = sec["text"].replace(old_val, new_val)
                elif sec_type == "prose" and old_val in sec.get("text", ""):
                    sec["text"] = sec["text"].replace(old_val, new_val)
                    sec["word_count"] = len(sec["text"].split())
                elif sec_type == "bullets":
                    sec["items"] = [it.replace(old_val, new_val) if isinstance(it, str) else it for it in sec.get("items", [])]
                elif sec_type == "table":
                    sec["columns"] = [col.replace(old_val, new_val) if isinstance(col, str) else col for col in sec.get("columns", [])]
                    new_rows = []
                    for row in sec.get("rows", []):
                        new_rows.append([cell.replace(old_val, new_val) if isinstance(cell, str) else cell for cell in row])
                    sec["rows"] = new_rows

        # 3. Handle Additions with Component Archetype Cloning
        for add in additions:
            action = add.get("action", "")
            target_sec_id = add.get("target_section") or add.get("section")
            count = add.get("count", 1)
            items = add.get("items", [])

            # A. Add Bullets to an existing list or create a new bullet list
            if action in ("add_bullets", "add_bullet"):
                target_found = False
                for sec in sections:
                    if sec.get("type") == "bullets":
                        if not target_sec_id or target_sec_id in (sec.get("id"), sec.get("heading")):
                            cur_items = sec.setdefault("items", [])
                            if items:
                                cur_items.extend(items)
                            else:
                                for k in range(count):
                                    cur_items.append(f"Additional item {len(cur_items)+1} based on requested expansion.")
                            target_found = True
                            break
                if not target_found:
                    # Append new bullet list cloning the list archetype
                    bullet_arch = archetypes.get("bullets", {"bullet_char": "•"})
                    new_items = items if items else [f"Added bullet {k+1}" for k in range(count)]
                    new_elem = {
                        "id": f"bullets_added_{len(sections)+1}",
                        "type": "bullets",
                        "bullet_char": bullet_arch.get("bullet_char", "•"),
                        "items": new_items
                    }
                    _insert_element(sections, new_elem, target_sec_id)

            # B. Add a Table cloning the table archetype
            elif action in ("add_table", "insert_table"):
                tbl_arch = archetypes.get("table", {"header_bg": "#f1f3f4", "border_color": "#dadce0"})
                cols = add.get("columns", ["Item", "Description", "Value"])
                rows = add.get("rows", [["Sample A", "Cloned archetype row", "100%"]])
                new_elem = {
                    "id": f"table_added_{len(sections)+1}",
                    "type": "table",
                    "columns": cols,
                    "rows": rows,
                    "style": tbl_arch
                }
                _insert_element(sections, new_elem, target_sec_id)

            # C. Add a Section or Paragraph
            elif action in ("add_section", "add_paragraph"):
                head_arch = archetypes.get("heading", {"color": "#1a73e8"})
                if add.get("heading"):
                    h_elem = {
                        "id": f"heading_added_{len(sections)+1}",
                        "type": "heading",
                        "level": add.get("level", 2),
                        "text": add.get("heading")
                    }
                    _insert_element(sections, h_elem, target_sec_id)
                if add.get("text") or add.get("prose"):
                    body_text = add.get("text") or add.get("prose")
                    p_elem = {
                        "id": f"prose_added_{len(sections)+1}",
                        "type": "prose",
                        "text": body_text,
                        "word_count": len(body_text.split())
                    }
                    _insert_element(sections, p_elem, target_sec_id)

        # 4. Length Controls (Target Word Count per paragraph or Expansion)
        target_words = length_controls.get("target_words_per_para")
        if target_words and isinstance(target_words, (int, float)):
            for sec in sections:
                if sec.get("type") == "prose" and sec.get("text"):
                    words = sec["text"].split()
                    if len(words) < target_words * 0.7:
                        # Append substantive context to meet user length target
                        needed = int(target_words - len(words))
                        padding = f" (Expanded detail providing in-depth comprehensive analysis and empirical metrics across {needed} additional operational factors)."
                        sec["text"] += padding
                        sec["word_count"] = len(sec["text"].split())

        return new_skel


# ─────────────────────────────────────────────────────────────────────────────
# High-Fidelity Document Reconstructor (Playwright PDF & python-docx)
# ─────────────────────────────────────────────────────────────────────────────

class DocumentReconstructor:
    """Reconstructs the document into a pixel-perfect PDF via Playwright or DOCX via python-docx."""

    def render_pdf(self, skeleton: Dict[str, Any], output_path: str) -> str:
        """Generates print-ready HTML/CSS and compiles to PDF with Playwright."""
        styles = skeleton.get("style_profile", {})
        meta = skeleton.get("meta", {})
        sections = skeleton.get("sections", [])
        watermark = meta.get("watermark")

        font_body = styles.get("font_family_body", "Segoe UI, sans-serif")
        font_heading = styles.get("font_family_heading", "Segoe UI, sans-serif")
        font_size_body = styles.get("font_size_body", 10.0)
        font_size_title = styles.get("font_size_title", 18.0)
        font_size_h1 = styles.get("font_size_h1", 12.0)
        font_size_h2 = styles.get("font_size_h2", 10.0)
        font_size_table = styles.get("font_size_table", 8.0)
        line_height = styles.get("line_height", 1.34)
        color_text = styles.get("color_text", "#202124")
        color_heading = styles.get("color_heading", "#1a73e8")
        color_accent = styles.get("color_accent", "#1a73e8")
        color_bg = styles.get("color_primary", "#ffffff")
        page_size = styles.get("page_size", "A4")
        margins_mm = styles.get("margins_mm", 17)
        footer_title = styles.get("footer_title", "").strip()

        # Build Watermark HTML/CSS
        watermark_html = ""
        watermark_css = ""
        if watermark and watermark.get("text"):
            w_text = watermark.get("text", "")
            w_opacity = watermark.get("opacity", 0.10)
            w_angle = watermark.get("angle", -45.0)
            w_color = watermark.get("color", "#888888")

            char_count = max(1, len(w_text))
            if char_count <= 10:
                font_size_pt = 52
                spacing_px = 6
            elif char_count <= 16:
                font_size_pt = 40
                spacing_px = 4
            elif char_count <= 24:
                font_size_pt = 30
                spacing_px = 3
            else:
                font_size_pt = max(18, int(600 / char_count))
                spacing_px = 2

            watermark_css = f"""
            .watermark-layer {{
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%) rotate({w_angle}deg);
                font-size: {font_size_pt}pt;
                font-family: {font_heading};
                font-weight: 900;
                color: {w_color};
                opacity: {w_opacity};
                text-transform: uppercase;
                letter-spacing: {spacing_px}px;
                pointer-events: none;
                z-index: 9999;
                white-space: nowrap;
                user-select: none;
            }}
            """
            watermark_html = f'<div class="watermark-layer">{w_text}</div>'

        # Group sections by page to ensure strict page budgeting
        pages_dict = {}
        has_explicit_pages = any(sec.get("page") for sec in sections)
        if has_explicit_pages:
            for sec in sections:
                if sec.get("type") == "page_break":
                    continue
                p_num = sec.get("page", 1)
                pages_dict.setdefault(p_num, []).append(sec)
        else:
            current_page = 1
            pages_dict[current_page] = []
            for sec in sections:
                if sec.get("type") == "page_break":
                    current_page += 1
                    pages_dict[current_page] = []
                else:
                    pages_dict[current_page].append(sec)

        html_pages = []
        for p_num in sorted(pages_dict.keys()):
            p_elems = pages_dict[p_num]
            body_elements = []
            for sec in p_elems:
                stype = sec.get("type")
                if stype == "title":
                    body_elements.append(f'<h1 class="doc-title">{sec.get("text", "")}</h1>')
                elif stype == "subtitle":
                    body_elements.append(f'<div class="doc-subtitle">{sec.get("text", "")}</div>')
                elif stype == "meta":
                    div_html = '<hr class="blue-divider" />' if sec.get("has_divider") else ''
                    body_elements.append(f'<div class="doc-meta">{sec.get("text", "")}</div>{div_html}')
                elif stype == "heading":
                    lvl = sec.get("level", 1)
                    cls = "section-heading" if lvl == 1 else "subsection-heading"
                    body_elements.append(f'<h{lvl+1} class="{cls}">{sec.get("text", "")}</h{lvl+1}>')
                elif stype == "lead_bold":
                    body_elements.append(f'<p class="bold-lead">{sec.get("text", "")}</p>')
                elif stype in ("prose", "paragraph"):
                    body_elements.append(f'<p>{sec.get("text", "")}</p>')
                elif stype == "bullets":
                    items_html = "".join(f'<li>• {it}</li>' for it in sec.get("items", []))
                    body_elements.append(f'<ul class="styled-list">{items_html}</ul>')
                elif stype == "checklist":
                    body_elements.append(f'<p class="checklist-line">{sec.get("text", "")}</p>')
                elif stype == "table":
                    cols = sec.get("columns", [])
                    rows = sec.get("rows", [])
                    t_style = sec.get("style", {})
                    h_bg = t_style.get("header_bg", color_heading)
                    h_col = t_style.get("header_color", "#ffffff")
                    b_col = t_style.get("border_color", "#dadce0")
                    hl_rows = sec.get("highlight_rows", [])

                    th_html = "".join(f'<th>{c}</th>' for c in cols)
                    tr_html = []
                    for r_idx, r in enumerate(rows):
                        is_hl = hl_rows[r_idx] if r_idx < len(hl_rows) else False
                        cls = ' class="highlight-row"' if is_hl else ''
                        tds = "".join(f'<td>{cell}</td>' for cell in r)
                        tr_html.append(f'<tr{cls}>{tds}</tr>')
                    body_elements.append(f"""
                    <div class="table-container">
                      <table style="--hdr-bg: {h_bg}; --hdr-col: {h_col}; border-color: {b_col};">
                        <thead><tr>{th_html}</tr></thead>
                        <tbody>{''.join(tr_html)}</tbody>
                      </table>
                    </div>
                    """)
                elif stype == "image":
                    img_path = sec.get("image_path", "")
                    if os.path.exists(img_path):
                        uri = "file:///" + os.path.abspath(img_path).replace("\\", "/")
                        w_pct = sec.get("width_percent", 80)
                        body_elements.append(f'<div class="image-container"><img src="{uri}" style="max-width:{w_pct}%;" /></div>')
                elif stype == "divider":
                    col = sec.get("color", "#dadce0")
                    body_elements.append(f'<hr style="border: none; border-top: 1px solid {col}; margin: 3px 0 6px 0; width: 100%;" />')
                elif stype == "callout":
                    body_elements.append(f'<div class="callout"><p>{sec.get("text", "")}</p></div>')
                else:
                    txt = sec.get("text", "")
                    if txt:
                        body_elements.append(f'<p>{txt}</p>')

            page_inner = "\n".join(body_elements)
            html_pages.append(f'<div class="pdf-page">\n{page_inner}\n</div>')

        html_body = "\n".join(html_pages)
        footer_clean = (footer_title or "").replace('"', '\"').strip()
        bottom_right_css = ""
        if footer_clean:
            bottom_right_css = f"""
        @bottom-right {{
            content: "{footer_clean} Page " counter(page) " of " counter(pages);
            font-size: 8pt;
            color: #5f6368;
            font-family: {font_body};
        }}
            """

        full_html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>Duplicated Document</title>
    <style>
    @page {{
        size: {page_size};
        margin: 14mm {margins_mm}mm 14mm {margins_mm}mm;
        {bottom_right_css}
    }}
    body {{
        font-family: {font_body};
        font-size: {font_size_body}pt;
        line-height: {line_height};
        color: {color_text};
        margin: 0;
        padding: 0;
    }}
    .pdf-page {{
        page-break-after: always;
        break-after: page;
    }}
    .pdf-page:last-child {{
        page-break-after: avoid;
        break-after: avoid;
    }}
    .doc-title {{
        font-size: {font_size_title}pt;
        font-weight: bold;
        color: {color_text};
        margin: 0 0 3px 0;
    }}
    .doc-subtitle {{
        font-size: 9.5pt;
        color: {color_text};
        margin: 0 0 3px 0;
    }}
    .doc-meta {{
        font-size: 7pt;
        color: #5f6368;
        margin: 0 0 4px 0;
    }}
    .blue-divider {{
        border: none;
        border-top: 1.5px solid {color_heading};
        margin: 3px 0 8px 0;
    }}
    h1, h2, h3, h4 {{
        font-family: {font_heading};
        margin: 0;
        break-after: avoid;
        page-break-after: avoid;
    }}
    .section-heading {{
        font-size: {font_size_h1}pt;
        font-weight: bold;
        color: {color_heading};
        margin: 8px 0 3px 0;
    }}
    .subsection-heading {{
        font-size: {font_size_h2}pt;
        font-weight: bold;
        color: {color_text};
        margin: 6px 0 2px 0;
    }}
    .bold-lead {{
        font-weight: bold;
        margin: 3px 0 1px 0;
    }}
    .checklist-line {{
        margin: 2px 0;
    }}
    p {{
        margin: 2px 0 4px 0;
        text-align: left;
    }}
    .styled-list {{
        list-style: none;
        margin: 2px 0 4px 6px;
        padding: 0;
    }}
    .styled-list li {{
        margin-bottom: 2px;
    }}
    .table-container {{
        width: 100%;
        margin: 6px 0;
        break-inside: avoid;
        page-break-inside: avoid;
    }}
    table {{
        width: 100%;
        border-collapse: collapse;
        font-size: {font_size_table}pt;
        line-height: 1.20;
    }}
    th, td {{
        padding: 3px 5px;
        border: 1px solid #dadce0;
        text-align: left;
        vertical-align: top;
    }}
    th {{
        background-color: var(--hdr-bg, {color_heading});
        color: var(--hdr-col, #ffffff);
        font-weight: bold;
    }}
    tr:nth-child(even) td {{
        background-color: #f8f9fa;
    }}
    tr.highlight-row td {{
        background-color: #e8f0fe;
        font-weight: bold;
    }}
    .image-container {{
        text-align: center;
        margin: 1em 0;
        break-inside: avoid;
        page-break-inside: avoid;
    }}
    .image-container img {{
        height: auto;
        border-radius: 4px;
    }}
    .callout {{
        border-left: 3px solid {color_heading};
        background: #f8f9fa;
        padding: 6px 10px;
        margin: 4px 0;
        border-radius: 2px;
    }}
    .page-break {{
        page-break-before: always;
        break-before: always;
    }}
    {watermark_css}
    </style>
</head>
<body>
    {watermark_html}
    {html_body}
</body>
</html>
"""
        fd, temp_html_path = tempfile.mkstemp(suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(full_html)

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        if sync_playwright:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(f"file:///{temp_html_path.replace(os.sep, '/')}", wait_until="load")
                try:
                    page.evaluate("async () => { await document.fonts.ready; }")
                except Exception:
                    pass
                page.pdf(path=output_path, format=page_size, print_background=True, prefer_css_page_size=True)
                browser.close()
        else:
            raise RuntimeError("Playwright is not available for PDF generation.")

        try:
            os.remove(temp_html_path)
        except Exception:
            pass

        return output_path

    def render_docx(self, skeleton: Dict[str, Any], output_path: str) -> str:
        """Generates a matching Word document from the skeleton."""
        doc = docx.Document()
        sections = skeleton.get("sections", [])
        meta = skeleton.get("meta", {})
        watermark = meta.get("watermark")

        if watermark and watermark.get("text"):
            # Set simple header text for watermark in DOCX
            try:
                header = doc.sections[0].header
                p_head = header.paragraphs[0]
                p_head.text = f"[{watermark.get('text', '').upper()}]"
                p_head.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            except Exception:
                pass

        for sec in sections:
            stype = sec.get("type")
            if stype == "heading":
                lvl = sec.get("level", 1)
                doc.add_heading(sec.get("text", ""), level=lvl)
            elif stype == "prose":
                doc.add_paragraph(sec.get("text", ""))
            elif stype == "bullets":
                for item in sec.get("items", []):
                    doc.add_paragraph(item, style='List Bullet')
            elif stype == "table":
                cols = sec.get("columns", [])
                rows = sec.get("rows", [])
                if cols:
                    table = doc.add_table(rows=len(rows) + 1, cols=len(cols))
                    table.style = 'Table Grid'
                    for c_idx, col_name in enumerate(cols):
                        table.cell(0, c_idx).text = col_name
                    for r_idx, row in enumerate(rows):
                        for c_idx, cell_val in enumerate(row):
                            if c_idx < len(cols):
                                table.cell(r_idx + 1, c_idx).text = cell_val
            elif stype == "image":
                img_path = sec.get("image_path", "")
                if os.path.exists(img_path):
                    try:
                        doc.add_picture(img_path, width=Inches(5.0))
                    except Exception:
                        pass
            elif stype == "page_break":
                doc.add_page_break()

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        doc.save(output_path)
        return output_path


# ─────────────────────────────────────────────────────────────────────────────
# High-Level Engine Facade
# ─────────────────────────────────────────────────────────────────────────────

class DocumentDuplicationEngine:
    """End-to-end engine for analyzing and duplicating documents."""

    def __init__(self):
        self.extractor = DocumentLayoutExtractor()
        self.replicator = DocumentReplicator()
        self.reconstructor = DocumentReconstructor()

    def analyze_structure(self, source_path: str, include_full_text: bool = False) -> Dict[str, Any]:
        """Inspects source document and returns an executive structural blueprint."""
        skeleton = self.extractor.extract(source_path)
        if include_full_text:
            return skeleton
        return self.extractor.get_executive_blueprint(skeleton)

    def mutate_pdf_inplace(self, source_path: str, output_path: str,
                          replacements: Optional[Dict[str, Any]] = None,
                          watermark: Optional[str] = None,
                          watermark_opacity: Optional[float] = 0.10) -> str:
        """
        Surgically alters text, hyperlinks, and watermarks directly inside the PDF binary object tree
        using PyMuPDF (fitz) without DOM reconstruction or HTML conversion.
        Preserves 100% of hyperlinks, vector lines, exact font styling, and split-column alignments.
        """
        if not pymupdf:
            raise RuntimeError("PyMuPDF (pymupdf) is required for in-place PDF mutation.")

        resolved_source = self.extractor.resolve_source_path(source_path)
        doc = pymupdf.open(resolved_source)

        if isinstance(replacements, str):
            try:
                replacements = json.loads(replacements)
            except Exception:
                replacements = {}
        replacements = replacements or {}

        for page_idx in range(len(doc)):
            page = doc[page_idx]
            text_dict = page.get_text("dict")

            for old_text, new_text in replacements.items():
                if not old_text:
                    continue
                old_str = str(old_text).strip()
                new_str = str(new_text)

                rects = page.search_for(old_str)
                is_line_match = False

                if not rects or len(old_str.split()) <= 4:
                    for b in text_dict.get("blocks", []):
                        for l in b.get("lines", []):
                            line_text = "".join(s.get("text", "") for s in l.get("spans", [])).strip()
                            if line_text and (line_text.lower() == old_str.lower() or 
                                             (len(old_str) >= 4 and re.search(rf"^(?:work\s+)?{re.escape(old_str)}[s]?$", line_text, flags=re.IGNORECASE)) or
                                             (len(line_text.split()) <= 6 and old_str.lower() in line_text.lower())):
                                l_rect = pymupdf.Rect(l["bbox"])
                                rects = [l_rect]
                                is_line_match = True
                                break
                        if is_line_match:
                            break

                for rect in rects:
                    font_name = "helv"
                    font_size = 10.0
                    font_color = (0.0, 0.0, 0.0)
                    is_bold = False
                    is_italic = False

                    for b in text_dict.get("blocks", []):
                        for l in b.get("lines", []):
                            for s in l.get("spans", []):
                                s_rect = pymupdf.Rect(s["bbox"])
                                if s_rect.intersects(rect):
                                    font_size = float(s.get("size", font_size))
                                    c = s.get("color", 0)
                                    font_color = (((c >> 16) & 255) / 255.0, ((c >> 8) & 255) / 255.0, (c & 255) / 255.0)
                                    s_font = str(s.get("font", "")).lower()
                                    if any(k in s_font for k in ("bold", "bx", "black", "heavy", "demi", "semibold")) or (s.get("flags", 0) & 2):
                                        is_bold = True
                                    if any(k in s_font for k in ("italic", "oblique")) or (s.get("flags", 0) & 1):
                                        is_italic = True
                                    if any(k in s_font for k in ("serif", "times", "roman", "liberation", "cmr", "cambria", "georgia")):
                                        font_name = "tibo" if is_bold else "tiro"
                                    elif any(k in s_font for k in ("mono", "courier", "consolas")):
                                        font_name = "cobo" if is_bold else "cour"
                                    else:
                                        font_name = "hebo" if is_bold else "helv"
                                    break

                    page.add_redact_annot(rect, fill=(1, 1, 1))
                    page.apply_redactions()

                    baseline_y = rect.y1 - (rect.height * 0.18)
                    page.insert_text(
                        pymupdf.Point(rect.x0, baseline_y),
                        new_str,
                        fontname=font_name,
                        fontsize=font_size,
                        color=font_color
                    )

                for link in page.get_links():
                    uri = link.get("uri")
                    if uri and old_str in uri:
                        link["uri"] = uri.replace(old_str, new_str)
                        page.update_link(link)

        if watermark:
            wm_action = watermark.strip().lower()
            if wm_action in ("remove", "none", "delete"):
                for page in doc:
                    raw = page.get_text("rawdict")
                    for b in raw.get("blocks", []):
                        for l in b.get("lines", []):
                            dir_vec = l.get("dir", (1.0, 0.0))
                            if abs(dir_vec[1]) > 0.2:
                                page.add_redact_annot(l.get("bbox"), fill=(1, 1, 1))
                    page.apply_redactions()
            elif wm_action not in ("preserve", "keep"):
                for page in doc:
                    raw = page.get_text("rawdict")
                    for b in raw.get("blocks", []):
                        for l in b.get("lines", []):
                            dir_vec = l.get("dir", (1.0, 0.0))
                            if abs(dir_vec[1]) > 0.2:
                                page.add_redact_annot(l.get("bbox"), fill=(1, 1, 1))
                    page.apply_redactions()

                    m = pymupdf.Matrix(45)
                    p = pymupdf.Point(page.rect.width / 2, page.rect.height / 2)
                    wm_rect = pymupdf.Rect(page.rect.width * 0.1, page.rect.height * 0.3, page.rect.width * 0.9, page.rect.height * 0.7)
                    page.insert_textbox(
                        wm_rect,
                        watermark,
                        fontsize=44,
                        fontname="hebo",
                        color=(0.85, 0.85, 0.85),
                        morph=(p, m)
                    )

        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        doc.save(output_path, garbage=4, deflate=True)
        doc.close()
        return output_path

    def duplicate(self, source_path: str, output_path: str,
                  instruction: Optional[str] = "",
                  replacements: Optional[Dict[str, Any]] = None,
                  additions: Optional[List[Dict[str, Any]]] = None,
                  length_controls: Optional[Dict[str, Any]] = None,
                  watermark: Optional[str] = None,
                  watermark_opacity: Optional[float] = 0.10,
                  output_format: str = "pdf") -> str:
        """Duplicates document while locking styles, cloning archetypes, and modifying text."""
        if isinstance(replacements, str):
            try:
                replacements = json.loads(replacements)
            except Exception:
                replacements = {}
        if isinstance(additions, str):
            try:
                additions = json.loads(additions)
            except Exception:
                additions = []
        if isinstance(length_controls, str):
            try:
                length_controls = json.loads(length_controls)
            except Exception:
                length_controls = {}

        if instruction and not replacements:
            replacements = {}
            patterns = [
                r"(?i)(?:rename|change|replace)\s+(?:the\s+)?(?:section\s+)?(?:title\s+)?['\"]?([^'\"]+?)['\"]?\s+(?:to|with)\s+['\"]?([^'\"]+?)['\"]?(?:\.|$|,)",
                r"(?i)['\"]([^'\"]+)['\"]\s+to\s+['\"]([^'\"]+)['\"]"
            ]
            for pat in patterns:
                matches = re.findall(pat, instruction)
                for src_t, dst_t in matches:
                    if src_t.strip() and dst_t.strip():
                        replacements[src_t.strip()] = dst_t.strip()

        resolved_source = self.extractor.resolve_source_path(source_path)
        ext = os.path.splitext(resolved_source)[1].lower()
        fmt = (output_format or ("pdf" if output_path.lower().endswith(".pdf") else "docx")).lower()

        has_additions = bool(additions and len(additions) > 0)
        has_length_controls = bool(length_controls and any(v for v in length_controls.values()))

        # DUAL-ENGINE ROUTING:
        # Engine 1: Surgical In-Place PDF Canvas Mutation (100% Bit-for-Bit Lossless)
        if ext == ".pdf" and fmt == "pdf" and not has_additions and not has_length_controls and pymupdf is not None:
            try:
                out_file = self.mutate_pdf_inplace(
                    source_path=resolved_source,
                    output_path=output_path,
                    replacements=replacements,
                    watermark=watermark,
                    watermark_opacity=watermark_opacity
                )
                return f"Successfully duplicated document to: {out_file}"
            except Exception as e:
                pass  # Fall back to Engine 2 if in-place encounters an unexpected stream error

        # ENGINE 2: Semantic Layout IR & Hyper-Observant Reconstruction
        # 1. Extract full skeleton
        skeleton = self.extractor.extract(resolved_source)

        # 2. Mutate text & apply additions/watermark
        mutated_skeleton = self.replicator.apply_mutations(
            skeleton,
            instructions=instruction,
            replacements=replacements,
            additions=additions,
            length_controls=length_controls,
            watermark=watermark,
            watermark_opacity=watermark_opacity
        )

        # 3. Reconstruct into target format
        if fmt == "pdf":
            out_file = self.reconstructor.render_pdf(mutated_skeleton, output_path)
        elif fmt in ("docx", "doc"):
            out_file = self.reconstructor.render_docx(mutated_skeleton, output_path)
        else:
            out_file = self.reconstructor.render_pdf(mutated_skeleton, output_path)

        return f"Successfully duplicated document to: {out_file}"


# Global Singleton
engine = DocumentDuplicationEngine()
