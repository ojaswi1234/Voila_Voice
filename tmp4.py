with open(r"mobile-agent\lib\main.dart", "r", encoding="utf-8") as f:
    lines = f.readlines()
for k in range(2350, 2400):
    print(f"{k}: {lines[k].rstrip()}")
