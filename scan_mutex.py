import os, glob, re

for file in glob.glob("local-agent/*.go") + ["main.go"]:
    with open(file, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # We want to find functions that have a Lock() but might miss an Unlock()
    functions = re.finditer(r'func\s+[^{]+\{', content)
    starts = [m.end() for m in functions]
    
    # Simple check: count Lock() vs Unlock() in the file. 
    locks = len(re.findall(r'\.Lock\(\)', content))
    unlocks = len(re.findall(r'\.Unlock\(\)', content))
    rlocks = len(re.findall(r'\.RLock\(\)', content))
    runlocks = len(re.findall(r'\.RUnlock\(\)', content))
    
    if locks != unlocks or rlocks != runlocks:
        print(f"{file}: Mismatch! Lock:{locks} Unlock:{unlocks} | RLock:{rlocks} RUnlock:{runlocks}")
