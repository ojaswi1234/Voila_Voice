import sys
import re

with open('mobile-agent/lib/artifacts_page.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Change default status to completed
content = content.replace("this.status = 'pending',", "this.status = 'completed',")

# 2. Remove the Approve/Reject buttons from the bottom of ArtifactDetailPage
# Locate the block: if (artifact.status == 'pending')
start = content.find("if (artifact.status == 'pending')")
if start != -1:
    # Find the end of the Scaffold's body column
    # It's at the end of the file.
    # We can just use a regex to remove everything from if (artifact.status == 'pending') up to the end of the Column
    pattern = r"if\s*\(artifact\.status\s*==\s*'pending'\).*?,\s*\]\,\s*\)\,\s*\)\;\s*\}\s*\}"
    content = re.sub(pattern, "        ],\n      ),\n    );\n  }\n}", content, flags=re.DOTALL)


with open('mobile-agent/lib/artifacts_page.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print("Artifact approval buttons removed.")
