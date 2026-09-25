import re

with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8') as f:
    text = f.read()

# Extract the entire function
pattern = re.compile(r'def _draw_analytics_section\(dc, w, h\):.*?(?=def _draw_settings_section\(dc, w, h\):)', re.DOTALL)

new_func = """def _draw_analytics_section(dc, w, h):
    # Calculate some derived stats
    success_rate = 0
    if usage_stats['commands_executed'] > 0:
        success_rate = int((usage_stats['commands_successful'] / usage_stats['commands_executed']) * 100)
    session_duration = int((time.time() - usage_stats['session_start']) / 60)
    cpm = int(usage_stats['commands_executed'] / max(0.1, (time.time() - usage_stats['session_start']) / 60.0))
    
    # Grid Layout
    margin = 15
    col_w = (w - (margin * 3)) // 2
    y_start = 10
    
    # ---------------------------------------------------------
    # LEFT COLUMN: CHARTS & GRAPHS
    # ---------------------------------------------------------
    left_x = margin
    
    # 1. SCATTERPLOT: Latency Distribution
    sc_y = y_start
    sc_h = 160
    dc.create_text(left_x, sc_y, text='LATENCY SCATTERPLOT (ms)', fill='#9CA3AF', font=('Segoe UI', 10, 'bold'), anchor='nw')
    dc.create_rectangle(left_x, sc_y + 20, left_x + col_w, sc_y + 20 + sc_h, fill='#1A1D23', outline='#2A2D35')
    
    t_data = usage_stats.get('timeline_data', [])
    if t_data:
        max_ms = max(5000, max(t_data))
        pt_w = col_w / max(1, len(t_data))
        for i, ms in enumerate(t_data):
            px = left_x + (i * pt_w) + (pt_w/2)
            py = (sc_y + 20 + sc_h) - ((ms / max_ms) * (sc_h - 20)) - 10
            # Draw point
            color = '#10B981' if ms < 1500 else ('#F59E0B' if ms < 3000 else '#EF4444')
            dc.create_oval(px-3, py-3, px+3, py+3, fill=color, outline='#FFFFFF')
            # Connect line if not first
            if i > 0:
                prev_ms = t_data[i-1]
                prev_px = left_x + ((i-1) * pt_w) + (pt_w/2)
                prev_py = (sc_y + 20 + sc_h) - ((prev_ms / max_ms) * (sc_h - 20)) - 10
                dc.create_line(prev_px, prev_py, px, py, fill='#4B5563', dash=(2, 2))
    else:
        dc.create_text(left_x + col_w//2, sc_y + 20 + sc_h//2, text="No telemetry data", fill='#4B5563', font=('Segoe UI', 10))

    # 2. BAR CHART: Tool Execution
    bar_y = sc_y + sc_h + 40
    bar_h = 160
    dc.create_text(left_x, bar_y, text='TOOL EXECUTION DISTRIBUTION', fill='#9CA3AF', font=('Segoe UI', 10, 'bold'), anchor='nw')
    dc.create_rectangle(left_x, bar_y + 20, left_x + col_w, bar_y + 20 + bar_h, fill='#1A1D23', outline='#2A2D35')
    
    tools = sorted(usage_stats.get('tools_used', {}).items(), key=lambda x: x[1], reverse=True)[:5]
    if tools:
        max_t = max([t[1] for t in tools])
        bw = (col_w - 20) / len(tools)
        for i, (tool, count) in enumerate(tools):
            bx = left_x + 10 + (i * bw)
            bh = (count / max_t) * (bar_h - 40)
            by = (bar_y + 20 + bar_h) - bh - 20
            dc.create_rectangle(bx + 10, by, bx + bw - 10, bar_y + 20 + bar_h - 20, fill='#3B82F6', outline='')
            # Label
            lbl = tool[:7] + '..' if len(tool) > 9 else tool
            dc.create_text(bx + bw/2, bar_y + 20 + bar_h - 10, text=lbl, fill='#9CA3AF', font=('Segoe UI', 8), anchor='center')
            dc.create_text(bx + bw/2, by - 10, text=str(count), fill='#E5E7EB', font=('Segoe UI', 8, 'bold'), anchor='center')
    else:
        dc.create_text(left_x + col_w//2, bar_y + 20 + bar_h//2, text="No tool data", fill='#4B5563', font=('Segoe UI', 10))

    # 3. DONUT CHART: Success vs Fail
    donut_y = bar_y + bar_h + 40
    dc.create_text(left_x, donut_y, text='COMMAND RELIABILITY', fill='#9CA3AF', font=('Segoe UI', 10, 'bold'), anchor='nw')
    
    succ = usage_stats['commands_successful']
    fail = usage_stats['commands_failed']
    total = succ + fail
    
    if total > 0:
        succ_deg = (succ / total) * 360
        dc.create_arc(left_x + 30, donut_y + 30, left_x + 110, donut_y + 110, start=90, extent=succ_deg, fill='#10B981', outline='')
        dc.create_arc(left_x + 30, donut_y + 30, left_x + 110, donut_y + 110, start=90+succ_deg, extent=360-succ_deg, fill='#EF4444', outline='')
        # Inner hole
        dc.create_oval(left_x + 50, donut_y + 50, left_x + 90, donut_y + 90, fill='#0F1115', outline='')
        dc.create_text(left_x + 70, donut_y + 70, text=f"{success_rate}%", fill='#E5E7EB', font=('Segoe UI', 10, 'bold'), anchor='center')
    
    # ---------------------------------------------------------
    # RIGHT COLUMN: CARDS & STATS
    # ---------------------------------------------------------
    right_x = margin * 2 + col_w
    
    # API Backend Health Card
    c1_y = y_start
    c1_h = 100
    dc.create_text(right_x, c1_y, text='BACKEND API CLUSTER', fill='#9CA3AF', font=('Segoe UI', 10, 'bold'), anchor='nw')
    dc.create_rectangle(right_x, c1_y + 20, right_x + col_w, c1_y + 20 + c1_h, fill='#1A1D23', outline='#2A2D35')
    
    b_stat = usage_stats.get('backend_status', 'OFFLINE')
    b_color = '#10B981' if b_stat == 'ONLINE' else '#EF4444'
    dc.create_text(right_x + 15, c1_y + 40, text="API Status:", fill='#6B7280', font=('Segoe UI', 10), anchor='w')
    dc.create_text(right_x + col_w - 15, c1_y + 40, text=b_stat, fill=b_color, font=('Segoe UI', 10, 'bold'), anchor='e')
    
    m_cli = usage_stats.get('mobile_clients', 0)
    dc.create_text(right_x + 15, c1_y + 70, text="Connected Mobile Apps:", fill='#6B7280', font=('Segoe UI', 10), anchor='w')
    dc.create_text(right_x + col_w - 15, c1_y + 70, text=str(m_cli), fill='#3B82F6', font=('Segoe UI', 12, 'bold'), anchor='e')
    
    dc.create_text(right_x + 15, c1_y + 100, text="Bridge Port:", fill='#6B7280', font=('Segoe UI', 10), anchor='w')
    dc.create_text(right_x + col_w - 15, c1_y + 100, text="19882 (UDP)", fill='#E5E7EB', font=('Segoe UI', 10), anchor='e')

    # Graphify Engine Card
    c2_y = c1_y + c1_h + 40
    c2_h = 100
    dc.create_text(right_x, c2_y, text='GRAPHIFY ORCHESTRATION', fill='#9CA3AF', font=('Segoe UI', 10, 'bold'), anchor='nw')
    dc.create_rectangle(right_x, c2_y + 20, right_x + col_w, c2_y + 20 + c2_h, fill='#1A1D23', outline='#2A2D35')
    
    mode = usage_stats.get('active_mode', 'IDLE')
    dc.create_text(right_x + 15, c2_y + 40, text="Active Engine Mode:", fill='#6B7280', font=('Segoe UI', 10), anchor='w')
    dc.create_text(right_x + col_w - 15, c2_y + 40, text=mode, fill='#ec4899', font=('Segoe UI', 10, 'bold'), anchor='e')
    
    fallbacks = usage_stats.get('fallbacks', 0)
    dc.create_text(right_x + 15, c2_y + 70, text="Dynamic LLM Fallbacks:", fill='#6B7280', font=('Segoe UI', 10), anchor='w')
    dc.create_text(right_x + col_w - 15, c2_y + 70, text=str(fallbacks), fill='#F59E0B' if fallbacks > 0 else '#E5E7EB', font=('Segoe UI', 12, 'bold'), anchor='e')

    rejections = usage_stats.get('rejections', 0)
    dc.create_text(right_x + 15, c2_y + 100, text="Team Debates / Rejections:", fill='#6B7280', font=('Segoe UI', 10), anchor='w')
    dc.create_text(right_x + col_w - 15, c2_y + 100, text=str(rejections), fill='#3B82F6', font=('Segoe UI', 12, 'bold'), anchor='e')

    # Performance & Context Matrix
    c3_y = c2_y + c2_h + 40
    c3_h = 100
    dc.create_text(right_x, c3_y, text='SYSTEM MATRIX', fill='#9CA3AF', font=('Segoe UI', 10, 'bold'), anchor='nw')
    dc.create_rectangle(right_x, c3_y + 20, right_x + col_w, c3_y + 20 + c3_h, fill='#1A1D23', outline='#2A2D35')
    
    dc.create_text(right_x + 15, c3_y + 40, text="Average Latency:", fill='#6B7280', font=('Segoe UI', 10), anchor='w')
    dc.create_text(right_x + col_w - 15, c3_y + 40, text=f"{usage_stats['avg_latency_ms']}ms", fill='#E5E7EB', font=('Segoe UI', 10, 'bold'), anchor='e')

    dc.create_text(right_x + 15, c3_y + 70, text="Context Cache Hits:", fill='#6B7280', font=('Segoe UI', 10), anchor='w')
    dc.create_text(right_x + col_w - 15, c3_y + 70, text="Optimized (VRAM)", fill='#10B981', font=('Segoe UI', 10, 'bold'), anchor='e')

    dc.create_text(right_x + 15, c3_y + 100, text="Session Uptime:", fill='#6B7280', font=('Segoe UI', 10), anchor='w')
    dc.create_text(right_x + col_w - 15, c3_y + 100, text=f"{session_duration}m", fill='#E5E7EB', font=('Segoe UI', 10, 'bold'), anchor='e')

"""

text = pattern.sub(new_func, text)

with open('local-agent/run_hidden_agent.pyw', 'w', encoding='utf-8') as f:
    f.write(text)
