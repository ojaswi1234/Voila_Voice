import re

with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Update usage_stats definition
text = text.replace(
    "'timeline_data': []\n}",
    "'timeline_data': [],\n    'tools_used': {},\n    'active_mode': 'IDLE'\n}"
)

# 2. Add log parsing for tools and modes
log_parser_hook = """
    if "STATUS: CMD_DONE:FAILED" in line:
"""
new_parsers = """
    if "STATUS: TOOL:" in line:
        try:
            tool = line.split("STATUS: TOOL:")[1].strip()
            usage_stats["tools_used"][tool] = usage_stats["tools_used"].get(tool, 0) + 1
        except: pass
        return

    if "STATUS: MODE:" in line:
        try:
            usage_stats["active_mode"] = line.split("STATUS: MODE:")[1].strip()
        except: pass
        # do not return, let it fall through for other logic if needed
"""
if "STATUS: TOOL:" not in text:
    text = text.replace(log_parser_hook, new_parsers + log_parser_hook)

# 3. Rewrite Detailed Statistics section
old_stats = """    # Detailed stats
    stats_y = timeline_y + 20 + timeline_h + 20
    dc.create_text(10, stats_y, text='Detailed Statistics', fill='#888888', font=('Segoe UI', 10, 'bold'), anchor='w')
    
    dc.create_rectangle(10, stats_y + 20, w - 10, stats_y + 120, fill='#1A1D23', outline='#2A2D35')
    
    dc.create_text(24, stats_y + 40, text=f"Successful: {usage_stats['commands_successful']}", fill='#10B981', font=('Segoe UI', 11), anchor='w')
    dc.create_text(24, stats_y + 65, text=f"Failed: {usage_stats['commands_failed']}", fill='#EF4444', font=('Segoe UI', 11), anchor='w')
    dc.create_text(24, stats_y + 90, text=f"Commands/min: {commands_per_min}", fill='#6B7280', font=('Segoe UI', 11), anchor='w')
    dc.create_text(w - 24, stats_y + 40, text=f"Session: {session_duration}m", fill='#6B7280', font=('Segoe UI', 11), anchor='e')
    dc.create_text(w - 24, stats_y + 65, text=f"Peak/min: {usage_stats['peak_commands_per_min']}", fill='#6B7280', font=('Segoe UI', 11), anchor='e')"""

new_stats = """    # Deep Telemetry Grid
    stats_y = timeline_y + 20 + timeline_h + 20
    dc.create_text(10, stats_y, text='Deep Telemetry', fill='#888888', font=('Segoe UI', 10, 'bold'), anchor='w')
    
    # Left Box: Tool Distribution
    left_w = (w - 30) // 2
    dc.create_rectangle(10, stats_y + 20, 10 + left_w, stats_y + 140, fill='#1A1D23', outline='#2A2D35')
    dc.create_text(24, stats_y + 35, text="Tool Distribution (Top 4)", fill='#6B7280', font=('Segoe UI', 9, 'bold'), anchor='w')
    
    tools = sorted(usage_stats.get('tools_used', {}).items(), key=lambda x: x[1], reverse=True)
    if not tools:
        dc.create_text(24, stats_y + 65, text="No tools executed yet.", fill='#4B5563', font=('Segoe UI', 10, 'italic'), anchor='w')
    else:
        for i, (tool, count) in enumerate(tools[:4]):
            y_offset = stats_y + 60 + (i * 20)
            dc.create_text(24, y_offset, text=f"{tool}", fill='#9CA3AF', font=('Segoe UI', 10), anchor='w')
            dc.create_text(10 + left_w - 15, y_offset, text=str(count), fill='#ec4899', font=('Segoe UI', 10, 'bold'), anchor='e')

    # Right Box: Session Status
    right_x = 20 + left_w
    dc.create_rectangle(right_x, stats_y + 20, w - 10, stats_y + 140, fill='#1A1D23', outline='#2A2D35')
    dc.create_text(right_x + 14, stats_y + 35, text="Engine Health", fill='#6B7280', font=('Segoe UI', 9, 'bold'), anchor='w')
    
    total_tools = sum(usage_stats.get('tools_used', {}).values())
    mode_color = '#10B981' if usage_stats.get('active_mode', 'IDLE') != 'IDLE' else '#F59E0B'
    
    dc.create_text(right_x + 14, stats_y + 60, text=f"Total Sub-Tools Fired:", fill='#9CA3AF', font=('Segoe UI', 10), anchor='w')
    dc.create_text(w - 24, stats_y + 60, text=str(total_tools), fill='#3B82F6', font=('Segoe UI', 10, 'bold'), anchor='e')
    
    dc.create_text(right_x + 14, stats_y + 85, text=f"Active Orchestrator:", fill='#9CA3AF', font=('Segoe UI', 10), anchor='w')
    dc.create_text(w - 24, stats_y + 85, text=usage_stats.get('active_mode', 'IDLE'), fill=mode_color, font=('Segoe UI', 10, 'bold'), anchor='e')
    
    dc.create_text(right_x + 14, stats_y + 110, text=f"Session Uptime:", fill='#9CA3AF', font=('Segoe UI', 10), anchor='w')
    dc.create_text(w - 24, stats_y + 110, text=f"{session_duration}m", fill='#E5E7EB', font=('Segoe UI', 10, 'bold'), anchor='e')"""

text = text.replace(old_stats, new_stats)

with open('local-agent/run_hidden_agent.pyw', 'w', encoding='utf-8') as f:
    f.write(text)
