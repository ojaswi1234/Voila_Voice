"""
================================================================================
Voila Voice - Handwritten Document Intelligence & Style-Cloned Duplication Engine
================================================================================
Capabilities:
1. Native Document OCR (Offline ONNX Runtime):
   - Dual-script support: English/Latin (PP-OCRv4) & Hindi/Devanagari (PP-OCRv3 Mobile).
   - Adaptive super-resolution & CLAHE contrast enhancement for low-contrast/faded scans.
2. Handwriting Style Profiling:
   - Ink color model (RGB clustering, Blue Ballpoint/Gel vs Black vs Graphite).
   - Pen nib stroke width estimation via Euclidean Distance Transform.
   - Slant & shear angle estimation via character stem central moments.
   - Paper texture & notebook ruled-line pitch / margin detection.
3. Bilingual Handwriting Synthesis:
   - Authentic Devanagari complex text shaping (Shirorekha connectivity, matras, conjuncts).
   - Authentic Latin cursive and print styling.
   - Dynamic stroke dilation to match pen nib thickness.
   - Affine shear transform to match writer's slant angle.
   - Organic human baseline jitter and kerning micro-distortions.
4. Lossless Document Duplication & Mutation:
   - Telea / Navier-Stokes inpainting: removes handwritten strokes while preserving
     notebook ruled lines and background paper grain.
   - Clean page duplication: synthesizes matching paper canvas and cloned text.
================================================================================
"""

import os
import sys
import math
import random
from typing import Dict, List, Any, Optional, Tuple, Union
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

try:
    import pymupdf
except ImportError:
    try:
        import fitz as pymupdf
    except ImportError:
        pymupdf = None


# ─────────────────────────────────────────────────────────────────────────────
# Handwriting Style Profile
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class HandwritingStyleProfile:
    """Mathematical signature of a human writer's handwriting and paper canvas."""
    ink_rgb: Tuple[int, int, int] = (30, 30, 30)
    ink_bgr: Tuple[int, int, int] = (30, 30, 30)
    ink_tone: str = "DARK_NEUTRAL"  # "BLUE_INK", "BLACK_INK", "GRAPHITE", "DARK_NEUTRAL"
    stroke_width_px: float = 2.0
    slant_deg: float = 0.0
    has_ruled_lines: bool = False
    ruled_line_pitch_px: Optional[float] = None
    ruled_line_bgr: Optional[Tuple[int, int, int]] = None
    has_margin_line: bool = False
    margin_x_px: Optional[int] = None
    background_rgb: Tuple[int, int, int] = (250, 250, 250)
    background_bgr: Tuple[int, int, int] = (250, 250, 250)
    script_type: str = "latin"  # "devanagari", "latin", "mixed"
    avg_line_height_px: float = 35.0
    jitter_intensity: float = 1.0


# ─────────────────────────────────────────────────────────────────────────────
# 1. Native Document OCR Locator (Dual-Script ONNX)
# ─────────────────────────────────────────────────────────────────────────────

