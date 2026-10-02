with open(r"mobile-agent\lib\main.dart", "r", encoding="utf-8") as f:
    content = f.read()

lines = content.splitlines()
errors = []

# Check for lines that have if (mounted) immediately before a ")" or "," alone on next few tokens
# which would indicate it was prepended to an expression in a call site
import re
for i, line in enumerate(lines, 1):
    s = line.lstrip()
    # Case: "if (mounted) someIdentifier(" - this is a statement, OK
    # Case: "if (mounted) someIdentifier: " - this is a named param in a call, BROKEN
    # We already fixed "named:" above but check for other patterns like
    # "if (mounted) Widget(" -> this would mean if was prepended to a widget constructor used as an expression
    # e.g. "if (mounted) Text("hello")," - this could be inside a List context (children:[]) 
    # In a List/children context this is fine because Flutter supports if-as-collection-element
    # The problematic ones are only the "if (mounted) namedParam: value" patterns
    # (already fixed). Let us also ensure no "if (mounted) )" or "if (mounted) ," alone
    if re.match(r"^\s*if \(mounted\) [)},]", line):
        errors.append(f"L{i}: {line}")

if errors:
    print("SYNTAX ISSUES:")
    for e in errors:
        print(e)
else:
    print("No obvious structural issues found.")
    
# Count parens balance in just main function bodies - rough check
opens = content.count("{")
closes = content.count("}")
print(f"\nBrace balance: {{ = {opens}, }} = {closes}, diff = {opens - closes}")
