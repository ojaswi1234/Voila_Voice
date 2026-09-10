"""
Adjust text-box Y positions in document_tools.py to clear the new
top accent bar (0.075 inch).  Old design had a left bar so X offsets
were tuned; new design has a top bar so we need Y + 0.10 headroom.
"""
BAR_OFFSET = 0.10   # inches of extra vertical padding inside card

with open('local-agent/document_tools.py', 'r', encoding='utf-8') as f:
    src = f.read()

# ── content slide ─────────────────────────────────────────────────────────────
# Card top = 1.75", content textbox top was 1.9" (0.15" below card)
# After top bar we want  card.top(1.75) + bar(0.075) + pad(0.10) = 1.925"
src = src.replace(
    '_add_card(slide, Inches(0.4), Inches(1.75), Inches(9.2), Inches(5.15))\n'
    '            body_box = slide.shapes.add_textbox(Inches(0.65), Inches(1.9), Inches(8.8), Inches(4.9))',
    '_add_card(slide, Inches(0.4), Inches(1.75), Inches(9.2), Inches(5.15))\n'
    '            body_box = slide.shapes.add_textbox(Inches(0.62), Inches(1.98), Inches(8.85), Inches(4.75))'
)

# ── quote slide ───────────────────────────────────────────────────────────────
# Card top = 2.0", text was 2.2" → should be 2.0+0.075+0.10 = 2.18"
src = src.replace(
    '_add_card(slide, Inches(1.2), Inches(2.0), Inches(7.6), Inches(3.2))\n'
    '            q_box = slide.shapes.add_textbox(Inches(1.5), Inches(2.2), Inches(7.0), Inches(2.8))',
    '_add_card(slide, Inches(1.2), Inches(2.0), Inches(7.6), Inches(3.2))\n'
    '            q_box = slide.shapes.add_textbox(Inches(1.45), Inches(2.22), Inches(7.1), Inches(2.72))'
)

# ── metrics slide: value textbox ─────────────────────────────────────────────
# card top = top_y (Inches(1.9)), value text was top_y+0.35 → top_y+0.45
src = src.replace(
    'card_left + Inches(0.15), top_y + Inches(0.35), card_w - Inches(0.25), Inches(1.8))',
    'card_left + Inches(0.15), top_y + Inches(0.45), card_w - Inches(0.25), Inches(1.7))'
)
# label text was top_y+2.15 → top_y+2.20
src = src.replace(
    'card_left + Inches(0.15), top_y + Inches(2.15), card_w - Inches(0.25), Inches(1.0))',
    'card_left + Inches(0.15), top_y + Inches(2.22), card_w - Inches(0.25), Inches(0.9))'
)

# ── agenda: item text ────────────────────────────────────────────────────────
# row card top = row_top, item text was row_top+0.12 → row_top+0.17
src = src.replace(
    'item_box = slide.shapes.add_textbox(Inches(1.65), int(row_top + Inches(0.12)), Inches(7.6), row_h - Inches(0.18))',
    'item_box = slide.shapes.add_textbox(Inches(1.65), int(row_top + Inches(0.17)), Inches(7.6), row_h - Inches(0.22))'
)

with open('local-agent/document_tools.py', 'w', encoding='utf-8') as f:
    f.write(src)

print("Patch applied.")
