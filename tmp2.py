with open(r"mobile-agent\lib\main.dart", "r", encoding="utf-8") as f:
    lines = f.readlines()
for k in range(3275, 3300):
    print(f"{k}: {lines[k].rstrip()}")