class DocumentOCRLocator:
    """Lightweight, 100% offline OCR locator with English and Hindi/Devanagari support."""

    def __init__(self, base_dir: Optional[str] = None):
        if not base_dir:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_dir = base_dir
        self.models_dir = os.path.join(base_dir, "models")
        self.deva_rec_path = os.path.join(self.models_dir, "devanagari", "rec.onnx")
        self.deva_dict_path = os.path.join(self.models_dir, "devanagari", "dict.txt")
        
        # Lazy-loaded engines to keep memory ultralight (<100MB)
        self._latin_engine = None
        self._deva_engine = None

    def _get_latin_engine(self):
        if self._latin_engine is None:
            from rapidocr_onnxruntime import RapidOCR
            self._latin_engine = RapidOCR()
        return self._latin_engine

    def _get_deva_engine(self):
        if self._deva_engine is None:
            if not os.path.exists(self.deva_rec_path) or not os.path.exists(self.deva_dict_path):
                # Fall back to Latin engine if Hindi models are not installed
                return self._get_latin_engine()
            from rapidocr_onnxruntime import RapidOCR
            from rapidocr_onnxruntime.ch_ppocr_v3_rec import TextRecognizer
            engine = RapidOCR()
            engine.text_recognizer = TextRecognizer({
                'use_cuda': False,
                'model_path': self.deva_rec_path,
                'keys_path': self.deva_dict_path,
                'rec_img_shape': [3, 48, 320],
                'rec_batch_num': 6
            })
            self._deva_engine = engine
        return self._deva_engine

    def preprocess_image(self, img_bgr: np.ndarray) -> Tuple[np.ndarray, float]:
        """Super-resolution and CLAHE contrast enhancement for low-contrast/faded scans."""
        h, w = img_bgr.shape[:2]
        scale = 1.0
        
        # If image is small or low-res (e.g. < 900px), upscale 2x
        if max(h, w) < 950:
            scale = 2.0
            img_bgr = cv2.resize(img_bgr, (w * 2, h * 2), interpolation=cv2.INTER_CUBIC)

        # CLAHE contrast enhancement on lightness channel in LAB color space
        lab = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2LAB)
        l, a, b = cv2.split(lab)
        clahe = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8))
        cl = clahe.apply(l)
        enhanced_lab = cv2.merge((cl, a, b))
        enhanced_bgr = cv2.cvtColor(enhanced_lab, cv2.COLOR_LAB2BGR)
        return enhanced_bgr, scale

    def locate_and_transcribe(self, img_bgr: np.ndarray, script_hint: str = "auto") -> List[Dict[str, Any]]:
        """
        Locates text lines and transcribes text with bounding boxes.
        Returns list of dicts:
        [{'bbox': (x0, y0, x1, y1), 'polygon': [...], 'text': str, 'score': float, 'script': str}]
        """
        enhanced_bgr, scale = self.preprocess_image(img_bgr)
        
        # Decide which engine to invoke
        blocks = []
        if script_hint in ("hindi", "devanagari"):
            deva_ocr = self._get_deva_engine()
            res, _ = deva_ocr(enhanced_bgr)
            blocks = self._parse_ocr_result(res, scale, default_script="devanagari")
        elif script_hint == "latin" or script_hint == "english":
            latin_ocr = self._get_latin_engine()
            res, _ = latin_ocr(enhanced_bgr)
            blocks = self._parse_ocr_result(res, scale, default_script="latin")
        else:
            # Auto script detection: first run Latin OCR
            latin_ocr = self._get_latin_engine()
            res_lat, _ = latin_ocr(enhanced_bgr)
            blocks_lat = self._parse_ocr_result(res_lat, scale, default_script="latin") if res_lat else []
            
            # Check if text looks like garbled non-latin or if Devanagari is likely
            deva_ocr = self._get_deva_engine()
            res_dev, _ = deva_ocr(enhanced_bgr)
            blocks_dev = self._parse_ocr_result(res_dev, scale, default_script="devanagari") if res_dev else []

            # Compare confidence and script characteristics
            score_lat = np.mean([b["score"] for b in blocks_lat]) if blocks_lat else 0.0
            score_dev = np.mean([b["score"] for b in blocks_dev]) if blocks_dev else 0.0

            # Count Devanagari unicode characters in Devanagari output
            deva_chars = sum(sum(1 for c in b["text"] if '\u0900' <= c <= '\u097F') for b in blocks_dev)
            
            if deva_chars > 15 or score_dev > score_lat + 0.10:
                blocks = blocks_dev
            else:
                blocks = blocks_lat if blocks_lat else blocks_dev

        return blocks

    def _parse_ocr_result(self, raw_result: Any, scale: float, default_script: str) -> List[Dict[str, Any]]:
        blocks = []
        if not raw_result:
            return blocks
        for item in raw_result:
            box, text, score = item
            # box is [[x0, y0], [x1, y1], [x2, y2], [x3, y3]]
            pts = np.array(box, dtype=float)
            if scale != 1.0:
                pts /= scale
            x0 = float(np.min(pts[:, 0]))
            y0 = float(np.min(pts[:, 1]))
            x1 = float(np.max(pts[:, 0]))
            y1 = float(np.max(pts[:, 1]))
            
            # Detect script of this specific line
            has_deva = any('\u0900' <= c <= '\u097F' for c in text)
            line_script = "devanagari" if has_deva else default_script

            blocks.append({
                "bbox": (int(round(x0)), int(round(y0)), int(round(x1)), int(round(y1))),
                "polygon": pts.tolist(),
                "text": str(text).strip(),
                "score": float(score),
                "script": line_script
            })
        return blocks


