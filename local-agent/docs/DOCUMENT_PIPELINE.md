# Voila Document Pipeline

## Architecture Overview
The Voila Document Pipeline converts structured Design IR (JSON) into formatted PDF, PPTX, and DOCX documents.
The pipeline follows a strict separation of concerns:

1. **Agent / LLM** -> generates **Design IR** (JSON)
2. **Sanitize / Normalize** -> `normalize_ir()` strips un-evaluated shell commands, fixes unicode mojibake (e.g. replacing `Â°` with `°`), and injects real timestamps into `meta.generated_at`.
3. **Renderers** -> 
   - **PDF**: Uses Jinja2 templates + `tokens.css` rendered via `weasyprint` (primary).
   - **PPTX**: Uses `python-pptx` with predefined masters mapped from IR slides.
   - **DOCX**: Uses `python-docx` mapped from IR sections.

## Design IR
See WP2 specs.

## Security
No shell commands or eval-able templates are written into the final documents.
