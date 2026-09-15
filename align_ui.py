import sys
import re

with open('local-agent/run_hidden_agent.pyw', 'r', encoding='utf-8') as f:
    text = f.read()

# Fix Groq Layout
groq_sec_key_label = "tk.Label(groq_frame, text='Sec Key:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(\n        row=1, column=0, padx=12, pady=4, sticky='w')"
groq_opt_label = "tk.Label(groq_frame, text='(Optional)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=2, column=3, sticky='w')"

# If it says row=2, column=3, we fix it to row=1, column=3 (so it aligns with Sec Key)
# BUT wait! earlier I did `text = text.replace("grid(row=1, column=3, sticky='w')", "grid(row=2, column=3, sticky='w')")` which affected ALL labels!
# Let's just fix them individually.

# 1. Fix Groq (Optional)
text = text.replace("tk.Label(groq_frame, text='(Optional)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=2, column=3, sticky='w')",
                    "tk.Label(groq_frame, text='(Optional)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=1, column=3, sticky='w')")

text = text.replace("tk.Label(groq_frame, text='(Optional)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=1, column=3, sticky='w')",
                    "tk.Label(groq_frame, text='(Optional)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=1, column=3, sticky='w')")


# 2. Fix Ollama Layout
# We need to find Ollama Model Label and change it to row 3
text = text.replace("tk.Label(ollama_frame, text='Model:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(\n        row=1, column=0, padx=12, pady=4, sticky='w')",
                    "tk.Label(ollama_frame, text='Model:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(\n        row=3, column=0, padx=12, pady=4, sticky='w')")

# We need to find Ollama API Key and change it to row 1
text = text.replace("tk.Label(ollama_frame, text='API Key (Opt):', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(\n        row=2, column=0, padx=12, pady=4, sticky='w')",
                    "tk.Label(ollama_frame, text='API Key (Opt):', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(\n        row=1, column=0, padx=12, pady=4, sticky='w')")

# And its entry:
text = text.replace(".grid(\n        row=2, column=1, columnspan=3, padx=6, pady=4, sticky='ew')",
                    ".grid(\n        row=1, column=1, columnspan=3, padx=6, pady=4, sticky='ew')")

# We need to find Ollama Sec Key and change it to row 2
text = text.replace("tk.Label(ollama_frame, text='Sec Key:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(\n        row=3, column=0, padx=12, pady=4, sticky='w')",
                    "tk.Label(ollama_frame, text='Sec Key:', bg='#1A1D23', fg='#9CA3AF', font=('Segoe UI', 9)).grid(\n        row=2, column=0, padx=12, pady=4, sticky='w')")
text = text.replace("ollama_sec_entry.grid(row=3, column=1, padx=6, pady=4, sticky='ew')",
                    "ollama_sec_entry.grid(row=2, column=1, padx=6, pady=4, sticky='ew')")
text = text.replace("tk.Label(ollama_frame, text='(Optional)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=3, column=2, sticky='w')",
                    "tk.Label(ollama_frame, text='(Optional)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=2, column=2, sticky='w')")

# And we need to find Ollama Model Combobox and Free Tier label and change to row 3
text = text.replace("ollama_model_cb.grid(row=4, column=1, columnspan=2, padx=6, pady=4, sticky='w')",
                    "ollama_model_cb.grid(row=3, column=1, columnspan=2, padx=6, pady=4, sticky='w')")
text = text.replace("tk.Label(ollama_frame, text='(Free tier + tool calling)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=4, column=3, sticky='w')",
                    "tk.Label(ollama_frame, text='(Free tier + tool calling)', bg='#1A1D23', fg='#6B7280', font=('Segoe UI', 8)).grid(row=3, column=3, sticky='w')")

with open('local-agent/run_hidden_agent.pyw', 'w', encoding='utf-8') as f:
    f.write(text)

print("Fixed all row alignments")
