import sys

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
    return Container(
      margin: const EdgeInsets.only(left: 16, right: 16, bottom: 24, top: 8),
      decoration: AppTokens.glassBox(radius: 32).copyWith(
        color: Colors.black.withOpacity(0.4),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(32),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
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
                    margin: const EdgeInsets.only(bottom: 2, right: 8, left: 4),
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: AppTokens.glassBorder,
                      shape: BoxShape.circle,
                    ),
                    child: Icon(Icons.camera_alt_rounded, color: AppTokens.textSecondary, size: 22),
                  ),
                ),
                Expanded(
                  child: Container(
                    margin: const EdgeInsets.only(bottom: 2),
                    decoration: BoxDecoration(
                      color: Colors.white.withOpacity(0.02),
                      borderRadius: BorderRadius.circular(24),
                      border: Border.all(color: AppTokens.glassBorder),
                    ),
                    child: TextField(
                      controller: _controller,
                      minLines: 1,
                      maxLines: 4,
                      style: GoogleFonts.outfit(fontSize: 15, color: AppTokens.textPrimary),
                      decoration: InputDecoration(
                        hintText: _isListening ? 'Listening...' : (_currentMode == 'agent' ? 'Ask Agent...' : 'Enter command...'),
                        hintStyle: GoogleFonts.outfit(color: AppTokens.textSecondary.withOpacity(0.5)),
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
                    duration: const Duration(milliseconds: 300),
                    curve: Curves.easeOutCubic,
                    margin: const EdgeInsets.only(bottom: 2, right: 4),
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      gradient: _isThinking
                          ? AppTokens.warningGradient
                          : (_controller.text.isNotEmpty
                              ? AppTokens.primaryGradient
                              : _isListening
                                  ? AppTokens.accentGradient
                                  : AppTokens.glassGradient),
                      shape: BoxShape.circle,
                      border: Border.all(color: _isListening || _controller.text.isNotEmpty || _isThinking ? Colors.transparent : AppTokens.glassBorder),
                      boxShadow: _isListening || _controller.text.isNotEmpty || _isThinking
                          ? [
                              BoxShadow(
                                color: (_isThinking ? const Color(0xFFE11D48) : (_isListening ? const Color(0xFF8B5CF6) : const Color(0xFF2DD4BF))).withOpacity(0.5),
                                blurRadius: 16,
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
                      color: _isListening || _controller.text.isNotEmpty || _isThinking ? Colors.white : AppTokens.textSecondary,
                      size: 22,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }'''
replace_method('_buildInputArea', new_input)

# 2. Update _buildMessageCard
new_message = '''  Widget _buildMessageCard(Map<String, dynamic> message, ColorScheme colorScheme) {
    final type = message['type'] as String? ?? 'unknown';
    final content = message['content'] as String? ?? '';
    final isUser = type == 'user';
    final isError = type == 'error';

    return Container(
      margin: EdgeInsets.only(
        bottom: 24,
        left: isUser ? 40 : 12,
        right: isUser ? 12 : 40,
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
                gradient: AppTokens.accentGradient,
                boxShadow: [
                  BoxShadow(color: const Color(0xFF8B5CF6).withOpacity(0.4), blurRadius: 12, offset: const Offset(0, 4)),
                ],
              ),
              child: const Icon(Icons.auto_awesome, size: 16, color: Colors.white),
            ),
          ],
          Flexible(
            child: ClipRRect(
              borderRadius: BorderRadius.only(
                topLeft: const Radius.circular(24),
                topRight: const Radius.circular(24),
                bottomLeft: Radius.circular(isUser ? 24 : 6),
                bottomRight: Radius.circular(isUser ? 6 : 24),
              ),
              child: BackdropFilter(
                filter: ImageFilter.blur(sigmaX: 12, sigmaY: 12),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
                  decoration: BoxDecoration(
                    gradient: isUser
                        ? AppTokens.primaryGradient
                        : isError
                            ? AppTokens.warningGradient
                            : AppTokens.glassGradient,
                    border: Border.all(
                      color: isUser || isError ? Colors.transparent : AppTokens.glassBorder,
                      width: 1,
                    ),
                    boxShadow: [
                      if (isUser)
                        BoxShadow(
                          color: const Color(0xFF2DD4BF).withOpacity(0.3),
                          blurRadius: 20,
                          offset: const Offset(0, 8),
                        )
                    ],
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
                              color: isUser || isError ? Colors.white : AppTokens.textPrimary.withOpacity(0.9),
                              fontSize: 15,
                              height: 1.6,
                              fontWeight: isUser ? FontWeight.w500 : FontWeight.w400,
                            ),
                          ),
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
                color: AppTokens.glassBorder,
                border: Border.all(color: AppTokens.glassBorder),
              ),
              child: Icon(Icons.person, size: 16, color: AppTokens.textSecondary),
            ),
          ],
        ],
      ),
    );
  }'''
replace_method('_buildMessageCard', new_message)

# 3. Update _buildModeToggle
new_toggle = '''  Widget _buildModeToggle(ColorScheme colorScheme) {
    bool isAgent = _currentMode == 'agent';
    return Container(
      decoration: AppTokens.glassBox(radius: 100).copyWith(
        color: Colors.black.withOpacity(0.4),
      ),
      padding: const EdgeInsets.all(4),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          GestureDetector(
            onTap: () {
              if (!isAgent) {
                setState(() { _currentMode = 'agent'; });
                _storage.write(key: 'last_mode', value: 'agent');
              }
            },
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOutCubic,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
              decoration: BoxDecoration(
                gradient: isAgent ? AppTokens.accentGradient : null,
                color: isAgent ? null : Colors.transparent,
                borderRadius: BorderRadius.circular(100),
                boxShadow: isAgent ? [
                  BoxShadow(color: const Color(0xFF8B5CF6).withOpacity(0.5), blurRadius: 12, offset: const Offset(0, 4))
                ] : [],
              ),
              child: Text(
                'AGENT',
                style: GoogleFonts.outfit(
                  color: isAgent ? Colors.white : AppTokens.textSecondary,
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                  letterSpacing: 1.0,
                ),
              ),
            ),
          ),
          GestureDetector(
            onTap: () {
              if (isAgent) {
                setState(() { _currentMode = 'shell'; });
                _storage.write(key: 'last_mode', value: 'shell');
              }
            },
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOutCubic,
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
              decoration: BoxDecoration(
                gradient: !isAgent ? AppTokens.warningGradient : null,
                color: !isAgent ? null : Colors.transparent,
                borderRadius: BorderRadius.circular(100),
                boxShadow: !isAgent ? [
                  BoxShadow(color: const Color(0xFFE11D48).withOpacity(0.5), blurRadius: 12, offset: const Offset(0, 4))
                ] : [],
              ),
              child: Text(
                'SHELL',
                style: GoogleFonts.outfit(
                  color: !isAgent ? Colors.white : AppTokens.textSecondary,
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                  letterSpacing: 1.0,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }'''
replace_method('_buildModeToggle', new_toggle)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print("Tokens applied successfully.")
