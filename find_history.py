import os, json, glob
from datetime import datetime

brain_dir = r'C:\Users\ojasw\.gemini\antigravity-cli\brain'
transcripts = glob.glob(os.path.join(brain_dir, '**', 'transcript_full.jsonl'), recursive=True)

modifications = []

for fpath in transcripts:
    try:
        with open(fpath, 'r', encoding='utf-8') as f:
            for line in f:
                if 'run_hidden_agent' in line:
                    data = json.loads(line)
                    if data.get('type') == 'PLANNER_RESPONSE':
                        for tc in data.get('tool_calls', []):
                            tc_name = tc.get('function_name', '')
                            args = tc.get('function_args', {})
                            
                            is_mod = False
                            if tc_name in ['default_api:write_to_file', 'default_api:replace_file_content'] and 'run_hidden_agent' in args.get('TargetFile', ''):
                                is_mod = True
                            elif tc_name == 'default_api:run_command' and 'run_hidden_agent' in args.get('CommandLine', ''):
                                cmd = args.get('CommandLine', '')
                                if 'Out-File run_hidden_agent.pyw' in cmd or '> run_hidden_agent.pyw' in cmd or 'w' in cmd:
                                    is_mod = True
                                    
                            if is_mod:
                                created_at = data.get('created_at', '')
                                modifications.append((created_at, fpath, tc_name, args))
    except Exception as e:
        pass

modifications.sort(key=lambda x: x[0])
print(f'Found {len(modifications)} modifications to run_hidden_agent.pyw')
if modifications:
    current_session_id = '07683e77-e12d-475e-aea6-ce5cb1336fca'
    for mod in reversed(modifications):
        if current_session_id not in mod[1]:
            print('\\n=== LAST MOD BEFORE CURRENT SESSION ===')
            print(f'Time: {mod[0]}')
            print(f'File: {mod[1]}')
            print(f'Tool: {mod[2]}')
            if mod[2] == 'default_api:run_command':
                print(mod[3].get('CommandLine')[:500])
            else:
                print(mod[3].get('CodeContent', mod[3].get('ReplacementContent', ''))[:500])
            break
