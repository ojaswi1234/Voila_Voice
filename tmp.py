with open(r"mobile-agent\android\app\src\main\AndroidManifest.xml", "r", encoding="utf-8") as f:
    text = f.read()

import re
text = re.sub(r'android:name=".*?"', 'android:name="${applicationName}"', text, count=1)

with open(r"mobile-agent\android\app\src\main\AndroidManifest.xml", "w", encoding="utf-8") as f:
    f.write(text)
