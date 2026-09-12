# Voila Document Design System

This file documents the available themes, design constraints, and structure guidelines for generating Voila output documents (PDF, PPTX, DOCX).

## Allowed Themes
- corporate_blue
- modern_dark
- cyberpunk
- light_minimal

## Type Scale
- Header 1 (Title): 40pt
- Header 2 (Section): 24pt
- Body text: 12pt
- Labels / Accents: 10pt (muted/accent color)

## Document & Slide Constraints
- Use the predefined JSON IR structure.
- Max 6 bullets per slide or section to avoid overcrowding.
- Forbidden: purple gradient slop, >6 bullets/slide, Inter-as-only-default, unevaluated code in content, emoji in formal reports, decorative lines with no meaning.
- All documents must render standard Unicode characters natively, e.g., ° (degree), en/em dashes, smart quotes. Do NOT replace with latin-1 equivalents or garbled text like Â°C.

