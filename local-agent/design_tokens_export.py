import json, os
from design_tokens import THEMES

def export_tokens():
    # Export tokens.json
    out_dir = os.path.dirname(os.path.abspath(__file__))
    with open(os.path.join(out_dir, "tokens.json"), "w") as f:
        json.dump(THEMES, f, indent=2)

    # Export tokens.css
    css_content = ":root {\n"
    # we export default corporate_blue as root, but also theme classes
    for theme_name, theme_data in THEMES.items():
        css_content += f"  /* {theme_name} */\n"
        css_content += f"  .{theme_name} {{\n"
        for key, val in theme_data.items():
            if isinstance(val, tuple):
                css_content += f"    --{key.replace(\"_\", \"-\")}: rgb({val[0]}, {val[1]}, {val[2]});\n"
            elif isinstance(val, str):
                css_content += f"    --{key.replace(\"_\", \"-\")}: {val};\n"
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                css_content += f"    --{key.replace(\"_\", \"-\")}: {val};\n"
        css_content += "  }\n"
    
    # default body class mapping
    css_content += "}\n"
    
    with open(os.path.join(out_dir, "tokens.css"), "w") as f:
        f.write(css_content)

if __name__ == "__main__":
    export_tokens()

