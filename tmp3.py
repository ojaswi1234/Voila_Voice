with open(r"mobile-agent\lib\main.dart", "r", encoding="utf-8") as f:
    lines = f.readlines()
for k in range(3470, 3495):
    print(f"{k}: {lines[k].rstrip()}")
