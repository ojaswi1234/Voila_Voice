import re

with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8') as f:
    text = f.read()

parser_addition = """
    if "STATUS: SYSTEM_MSG:" in line:
        if "falling back to" in line or "dynamically switching" in line or "trying secondary" in line:
            usage_stats['fallbacks'] = usage_stats.get('fallbacks', 0) + 1
        elif "REJECTED" in line:
            usage_stats['rejections'] = usage_stats.get('rejections', 0) + 1
        return

    if "STATUS: BACKEND:" in line:
        usage_stats['backend_status'] = line.split("STATUS: BACKEND:")[1].strip()
        return
        
    if "STATUS: MOBILE_CLIENTS:" in line:
        try:
            usage_stats['mobile_clients'] = int(line.split("STATUS: MOBILE_CLIENTS:")[1].strip())
        except: pass
        return
"""

if "usage_stats['backend_status']" not in text:
    text = text.replace('if "STATUS: CMD_DONE:FAILED" in line:', parser_addition + '\n    if "STATUS: CMD_DONE:FAILED" in line:')

with open('local-agent/run_hidden_agent.pyw', 'w', encoding='utf-8') as f:
    f.write(text)
