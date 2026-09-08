# Shared design tokens for document generation
# Ensures visual consistency across DOCX, PDF, and PPTX formats

THEMES = {
    "corporate_blue": {
        "font_heading": "Segoe UI",
        "font_body": "Georgia",
        "pdf_font_heading": "Helvetica",  # FPDF core font mapping
        "pdf_font_body": "Times",        # FPDF core font mapping
        "color_primary": (16, 42, 67),      # Dark blue
        "color_accent": (36, 59, 83),       # Medium blue  
        "color_text": (51, 78, 104),        # Blue-gray
        "color_heading": (255, 110, 64),    # Orange accent
        "spacing_unit": 0.5,                # Base spacing unit
    },
    "cyberpunk": {
        "font_heading": "Segoe UI",
        "font_body": "Georgia",
        "pdf_font_heading": "Helvetica",  # FPDF core font mapping
        "pdf_font_body": "Times",        # FPDF core font mapping
        "color_primary": (13, 2, 8),        # Dark purple-black
        "color_accent": (255, 0, 85),       # Neon pink
        "color_text": (220, 220, 220),      # Light gray
        "color_heading": (0, 255, 204),     # Cyan
        "spacing_unit": 0.5,
    },
    "minimalist": {
        "font_heading": "Segoe UI",
        "font_body": "Georgia",
        "pdf_font_heading": "Helvetica",  # FPDF core font mapping
        "pdf_font_body": "Times",        # FPDF core font mapping
        "color_primary": (0, 0, 0),         # Black
        "color_accent": (200, 200, 200),    # Light gray
        "color_text": (100, 100, 100),      # Medium gray
        "color_heading": (0, 0, 0),         # Black
        "spacing_unit": 0.5,
    },
    "modern_dark": {
        "font_heading": "Segoe UI",
        "font_body": "Georgia",
        "pdf_font_heading": "Helvetica",  # FPDF core font mapping
        "pdf_font_body": "Times",        # FPDF core font mapping
        "color_primary": (30, 30, 36),      # Dark gray
        "color_accent": (255, 110, 64),     # Orange
        "color_text": (200, 200, 200),     # Light gray
        "color_heading": (255, 255, 255),   # White
        "spacing_unit": 0.5,
    },
}

def get_theme(theme_name="modern_dark"):
    """Get theme dictionary, default to modern_dark if not found."""
    return THEMES.get(theme_name, THEMES["modern_dark"])