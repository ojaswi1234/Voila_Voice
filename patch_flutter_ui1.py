import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update _buildInputArea with SegmentedControl
input_area_old = """  Widget _buildInputArea(ColorScheme colorScheme) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surface,
        boxShadow: [
          BoxShadow(
            color: colorScheme.shadow.withOpacity(0.1),
            blurRadius: 4,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: Row(
        children: [
          Expanded("""
          
input_area_new = """  Widget _buildInputArea(ColorScheme colorScheme) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surface,
        boxShadow: [
          BoxShadow(
            color: colorScheme.shadow.withOpacity(0.1),
            blurRadius: 4,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SegmentedButton<String>(
            segments: const [
              ButtonSegment<String>(
                value: 'ask',
                label: Text('Ask'),
                icon: Icon(Icons.auto_awesome),
                tooltip: 'Send to Antigravity',
              ),
              ButtonSegment<String>(
                value: 'command',
                label: Text('Command'),
                icon: Icon(Icons.terminal),
                tooltip: 'Run directly on device',
              ),
            ],
            selected: <String>{_currentMode},
            onSelectionChanged: (Set<String> newSelection) {
              setState(() {
                _currentMode = newSelection.first;
              });
            },
            showSelectedIcon: false,
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded("""
content = content.replace(input_area_old, input_area_new)

# Fix hint text inside _buildInputArea
content = content.replace(
    "hintText: _isListening ? 'Listening...' : 'Enter command...',",
    "hintText: _isListening ? 'Listening...' : (_currentMode == 'ask' ? 'Ask agent...' : 'Enter shell command...'),"
)
content = content.replace(
    """        child: Row(
          children: [
            Expanded(
              child: TextField(""",
    """        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: TextField("""
) # Wait, my replacement above did this already, let's undo this mistake if needed.
# Actually I'll just write a cleaner patch file to rewrite _buildInputArea fully.