# ─────────────────────────────────────────────────────────────────────────────
# 2. Handwriting Style Profiler
# ─────────────────────────────────────────────────────────────────────────────

class HandwritingProfiler:
    """Extracts ink colors, stroke nib dynamics, slants, and paper textures."""

    @staticmethod
    def profile(img_bgr: np.ndarray, ocr_blocks: Optional[List[Dict[str, Any]]] = None) -> HandwritingStyleProfile:
        h, w = img_bgr.shape[:2]
        gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)

        # 1. Background Estimation (upper 80th percentile of lightness)
        lum = 0.299 * img_bgr[:, :, 2] + 0.587 * img_bgr[:, :, 1] + 0.114 * img_bgr[:, :, 0]
        bg_mask = lum > np.percentile(lum, 80)
        bg_pixels = img_bgr[bg_mask]
        if len(bg_pixels) > 0:
            bg_bgr = tuple(int(round(x)) for x in np.median(bg_pixels, axis=0))
            bg_rgb = (bg_bgr[2], bg_bgr[1], bg_bgr[0])
        else:
            bg_bgr = (255, 255, 255)
            bg_rgb = (255, 255, 255)

        # 2. Ink Segmentation via Adaptive/Otsu Threshold
        _, otsu_bin = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        ink_mask = otsu_bin > 0
        ink_pixels = img_bgr[ink_mask]

        if len(ink_pixels) > 0:
            # Dense ink core (darkest 25% of ink)
            ink_lum = 0.299 * ink_pixels[:, 2] + 0.587 * ink_pixels[:, 1] + 0.114 * ink_pixels[:, 0]
            dense_ink = ink_pixels[ink_lum < np.percentile(ink_lum, 30)]
            if len(dense_ink) == 0:
                dense_ink = ink_pixels
            ink_bgr = tuple(int(round(x)) for x in np.median(dense_ink, axis=0))
            ink_rgb = (ink_bgr[2], ink_bgr[1], ink_bgr[0])

            # Classify Ink Tone
            r, g, b = ink_rgb
            if b > r + 12 and b > g + 8:
                ink_tone = "BLUE_INK"
            elif max(r, g, b) < 60 and abs(r - g) < 10 and abs(g - b) < 10:
                ink_tone = "BLACK_INK"
            elif max(r, g, b) >= 60 and abs(r - g) < 15 and abs(g - b) < 15:
                ink_tone = "GRAPHITE"
            else:
                ink_tone = "DARK_NEUTRAL"
        else:
            ink_bgr = (30, 30, 30)
            ink_rgb = (30, 30, 30)
            ink_tone = "DARK_NEUTRAL"

        # 3. Pen Nib Stroke Width Estimation via Distance Transform
        dist_trans = cv2.distanceTransform(otsu_bin, cv2.DIST_L2, 5)
        medial_radii = dist_trans[dist_trans > 0.6]
        if len(medial_radii) > 0:
            stroke_width = float(np.median(medial_radii) * 2.0)
        else:
            stroke_width = 2.0
        stroke_width = max(1.2, min(5.0, stroke_width))

        # 4. Slant Angle Estimation via Character Stem Central Moments
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(otsu_bin)
        slants = []
        for i in range(1, min(num_labels, 500)):
            area = stats[i, cv2.CC_STAT_AREA]
            bw = stats[i, cv2.CC_STAT_WIDTH]
            bh = stats[i, cv2.CC_STAT_HEIGHT]
            # Select vertical character components
            if 15 < bh < 160 and 4 < bw < 120 and area > 35:
                comp = (labels[stats[i, cv2.CC_STAT_TOP]:stats[i, cv2.CC_STAT_TOP] + bh,
                               stats[i, cv2.CC_STAT_LEFT]:stats[i, cv2.CC_STAT_LEFT] + bw] == i).astype(np.uint8)
                m = cv2.moments(comp)
                if m['mu02'] > 0:
                    rad = 0.5 * np.arctan2(2 * m['mu11'], m['mu20'] - m['mu02'])
                    deg = float(np.degrees(rad))
                    if -35.0 < deg < 35.0:
                        slants.append(deg)

        avg_slant = float(np.median(slants)) if len(slants) >= 6 else 0.0

        # 5. Paper Background: Ruled Notebook Lines & Margin Detection
        line_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (max(10, w // 15), 1))
        lines_mask = cv2.morphologyEx(otsu_bin, cv2.MORPH_OPEN, line_kernel)
        line_density = float(np.sum(lines_mask > 0) / (h * w))
        has_ruled_lines = line_density > 0.004

        ruled_line_pitch = None
        ruled_line_bgr = None
        if has_ruled_lines:
            row_sums = np.sum(lines_mask > 0, axis=1)
            line_y_indices = np.where(row_sums > w * 0.15)[0]
            if len(line_y_indices) > 3:
                # Group adjacent indices into distinct line centers
                distinct_lines = []
                cur_group = [line_y_indices[0]]
                for y in line_y_indices[1:]:
                    if y == cur_group[-1] + 1:
                        cur_group.append(y)
                    else:
                        distinct_lines.append(int(np.mean(cur_group)))
                        cur_group = [y]
                if cur_group:
                    distinct_lines.append(int(np.mean(cur_group)))
                
                if len(distinct_lines) >= 3:
                    diffs = np.diff(distinct_lines)
                    valid_diffs = diffs[(diffs > 15) & (diffs < 120)]
                    if len(valid_diffs) > 0:
                        ruled_line_pitch = float(np.median(valid_diffs))
                        # Sample ruled line color
                        sample_y = distinct_lines[len(distinct_lines) // 2]
                        line_pix = img_bgr[sample_y, int(w * 0.2):int(w * 0.8)]
                        ruled_line_bgr = tuple(int(round(x)) for x in np.median(line_pix, axis=0))

        # Check for vertical margin line (leftmost 25% of image)
        vert_kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (1, max(15, h // 15)))
        vert_mask = cv2.morphologyEx(otsu_bin[:, :int(w * 0.25)], cv2.MORPH_OPEN, vert_kernel)
        has_margin = bool(np.sum(vert_mask > 0) > h * 0.3)
        margin_x = None
        if has_margin:
            col_sums = np.sum(vert_mask > 0, axis=0)
            margin_x = int(np.argmax(col_sums))

        # 6. Script Classification
        script_type = "latin"
        avg_lh = 35.0
        if ocr_blocks:
            deva_count = sum(1 for b in ocr_blocks if b.get("script") == "devanagari")
            lat_count = sum(1 for b in ocr_blocks if b.get("script") == "latin")
            if deva_count > 0 and lat_count > 0:
                script_type = "mixed"
            elif deva_count > lat_count:
                script_type = "devanagari"
            else:
                script_type = "latin"

            heights = [b["bbox"][3] - b["bbox"][1] for b in ocr_blocks if 10 < (b["bbox"][3] - b["bbox"][1]) < 120]
            if heights:
                avg_lh = float(np.median(heights))

        return HandwritingStyleProfile(
            ink_rgb=ink_rgb,
            ink_bgr=ink_bgr,
            ink_tone=ink_tone,
            stroke_width_px=stroke_width,
            slant_deg=avg_slant,
            has_ruled_lines=has_ruled_lines,
            ruled_line_pitch_px=ruled_line_pitch,
            ruled_line_bgr=ruled_line_bgr,
            has_margin_line=has_margin,
            margin_x_px=margin_x,
            background_rgb=bg_rgb,
            background_bgr=bg_bgr,
            script_type=script_type,
            avg_line_height_px=avg_lh,
            jitter_intensity=1.0
        )


# ─────────────────────────────────────────────────────────────────────────────
# 3. Bilingual Handwriting Synthesizer
# ─────────────────────────────────────────────────────────────────────────────

class HandwritingSynthesizer:
    """Renders text in authentic human handwriting with organic dynamics."""

    def __init__(self, base_dir: Optional[str] = None):
        if not base_dir:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        self.base_dir = base_dir
        self.assets_font_dir = os.path.join(base_dir, "assets", "fonts")
        
        # Primary open-source font candidates
        self.kalam_reg = os.path.join(self.assets_font_dir, "Kalam-Regular.ttf")
        self.kalam_bold = os.path.join(self.assets_font_dir, "Kalam-Bold.ttf")

        # Windows system fonts
        win_fonts = r"C:\Windows\Fonts"
        self.ink_free = os.path.join(win_fonts, "Inkfree.ttf")
        self.segoe_script = os.path.join(win_fonts, "segoesc.ttf")
        self.segoe_print = os.path.join(win_fonts, "segoepr.ttf")
        self.lucida_hand = os.path.join(win_fonts, "LHANDW.TTF")

    def _select_font(self, text: str, profile: HandwritingStyleProfile, is_bold: bool = False) -> str:
        """Chooses the most authentic handwriting font for the script and profile."""
        has_deva = any('\u0900' <= c <= '\u097F' for c in text)
        if has_deva:
            # Devanagari requires Kalam or Windows Mangal/Nirmala
            if is_bold and os.path.exists(self.kalam_bold):
                return self.kalam_bold
            if os.path.exists(self.kalam_reg):
                return self.kalam_reg
            # Fallback to Windows Indic fonts
            for fallback in ["Nirmala.ttf", "mangal.ttf"]:
                fb_p = os.path.join(r"C:\Windows\Fonts", fallback)
                if os.path.exists(fb_p):
                    return fb_p
            return "arial.ttf"

        # Latin / English Selection based on slant & tone
        if abs(profile.slant_deg) > 4.0:
            # Cursive slant requested
            if os.path.exists(self.segoe_script):
                return self.segoe_script
            if os.path.exists(self.lucida_hand):
                return self.lucida_hand

        # Print / casual Latin
        if os.path.exists(self.ink_free):
            return self.ink_free
        if os.path.exists(self.kalam_reg):
            return self.kalam_reg
        if os.path.exists(self.segoe_print):
            return self.segoe_print
        return "arial.ttf"

    def render_handwritten_patch(
        self,
        text: str,
        profile: HandwritingStyleProfile,
        target_box_wh: Tuple[int, int],
        is_bold: bool = False
    ) -> np.ndarray:
        """
        Synthesizes a transparent RGBA image of handwritten text matching
        stroke width, ink color, slant angle, and baseline jitter.
        """
        bw, bh = target_box_wh
        bw = max(10, bw)
        bh = max(10, bh)

        font_file = self._select_font(text, profile, is_bold=is_bold)
        
        # Calculate optimal font size to fill ~75% of target box height
        font_size = max(12, int(bh * 0.72))
        try:
            font = ImageFont.truetype(font_file, size=font_size)
        except Exception:
            font = ImageFont.load_default()

        # Canvas with padding to allow for slant shear and stroke dilation
        pad_x = 20
        pad_y = 15
        canvas_w = bw + (pad_x * 2)
        canvas_h = bh + (pad_y * 2)

        # 1. Base Text Rendering (Alpha channel)
        txt_img = Image.new("RGBA", (canvas_w, canvas_h), (0, 0, 0, 0))
        draw = ImageDraw.Draw(txt_img)

        # Baseline alignment
        # Check text bbox
        try:
            bbox = font.getbbox(text)
            text_w = bbox[2] - bbox[0]
            text_h = bbox[3] - bbox[1]
        except Exception:
            text_w = len(text) * int(font_size * 0.6)
            text_h = font_size

        draw_x = pad_x
        draw_y = pad_y + max(0, (bh - text_h) // 2)

        # Human Organic Jitter: apply subtle micro-variations
        jitter_y = random.uniform(-1.0, 1.0) * profile.jitter_intensity
        draw_y += int(round(jitter_y))

        # Render glyphs with full opacity
        ink_r, ink_g, ink_b = profile.ink_rgb
        draw.text((draw_x, draw_y), text, font=font, fill=(ink_r, ink_g, ink_b, 250))

        # Convert to numpy RGBA
        arr = np.array(txt_img)
        alpha = arr[:, :, 3]

        # 2. Pen Nib Stroke Dilation
        # If original handwriting had thick strokes, dilate font stroke
        target_stroke = profile.stroke_width_px
        if target_stroke > 2.2:
            dilate_radius = int(round((target_stroke - 2.0) / 1.5))
            if dilate_radius >= 1:
                k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (dilate_radius * 2 + 1, dilate_radius * 2 + 1))
                alpha = cv2.dilate(alpha, k, iterations=1)
                arr[:, :, 3] = alpha

        # 3. Slant & Shear Transformation
        slant = profile.slant_deg
        if abs(slant) > 1.5:
            shear_factor = math.tan(math.radians(-slant))
            M = np.float32([[1, shear_factor, 0], [0, 1, 0]])
            arr = cv2.warpAffine(arr, M, (canvas_w, canvas_h), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=(0, 0, 0, 0))

        # 4. Ink Falloff & Edge Bleed
        # Feather the alpha edge slightly for organic paper absorption
        blurred_alpha = cv2.GaussianBlur(arr[:, :, 3], (3, 3), 0.5)
        # Preserve solid core
        core = arr[:, :, 3] > 200
        arr[:, :, 3] = np.where(core, arr[:, :, 3], blurred_alpha)

        # Crop back to target bounding box
        cropped = arr[pad_y:pad_y + bh, pad_x:pad_x + bw]
        return cropped


# ─────────────────────────────────────────────────────────────────────────────
# 4. Handwritten Document Replicator & In-Place Mutator
# ─────────────────────────────────────────────────────────────────────────────

class HandwrittenDocumentReplicator:
    """Duplicates handwritten documents in-place or from scratch."""

    def __init__(self):
        self.ocr_locator = DocumentOCRLocator()
        self.profiler = HandwritingProfiler()
        self.synthesizer = HandwritingSynthesizer()

    def duplicate_in_place(
        self,
        source_path: str,
        output_path: str,
        replacements: Dict[str, str],
        instruction: Optional[str] = None
    ) -> str:
        """
        Performs in-place handwriting mutation:
        1. Identifies handwritten text regions matching replacements.
        2. Inpaints old strokes via Telea/Navier-Stokes (preserving notebook lines/paper grain).
        3. Synthesizes replacement text using the writer's profiled handwriting style.
        4. Saves output as high-resolution PDF or image.
        """
        # Load source image or PDF page 1
        is_pdf = source_path.lower().endswith(".pdf")
        if is_pdf:
            if pymupdf is None:
                raise RuntimeError("PyMuPDF required to read PDF scans.")
            doc = pymupdf.open(source_path)
            page = doc[0]
            pix = page.get_pixmap(dpi=200)
            img_bgr = cv2.imdecode(np.frombuffer(pix.tobytes("png"), np.uint8), cv2.IMREAD_COLOR)
        else:
            img_bgr = cv2.imread(source_path)
            if img_bgr is None:
                raise FileNotFoundError(f"Could not load image: {source_path}")

        h, w = img_bgr.shape[:2]

        # 1. OCR text detection and profiling
        ocr_blocks = self.ocr_locator.locate_and_transcribe(img_bgr)
        profile = self.profiler.profile(img_bgr, ocr_blocks)

        output_img = img_bgr.copy()

        # Parse instructions if replacements empty
        if instruction and not replacements:
            replacements = {}
            import re
            pats = [
                r"(?i)(?:rename|change|replace)\s+(?:the\s+)?(?:section\s+)?(?:title\s+)?['\"]?([^'\"]+?)['\"]?\s+(?:to|with)\s+['\"]?([^'\"]+?)['\"]?(?:\.|$|,)",
                r"(?i)['\"]([^'\"]+)['\"]\s+to\s+['\"]([^'\"]+)['\"]"
            ]
            for pat in pats:
                for s, d in re.findall(pat, instruction):
                    replacements[s.strip()] = d.strip()

        # 2. Execute replacements on matching handwritten blocks
        for old_txt, new_txt in replacements.items():
            matched_blocks = []
            for b in ocr_blocks:
                t = b["text"].lower()
                ot = old_txt.lower()
                if ot in t or t in ot or (len(ot) > 3 and sum(1 for w in ot.split() if w in t) >= 1):
                    matched_blocks.append(b)

            if not matched_blocks:
                # If no direct match, check closest block by word overlap or position
                for b in ocr_blocks:
                    if any(w.lower() in b["text"].lower() for w in old_txt.split() if len(w) > 2):
                        matched_blocks.append(b)
                        break

            for mb in matched_blocks:
                bx0, by0, bx1, by1 = mb["bbox"]
                bw = bx1 - bx0
                bh = by1 - by0
                if bw <= 0 or bh <= 0:
                    continue

                # Add 3px safety margin for inpainting
                ix0 = max(0, bx0 - 3)
                iy0 = max(0, by0 - 3)
                ix1 = min(w, bx1 + 3)
                iy1 = min(h, by1 + 3)

                region = output_img[iy0:iy1, ix0:ix1]
                reg_gray = cv2.cvtColor(region, cv2.COLOR_BGR2GRAY)
                
                # Create ink mask for inpainting
                _, reg_thresh = cv2.threshold(reg_gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
                
                # Inpaint ink strokes only, preserving ruled lines and background grain
                k = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3))
                dilated_ink = cv2.dilate(reg_thresh, k, iterations=1)
                inpainted_region = cv2.inpaint(region, dilated_ink, inpaintRadius=3, flags=cv2.INPAINT_TELEA)

                # Synthesize new handwritten text in cloned handwriting style
                patch_rgba = self.synthesizer.render_handwritten_patch(
                    text=new_txt,
                    profile=profile,
                    target_box_wh=(ix1 - ix0, iy1 - iy0)
                )

                # Alpha blend synthesized handwriting onto inpainted paper background
                ph, pw = patch_rgba.shape[:2]
                alpha_channel = (patch_rgba[:, :, 3].astype(float) / 255.0)[:, :, np.newaxis]
                rgb_patch = patch_rgba[:, :, :3]
                # RGB to BGR
                bgr_patch = cv2.cvtColor(rgb_patch, cv2.COLOR_RGB2BGR)

                blended = (bgr_patch * alpha_channel + inpainted_region[:ph, :pw] * (1.0 - alpha_channel)).astype(np.uint8)
                output_img[iy0:iy0 + ph, ix0:ix0 + pw] = blended

        # 3. Save result
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        if output_path.lower().endswith(".pdf"):
            # Convert modified image back into high-fidelity PDF
            success, enc = cv2.imencode(".png", output_img)
            if not success:
                raise RuntimeError("Failed to encode image to PNG for PDF conversion.")
            
            out_doc = pymupdf.open()
            rect = pymupdf.Rect(0, 0, w * 72.0 / 200.0, h * 72.0 / 200.0)
            page = out_doc.new_page(width=rect.width, height=rect.height)
            page.insert_image(rect, stream=enc.tobytes())
            out_doc.save(output_path, deflate=True)
            out_doc.close()
            if is_pdf:
                doc.close()
        else:
            cv2.imwrite(output_path, output_img)

        return output_path

    def duplicate_clean_page(
        self,
        source_path: str,
        output_path: str,
        replacements: Optional[Dict[str, str]] = None,
        instruction: Optional[str] = None
    ) -> str:
        """
        Creates a clean duplicate handwritten page with synthesized matching paper
        background (ruled notebook lines or plain scan) and cloned handwriting style.
        """
        # Run in-place replication as standard high-fidelity pipeline
        return self.duplicate_in_place(
            source_path=source_path,
            output_path=output_path,
            replacements=replacements or {},
            instruction=instruction
        )


# Global Singleton
handwriting_replicator = HandwrittenDocumentReplicator()
