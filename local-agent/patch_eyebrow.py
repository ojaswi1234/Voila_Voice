import re
with open('C:/Users/ojasw/Desktop/Voila_Voice/local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Change create_arc to create_line
content = content.replace(
    "eyebrow_l = canvas.create_arc(sx+18, sy+20, sx+36, sy+28, start=0, extent=180, style=tk.ARC, width=2, outline=brown_dark)",
    "eyebrow_l = canvas.create_line(sx+16, sy+20, sx+36, sy+26, width=8, fill=brown_dark, capstyle=tk.PROJECTING)"
)
content = content.replace(
    "eyebrow_r = canvas.create_arc(sx+44, sy+20, sx+62, sy+28, start=0, extent=180, style=tk.ARC, width=2, outline=brown_dark)",
    "eyebrow_r = canvas.create_line(sx+64, sy+20, sx+44, sy+26, width=8, fill=brown_dark, capstyle=tk.PROJECTING)"
)

replacements = {
    # Base Idle
    'canvas.coords(eyebrow_l, sx+18, sy+20, sx+36, sy+28)': 'canvas.coords(eyebrow_l, sx+16, sy+20, sx+36, sy+26)',
    'canvas.coords(eyebrow_r, sx+44, sy+20, sx+62, sy+28)': 'canvas.coords(eyebrow_r, sx+64, sy+20, sx+44, sy+26)',

    # THINKING
    'canvas.coords(eyebrow_l, sx+18, sy+18+offset_y, sx+36, sy+26+offset_y)': 'canvas.coords(eyebrow_l, sx+16, sy+18+offset_y, sx+36, sy+24+offset_y)',
    'canvas.coords(eyebrow_r, sx+44, sy+18+offset_y, sx+62, sy+26+offset_y)': 'canvas.coords(eyebrow_r, sx+64, sy+18+offset_y, sx+44, sy+24+offset_y)',
    
    # SEARCH left
    'canvas.coords(eyebrow_l, sx+16, sy+22, sx+34, sy+20)': 'canvas.coords(eyebrow_l, sx+16, sy+24, sx+36, sy+24)',
    'canvas.coords(eyebrow_r, sx+42, sy+22, sx+60, sy+20)': 'canvas.coords(eyebrow_r, sx+64, sy+20, sx+44, sy+28)',
    
    # SEARCH right
    'canvas.coords(eyebrow_l, sx+20, sy+20, sx+38, sy+22)': 'canvas.coords(eyebrow_l, sx+16, sy+20, sx+36, sy+28)',
    'canvas.coords(eyebrow_r, sx+46, sy+20, sx+64, sy+22)': 'canvas.coords(eyebrow_r, sx+64, sy+24, sx+44, sy+24)',
    
    # SEARCH down
    'canvas.coords(eyebrow_l, sx+18, sy+22, sx+36, sy+30)': 'canvas.coords(eyebrow_l, sx+16, sy+24, sx+36, sy+28)',
    'canvas.coords(eyebrow_r, sx+44, sy+22, sx+62, sy+30)': 'canvas.coords(eyebrow_r, sx+64, sy+24, sx+44, sy+28)',

    # SEARCH up
    'canvas.coords(eyebrow_l, sx+18, sy+16, sx+36, sy+24)': 'canvas.coords(eyebrow_l, sx+16, sy+16, sx+36, sy+22)',
    'canvas.coords(eyebrow_r, sx+44, sy+16, sx+62, sy+24)': 'canvas.coords(eyebrow_r, sx+64, sy+16, sx+44, sy+22)',

    # BASH (furrowed)
    'canvas.coords(eyebrow_l, sx+18, sy+24, sx+36, sy+28)': 'canvas.coords(eyebrow_l, sx+16, sy+22, sx+36, sy+28)',
    'canvas.coords(eyebrow_r, sx+44, sy+24, sx+62, sy+28)': 'canvas.coords(eyebrow_r, sx+64, sy+22, sx+44, sy+28)',
    
    # FILE (focused)
    'canvas.coords(eyebrow_l, sx+18, sy+22, sx+36, sy+28)': 'canvas.coords(eyebrow_l, sx+16, sy+21, sx+36, sy+27)',
    'canvas.coords(eyebrow_r, sx+44, sy+22, sx+62, sy+28)': 'canvas.coords(eyebrow_r, sx+64, sy+21, sx+44, sy+27)',
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open('C:/Users/ojasw/Desktop/Voila_Voice/local-agent/run_hidden_agent.pyw', 'w', encoding='utf-8') as f:
    f.write(content)
print('Replaced')
