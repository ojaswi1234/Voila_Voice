import re

# Step 1: Read raw bytes
with open('local-agent/run_hidden_agent.pyw', 'rb') as f:
    raw = f.read()

# Step 2: Strip BOM if present
if raw.startswith(b'\xef\xbb\xbf'):
    raw = raw[3:]

# Step 3: Decode as UTF-8 (this gives us the mojibake string where 
#          multi-byte sequences appear as multiple latin1 chars)
text_mojibake = raw.decode('utf-8')

# Step 4: Fix the double encoding by re-encoding as latin-1 then decoding as utf-8
# This is the standard mojibake reversal
try:
    text_fixed = text_mojibake.encode('latin-1').decode('utf-8')
    print("Double-encoding fix applied successfully")
except (UnicodeDecodeError, UnicodeEncodeError) as e:
    print(f"Full fix failed ({e}), applying char-by-char repair...")
    # Fallback: fix char by char
    result = []
    i = 0
    chars = list(text_mojibake)
    while i < len(chars):
        c = chars[i]
        # Try to grab a sequence of latin-1 encodeable chars and decode as utf-8
        if ord(c) < 0x80:
            result.append(c)
            i += 1
        else:
            # Collect up to 4 bytes that look like a UTF-8 sequence
            seq = ''
            j = i
            while j < len(chars) and j < i + 6 and ord(chars[j]) <= 0xFF:
                seq += chars[j]
                j += 1
            try:
                decoded = seq.encode('latin-1').decode('utf-8')
                result.append(decoded)
                i = j
            except:
                result.append(c)
                i += 1
    text_fixed = ''.join(result)

# Step 5: Replace the specific broken symbols with clean readable equivalents
# Based on the audit report, the main offenders are:
REPLACEMENTS = {
    # Section dividers (long repeating ─ sequences)
    '\u2500': '\u2500',   # keep box drawing horizontal
    '\u2501': '\u2501',
    # Bullet points
    '\u2022': '\u2022',   # bullet
    # Close button X
    '\u2715': '\u2715',   # multiplication x (the close button ✕)
    '\u2717': '\u2717',
    '\u00d7': '\u00d7',  # × multiply
    # Arrows  
    '\u2192': '\u2192',
    '\u25b6': '\u25b6',
    # Mode labels - common icons that appear in MODE_LABELS dict
    # Robot emoji \U0001F916 → use "AI" text in Segoe UI
    '\U0001f916': '[AI]',
    '\U0001f4ca': '[GRAPH]',
    '\U0001f4bb': '[PC]',
    '\U0001f525': '[HOT]',
    '\U0001f50d': '[SEARCH]',
    # Star
    '\u2605': '*',
    '\u2728': '*',
    # Checkmark  
    '\u2713': 'OK',
    '\u2714': 'OK',
    # Cross
    '\u2718': 'X',
}

# Only apply text replacements for emoji that won't render in Segoe UI
# Segoe UI Emoji handles most modern emoji but NOT all box-drawing/special
for old, new in REPLACEMENTS.items():
    text_fixed = text_fixed.replace(old, new)

# Step 6: Write back as UTF-8-SIG
with open('local-agent/run_hidden_agent.pyw', 'w', encoding='utf-8-sig', newline='\r\n') as f:
    f.write(text_fixed)

print(f"Done. File re-saved ({len(text_fixed)} chars)")

# Verify - check a few key lines
lines = text_fixed.splitlines()
for i in [166, 168, 171, 358, 561]:
    if i < len(lines):
        print(f"  L{i+1}: {lines[i][:100]}")
