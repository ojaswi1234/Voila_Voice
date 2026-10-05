import sys

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

replacements = {
    "Icons.blur_on_rounded": "Icons.graphic_eq_rounded",
    "Icons.add_circle_outline": "Icons.add_circle_rounded",
    "Icons.folder_copy_outlined": "Icons.dashboard_customize_rounded",
    "Icons.security_outlined": "Icons.shield_rounded",
    "Icons.settings_outlined": "Icons.tune_rounded",
    "Icons.no_photography_outlined": "Icons.image_not_supported_rounded",
    "Icons.chat_bubble_outline_rounded": "Icons.chat_bubble_rounded",
}

for old, new in replacements.items():
    content = content.replace(old, new)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print("Icons updated.")
