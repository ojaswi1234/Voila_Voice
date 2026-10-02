# Check where the subagent put the marketplace and connectors files
import os
for root, dirs, files in os.walk(r"local-agent"):
    for f in files:
        if f in ("marketplace.go", "connectors.go", "connectors_test.go", "marketplace_test.go"):
            print(os.path.join(root, f))
