import sys
import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

def replace_method(method_name, new_code):
    global lines
    start = -1
    for i, line in enumerate(lines):
        if f'Widget {method_name}' in line:
            start = i
            break
    if start == -1: return False
    stack = []
    end = start
    for i in range(start, len(lines)):
        for char in lines[i]:
            if char == '{': stack.append('{')
            elif char == '}': 
                if stack: stack.pop()
        if len(stack) == 0 and i > start:
            end = i
            break
    lines = lines[:start] + new_code.split('\n') + lines[end+1:]
    return True

# 1. Update _buildInputArea
new_input = '''  Widget _buildInputArea(ColorScheme colorScheme) {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    return Container(
      margin: const EdgeInsets.only(left: 16, right: 16, bottom: 24, top: 8),
      decoration: AppTokens.bentoBox(isDark, radius: 32),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            GestureDetector(
              onTap: () {
                _controller.text = "__SCREENSHOT__";
                _sendMessage();
              },
              child: Container(
                margin: const EdgeInsets.only(bottom: 4, right: 8, left: 4),
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppTokens.cardAlt(isDark),
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.camera_alt_rounded, color: AppTokens.textSecondary(isDark), size: 22),
              ),
            ),
            Expanded(
              child: Container(
                margin: const EdgeInsets.only(bottom: 4),
                decoration: BoxDecoration(
                  color: AppTokens.cardAlt(isDark),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(color: AppTokens.border(isDark)),
                ),
                child: TextField(
                  controller: _controller,
                  minLines: 1,
                  maxLines: 4,
                  style: GoogleFonts.inter(fontSize: 15, color: AppTokens.textPrimary(isDark)),
                  decoration: InputDecoration(
                    hintText: _isListening ? 'Listening...' : (_currentMode == 'agent' ? 'Ask Agent...' : 'Enter command...'),
                    hintStyle: GoogleFonts.inter(color: AppTokens.textSecondary(isDark)),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                    border: InputBorder.none,
                  ),
                ),
              ),
            ),
            const SizedBox(width: 8),
            GestureDetector(
              onTap: () {
                if (_isThinking) {
                  _cancelBackendTask();
                } else if (_controller.text.isNotEmpty) {
                  _sendMessage();
                } else {
                  _toggleListening();
                }
              },
              child: AnimatedContainer(
                duration: const Duration(milliseconds: 200),
                margin: const EdgeInsets.only(bottom: 4, right: 4),
                padding: const EdgeInsets.all(14),
                decoration: BoxDecoration(
                  color: _isThinking
                      ? const Color(0xFFEF4444)
                      : (_controller.text.isNotEmpty
                          ? AppTokens.accent
                          : _isListening
                              ? AppTokens.accentSecondary
                              : AppTokens.cardAlt(isDark)),
                  shape: BoxShape.circle,
                  boxShadow: _isListening || _controller.text.isNotEmpty || _isThinking
                      ? [
                          BoxShadow(
                            color: (_isThinking ? const Color(0xFFEF4444) : (_isListening ? AppTokens.accentSecondary : AppTokens.accent)).withOpacity(0.4),
                            blurRadius: 12,
                            offset: const Offset(0, 4),
                          )
                        ]
                      : [],
                ),
                child: Icon(
                  _isThinking 
                      ? Icons.stop_rounded 
                      : (_controller.text.isNotEmpty 
                          ? Icons.send_rounded 
                          : (_isListening ? Icons.mic_rounded : Icons.mic_none_rounded)),
                  color: _isListening || _controller.text.isNotEmpty || _isThinking ? Colors.white : AppTokens.textSecondary(isDark),
                  size: 22,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }'''
replace_method('_buildInputArea', new_input)

# 2. Update _buildMessageCard
new_message = '''  Widget _buildMessageCard(Map<String, dynamic> message, ColorScheme colorScheme) {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    final type = message['type'] as String? ?? 'unknown';
    final content = message['content'] as String? ?? '';
    final isUser = type == 'user';
    final isError = type == 'error';

    return Container(
      margin: EdgeInsets.only(
        bottom: 24,
        left: isUser ? 40 : 16,
        right: isUser ? 16 : 40,
      ),
      child: Row(
        mainAxisAlignment: isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (!isUser) ...[
            Container(
              margin: const EdgeInsets.only(right: 12, bottom: 4),
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppTokens.card(isDark),
                border: Border.all(color: AppTokens.border(isDark), width: 1.5),
                boxShadow: AppTokens.shadow(isDark),
              ),
              child: const Icon(Icons.smart_toy_rounded, size: 16, color: AppTokens.accent),
            ),
          ],
          Flexible(
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
              decoration: BoxDecoration(
                color: isUser ? AppTokens.accent : (isError ? const Color(0xFFFEF2F2) : AppTokens.card(isDark)),
                borderRadius: BorderRadius.only(
                  topLeft: const Radius.circular(24),
                  topRight: const Radius.circular(24),
                  bottomLeft: Radius.circular(isUser ? 24 : 6),
                  bottomRight: Radius.circular(isUser ? 6 : 24),
                ),
                border: Border.all(
                  color: isUser ? AppTokens.accent : (isError ? const Color(0xFFFCA5A5) : AppTokens.border(isDark)),
                  width: 1.5,
                ),
                boxShadow: AppTokens.shadow(isDark),
              ),
              child: type == 'image'
                  ? ClipRRect(
                      borderRadius: BorderRadius.circular(12),
                      child: Image.memory(
                        base64Decode(content),
                        fit: BoxFit.cover,
                      ),
                    )
                  : CollapsibleOutput(
                      text: content,
                      style: GoogleFonts.inter(
                        textStyle: TextStyle(
                          color: isUser ? Colors.white : (isError ? const Color(0xFF991B1B) : AppTokens.textPrimary(isDark)),
                          fontSize: 15,
                          height: 1.6,
                          fontWeight: FontWeight.w500,
                        ),
                      ),
                    ),
            ),
          ),
          if (isUser) ...[
            Container(
              margin: const EdgeInsets.only(left: 12, bottom: 4),
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                shape: BoxShape.circle,
                color: AppTokens.cardAlt(isDark),
                border: Border.all(color: AppTokens.border(isDark)),
              ),
              child: Icon(Icons.person_rounded, size: 16, color: AppTokens.textSecondary(isDark)),
            ),
          ],
        ],
      ),
    );
  }'''
replace_method('_buildMessageCard', new_message)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print("Input and Message patched.")
