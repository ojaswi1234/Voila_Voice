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

# 1. Update _buildMessageCard (M-Chef / Learning Roadmap style)
new_message = '''  Widget _buildMessageCard(Map<String, dynamic> message, ColorScheme colorScheme) {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    final type = message['type'] as String? ?? 'unknown';
    final content = message['content'] as String? ?? '';
    final isUser = type == 'user';
    final isError = type == 'error';

    return Container(
      margin: EdgeInsets.only(
        bottom: 32,
        left: isUser ? 60 : 20,
        right: isUser ? 20 : 60,
      ),
      child: isUser
          // User messages are compact, bold pills (M-Chef style)
          ? Align(
              alignment: Alignment.centerRight,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                decoration: BoxDecoration(
                  color: AppTokens.accent,
                  borderRadius: BorderRadius.circular(100),
                  boxShadow: [
                    BoxShadow(color: AppTokens.accent.withOpacity(0.3), blurRadius: 12, offset: const Offset(0, 6))
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
                    : Text(
                        content,
                        style: GoogleFonts.inter(
                          color: Colors.white,
                          fontSize: 15,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
              ),
            )
          // AI messages are gorgeous raw text on background (Learning Roadmap style)
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: isError ? const Color(0xFFEF4444) : AppTokens.accentSecondary,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Text(
                      isError ? 'SYSTEM ERROR' : 'AI ASSISTANT',
                      style: GoogleFonts.spaceGrotesk(
                        color: isError ? const Color(0xFFEF4444) : AppTokens.accentSecondary,
                        fontSize: 11,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 2.0,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                type == 'image'
                    ? ClipRRect(
                        borderRadius: BorderRadius.circular(24),
                        child: Image.memory(
                          base64Decode(content),
                          fit: BoxFit.cover,
                        ),
                      )
                    : CollapsibleOutput(
                        text: content,
                        style: GoogleFonts.outfit(
                          textStyle: TextStyle(
                            color: isError ? const Color(0xFFEF4444) : AppTokens.textPrimary(isDark),
                            fontSize: 18,
                            height: 1.6,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
              ],
            ),
    );
  }'''
replace_method('_buildMessageCard', new_message)

