import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

collapsible_widget = """class CollapsibleOutput extends StatefulWidget {
  final String text;
  final TextStyle style;

  const CollapsibleOutput({super.key, required this.text, required this.style});

  @override
  State<CollapsibleOutput> createState() => _CollapsibleOutputState();
}

class _CollapsibleOutputState extends State<CollapsibleOutput> {
  bool _isExpanded = false;

  @override
  Widget build(BuildContext context) {
    final lines = widget.text.split('\\n');
    final isLong = lines.length > 15;
    final displayText = (!_isExpanded && isLong) ? lines.take(15).join('\\n') + '\\n...' : widget.text;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SelectableText(
          displayText,
          style: widget.style,
        ),
        if (isLong)
          TextButton(
            onPressed: () {
              setState(() {
                _isExpanded = !_isExpanded;
              });
            },
            style: TextButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 8),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: Text(
              _isExpanded ? 'Collapse' : 'Expand',
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
            ),
          ),
      ],
    );
  }
}
"""

# Insert widget at the bottom of the file
content = content + "\n\n" + collapsible_widget

# Replace SelectableText with CollapsibleOutput inside _buildMessageCard
old_text = """                child: SelectableText(
                  content,
                  style: GoogleFonts.firaCode(
                    fontSize: 12,
                    color: colorScheme.onSurface,
                  ),
                ),"""
new_text = """                child: CollapsibleOutput(
                  text: content,
                  style: GoogleFonts.firaCode(
                    fontSize: 12,
                    color: colorScheme.onSurface,
                  ),
                ),"""
content = content.replace(old_text, new_text)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
