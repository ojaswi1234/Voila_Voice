import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

logoArt = '''logoArt = `
██╗   ██╗              ██╗██╗       
██║   ██║  ██████╗     ██║██║      
██║   ██║  ██╔═══██╗    ██║██║      
╚██████╔╝  ██║   ██║██████║██║█████╗
 ╚████╔╝   ╚██████╔╝╚════██║██║╚════╝
  ╚═══╝     ╚═════╝      ╚═╝╚═╝     

       ━ ZERO TRUST ━ SECURE ━ FAST ━
`'''

connectedArt = '''connectedArt = `
╭──────────────────────────────────────────╮
│    🟢 CONNECTION ESTABLISHED             │
│    ⚡ READY TO EXECUTE COMMANDS         │
╰──────────────────────────────────────────╯
`'''

menuArt = '''menuArt = `
╭──────────────────────────────────────────╮
│                 MAIN MENU                │
╰──────────────────────────────────────────╯
`'''

footerArt = '''footerArt = `
╭───────────────────────────────────────────────────────╮
│  Voice-to-CLI Remote Execution System                 │
│  Zero Trust | Multi-Device | Secure                   │
│  v1.0.0 | ⚡ Fast | 🔒 Secure                         │
╰───────────────────────────────────────────────────────╯
`'''

statusOnline = '''statusOnline = `
╭───────────────────────────────────────────────────────╮
│  🟢 ONLINE - CONNECTED - LISTENING:8088               │
╰───────────────────────────────────────────────────────╯
`'''

statusOffline = '''statusOffline = `
╭───────────────────────────────────────────────────────╮
│  🔴 OFFLINE - WAITING FOR CONNECTION                  │
╰───────────────────────────────────────────────────────╯
`'''

separatorLine = '''separatorLine = "────────────────────────────────────────────────────────"'''

text = re.sub(r'logoArt = `.*?`', logoArt, text, flags=re.DOTALL)
text = re.sub(r'connectedArt = `.*?`', connectedArt, text, flags=re.DOTALL)
text = re.sub(r'menuArt = `.*?`', menuArt, text, flags=re.DOTALL)
text = re.sub(r'footerArt = `.*?`', footerArt, text, flags=re.DOTALL)
text = re.sub(r'statusOnline = `.*?`', statusOnline, text, flags=re.DOTALL)
text = re.sub(r'statusOffline = `.*?`', statusOffline, text, flags=re.DOTALL)
text = re.sub(r'separatorLine = ".*?"', separatorLine, text, flags=re.DOTALL)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)
