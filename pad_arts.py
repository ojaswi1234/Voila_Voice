import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

def make_rectangular(art_str):
    lines = art_str.strip('\n').split('\n')
    max_len = max(len(line.rstrip()) for line in lines) if lines else 0
    padded_lines = [line.rstrip().ljust(max_len) for line in lines]
    return '\n' + '\n'.join(padded_lines) + '\n'

logoArt = '''
██╗   ██╗              ██╗██╗
██║   ██║  ██████╗     ██║██║
██║   ██║  ██╔═══██╗    ██║██║
╚██████╔╝  ██║   ██║██████║██║█████╗
 ╚████╔╝   ╚██████╔╝╚════██║██║╚════╝
  ╚═══╝     ╚═════╝      ╚═╝╚═╝

       ━ ZERO TRUST ━ SECURE ━ FAST ━
'''

connectedArt = '''
╭──────────────────────────────────────────╮
│    🟢 CONNECTION ESTABLISHED             │
│    ⚡ READY TO EXECUTE COMMANDS          │
╰──────────────────────────────────────────╯
'''

menuArt = '''
╭──────────────────────────────────────────╮
│                 MAIN MENU                │
╰──────────────────────────────────────────╯
'''

footerArt = '''
╭──────────────────────────────────────────────────────╮
│  Voice-to-CLI Remote Execution System                │
│  Zero Trust | Multi-Device | Secure                  │
│  v1.0.0 | ⚡ Fast | 🔒 Secure                        │
╰──────────────────────────────────────────────────────╯
'''

statusOnline = '''
╭──────────────────────────────────────────────────────╮
│  🟢 ONLINE - CONNECTED - LISTENING:8088              │
╰──────────────────────────────────────────────────────╯
'''

statusOffline = '''
╭──────────────────────────────────────────────────────╮
│  🔴 OFFLINE - WAITING FOR CONNECTION                 │
╰──────────────────────────────────────────────────────╯
'''

separatorLine = "───────────────────────────────────────────────────────────────────────"

def replace_art(name, content):
    global text
    padded = make_rectangular(content.strip('\n'))
    replacement = f"{name} = `{padded}`"
    text = re.sub(f"{name} = `.*?`", replacement, text, flags=re.DOTALL)

replace_art('logoArt', logoArt)
replace_art('connectedArt', connectedArt)
replace_art('menuArt', menuArt)
replace_art('footerArt', footerArt)
replace_art('statusOnline', statusOnline)
replace_art('statusOffline', statusOffline)
text = re.sub(r'separatorLine = ".*?"', f'separatorLine = "{separatorLine}"', text, flags=re.DOTALL)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