# 2. Update _buildInputArea (Minimalist floating elements)
new_input = '''  Widget _buildInputArea(ColorScheme colorScheme) {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    bool isAgent = _currentMode == 'agent' || _isAssistant;

    if (isAgent) {
      if (_isLiveSession && !_showTextInput) {
        // Voice-only AI Assistant layout (Guardian Robotics style)
        return Container(
          width: double.infinity,
          padding: const EdgeInsets.only(bottom: 40, top: 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Text(
                _isAiSpeaking ? 'AI is speaking...' : (_isListening ? 'Listening...' : _currentStatus),
                style: GoogleFonts.spaceGrotesk(color: AppTokens.textPrimary(isDark), fontSize: 24, fontWeight: FontWeight.w800, letterSpacing: -0.5),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 40),
              // Massive pulsing mic button
              GestureDetector(
                onTap: () {
                  _stopListening();
                  flutterTts.stop();
                  if (mounted) setState(() { _isAiSpeaking = false; _isLiveSession = false; _showTextInput = true; });
                },
                child: Container(
                  width: 100,
                  height: 100,
                  decoration: BoxDecoration(
                    color: AppTokens.accent.withOpacity(0.1),
                    shape: BoxShape.circle,
                  ),
                  child: Center(
                    child: Container(
                      width: 70,
                      height: 70,
                      decoration: BoxDecoration(
                        color: AppTokens.accent,
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(color: AppTokens.accent.withOpacity(0.4), blurRadius: 30, spreadRadius: 10)
                        ]
                      ),
                      child: const Icon(Icons.mic_rounded, color: Colors.white, size: 36),
                    ),
                  ),
                ),
              ),
            ],
          ),
        );
      }

      // Minimal floating pill input
      return Container(
        margin: const EdgeInsets.only(left: 20, right: 20, bottom: 30, top: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            GestureDetector(
              onTap: () {
                _controller.text = "__SCREENSHOT__";
                _sendMessage();
              },
              child: Container(
                margin: const EdgeInsets.only(bottom: 2, right: 12),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppTokens.cardAlt(isDark),
                  shape: BoxShape.circle,
                  border: Border.all(color: AppTokens.border(isDark)),
                ),
                child: Icon(Icons.camera_alt_rounded, color: AppTokens.textSecondary(isDark), size: 22),
              ),
            ),
            
            Expanded(
              child: Container(
                margin: const EdgeInsets.only(bottom: 2),
                decoration: BoxDecoration(
                  color: AppTokens.cardAlt(isDark),
                  borderRadius: BorderRadius.circular(100),
                  border: Border.all(color: AppTokens.border(isDark)),
                ),
                child: TextField(
                  controller: _controller,
                  minLines: 1,
                  maxLines: 4,
                  style: GoogleFonts.inter(fontSize: 16, color: AppTokens.textPrimary(isDark), fontWeight: FontWeight.w500),
                  decoration: InputDecoration(
                    hintText: 'Ask me anything...',
                    hintStyle: GoogleFonts.inter(color: AppTokens.textSecondary(isDark)),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                    border: InputBorder.none,
                  ),
                ),
              ),
            ),

            const SizedBox(width: 12),
            GestureDetector(
              onTap: () {
                if (_isThinking) {
                  _cancelBackendTask();
                } else if (_controller.text.isNotEmpty) {
                  _sendMessage();
                } else {
                  setState(() { _isLiveSession = true; _showTextInput = false; });
                  _startListening();
                }
              },
              child: Container(
                margin: const EdgeInsets.only(bottom: 2),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: _isThinking
                      ? const Color(0xFFEF4444)
                      : (_controller.text.isNotEmpty
                          ? AppTokens.accentSecondary
                          : AppTokens.accent),
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: (_isThinking ? const Color(0xFFEF4444) : (_controller.text.isNotEmpty ? AppTokens.accentSecondary : AppTokens.accent)).withOpacity(0.4),
                      blurRadius: 16,
                      offset: const Offset(0, 6),
                    )
                  ],
                ),
                child: Icon(
                  _isThinking 
                      ? Icons.stop_rounded 
                      : (_controller.text.isNotEmpty 
                          ? Icons.send_rounded 
                          : Icons.mic_rounded),
                  color: _controller.text.isNotEmpty ? const Color(0xFF09090B) : Colors.white,
                  size: 22,
                ),
              ),
            ),
          ],
        ),
      );
    }
    
    // SHELL mode (keeps compact bento structure)
    return Container(
      margin: const EdgeInsets.only(left: 16, right: 16, bottom: 24, top: 8),
      decoration: AppTokens.bentoBox(isDark, radius: 24),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Container(
                margin: const EdgeInsets.only(bottom: 2),
                decoration: BoxDecoration(
                  color: AppTokens.cardAlt(isDark),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: AppTokens.border(isDark)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _controller,
                        minLines: 1,
                        maxLines: 4,
                        style: GoogleFonts.inter(fontSize: 14, color: AppTokens.textPrimary(isDark)),
                        decoration: InputDecoration(
                          hintText: _isListening ? 'Listening...' : 'Enter shell command...',
                          hintStyle: GoogleFonts.inter(color: AppTokens.textSecondary(isDark)),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          border: InputBorder.none,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 8),
            GestureDetector(
              onTap: () {
                _controller.text = "__SCREENSHOT__";
                _sendMessage();
              },
              child: Container(
                padding: const EdgeInsets.all(14),
                margin: const EdgeInsets.only(bottom: 2),
                decoration: BoxDecoration(
                  color: AppTokens.cardAlt(isDark),
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.camera_alt_rounded, color: AppTokens.textSecondary(isDark), size: 20),
              ),
            ),
            const SizedBox(width: 8),
            GestureDetector(
              onTap: _sendMessage,
              child: Container(
                padding: const EdgeInsets.all(14),
                margin: const EdgeInsets.only(bottom: 2),
                decoration: const BoxDecoration(
                  color: AppTokens.accent,
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.send_rounded, color: Colors.white, size: 20),
              ),
            ),
          ],
        ),
      ),
    );
  }'''
replace_method('_buildInputArea', new_input)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print("Rewrite complete.")
