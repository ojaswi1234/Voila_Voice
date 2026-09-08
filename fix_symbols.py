import re

# Read the raw bytes and decode correctly
with open('local-agent/run_hidden_agent.pyw', 'rb') as f:
    raw = f.read()

# The file has BOM and is UTF-8, but somewhere the bytes got double-encoded.
# Try decoding as latin-1 then re-encoding as utf-8 to fix mojibake:
try:
    # This is the classic mojibake fix: the file was read as latin-1 and saved,
    # so we need to re-encode as latin-1 then decode as utf-8
    fixed = raw.decode('utf-8-sig')
    print("File decoded cleanly as UTF-8-SIG")
except UnicodeDecodeError:
    # Some bytes are raw latin-1 encoded UTF-8 sequences
    fixed = raw.decode('latin-1').encode('latin-1').decode('utf-8')
    print("Applied mojibake fix")

# Now remap all Unicode symbols to safe, clean equivalents that Segoe UI Emoji can render
replacements = {
    # Decorative separators (em-dash sequences used as dividers)
    '\u2500': '-',   # box drawing
    '\u2501': '-',
    '\u2502': '|',
    '\u2503': '|',
    '\u2550': '=',
    '\u2551': '|',
    '\u2014': ' - ',  # em dash
    '\u2013': '-',    # en dash
    '\u2015': '-',
    '\u2500\u2500': '--',
    # Checkmarks / crosses  
    '\u2714': '[OK]',
    '\u2718': '[X]',
    '\u2717': '[X]',
    '\u2713': '[v]',
    '\u2715': 'x',
    '\u2716': 'X',
    '\u2796': '-',
    '\u2795': '+',
    # Arrows
    '\u27a4': '->',
    '\u25b6': '>',
    '\u25c0': '<',
    '\u25b2': '^',
    '\u25bc': 'v',
    '\u21d2': '=>',
    '\u2192': '->',
    '\u2190': '<-',
    '\u2191': '^',
    '\u2193': 'v',
    # Circles / dots
    '\u25cf': '*',
    '\u25cb': 'o',
    '\u2022': '*',
    '\u00b7': '.',
    # Quotes
    '\u2018': "'",
    '\u2019': "'",
    '\u201c': '"',
    '\u201d': '"',
    '\u2039': '<',
    '\u203a': '>',
    # Stars / misc
    '\u2605': '*',
    '\u2606': '*',
    '\u2728': '*',
    '\u26a1': '!',
    # Emoji (replace with text equivalents)
    '\U0001f916': '[AI]',   # robot face
    '\U0001f4ca': '[Chart]', # bar chart
    '\U0001f4bb': '[PC]',    # laptop
    '\U0001f50d': '[Search]',# magnifier
    '\U0001f4c1': '[Folder]',# folder
    '\u2699': '[Gear]',      # gear
    '\U0001f4e1': '[Signal]',# satellite
    '\U0001f7e2': '[ON]',    # green circle
    '\U0001f534': '[OFF]',   # red circle
    '\U0001f7e1': '[WARN]',  # yellow circle
    '\u26ab': '[o]',
    '\u2b24': '[*]',
    # Lines used as section separators 
    '\u2500' * 30: '-' * 30,
    '\u2501' * 30: '=' * 30,
}

for old, new in replacements.items():
    fixed = fixed.replace(old, new)

# Write back as UTF-8-SIG (with BOM, which is what the file originally had)
with open('local-agent/run_hidden_agent.pyw', 'w', encoding='utf-8-sig') as f:
    f.write(fixed)

print("Done. File re-saved with clean symbol mappings.")
print(f"File size: {len(fixed)} chars")
