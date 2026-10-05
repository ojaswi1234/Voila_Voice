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

new_input = '''  Widget _buildInputArea(ColorScheme colorScheme) {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    bool isAgent = _currentMode == 'agent' || _isAssistant;

    if (isAgent) {
      return Container(
        margin: const EdgeInsets.only(left: 16, right: 16, bottom: 24, top: 8),
        padding: const EdgeInsets.all(16),
        decoration: AppTokens.bentoBox(isDark, radius: 32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            if (_isLiveSession && !_showTextInput) ...[
              Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: List.generate(5, (index) => Container(
                  margin: const EdgeInsets.symmetric(horizontal: 4),
                  width: index == 0 ? 8 : 6,
                  height: index == 0 ? 8 : 6,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    color: index == 0 ? AppTokens.accent : AppTokens.textSecondary(isDark),
                  ),
                )),
              ),
              const SizedBox(height: 16),
            ],
            Row(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                if (!_isLiveSession || _showTextInput)
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
                
                if (_showTextInput || !_isLiveSession)
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
                          hintText: _isListening ? 'Listening...' : 'Ask Agent...',
                          hintStyle: GoogleFonts.inter(color: AppTokens.textSecondary(isDark)),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          border: InputBorder.none,
                        ),
                      ),
                    ),
                  ),
                
                if (_isLiveSession && !_showTextInput)
                  Expanded(
                    child: Center(
                      child: Text(
                        _isAiSpeaking ? 'AI is speaking...' : (_isListening ? 'Listening...' : _currentStatus),
                        style: GoogleFonts.outfit(color: AppTokens.textPrimary(isDark), fontSize: 16, fontWeight: FontWeight.w500),
                      ),
                    ),
                  ),

                const SizedBox(width: 8),
                
                AnimatedSize(
                  duration: const Duration(milliseconds: 250),
                  curve: Curves.easeInOut,
                  child: _showTextInput
                    ? const SizedBox(width: 0)
                    : Padding(
                        padding: const EdgeInsets.only(right: 8, bottom: 4),
                        child: GestureDetector(
                          onTap: () {
                            if (_isLiveSession) {
                              _stopListening();
                              flutterTts.stop();
                              if (mounted) setState(() { _isAiSpeaking = false; _isLiveSession = false; });
                            } else {
                              setState(() => _isLiveSession = true);
                              _startListening();
                            }
                          },
                          child: Container(
                            padding: const EdgeInsets.all(14),
                            decoration: BoxDecoration(
                              color: AppTokens.cardAlt(isDark),
                              shape: BoxShape.circle,
                            ),
                            child: Icon(_isLiveSession ? Icons.mic_rounded : Icons.mic_off_rounded, color: AppTokens.textPrimary(isDark), size: 22),
                          ),
                        ),
                      ),
                ),

                GestureDetector(
                  onTap: () {
                    if (_isThinking) {
                      _cancelBackendTask();
                    } else if (_controller.text.isNotEmpty) {
                      _sendMessage();
                      if (mounted) setState(() { _showTextInput = false; });
                    } else {
                      setState(() { _showTextInput = true; });
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
                              : AppTokens.accentSecondary),
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: (_isThinking ? const Color(0xFFEF4444) : (_controller.text.isNotEmpty ? AppTokens.accent : AppTokens.accentSecondary)).withOpacity(0.4),
                          blurRadius: 12,
                          offset: const Offset(0, 4),
                        )
                      ],
                    ),
                    child: Icon(
                      _isThinking 
                          ? Icons.stop_rounded 
                          : (_controller.text.isNotEmpty 
                              ? Icons.send_rounded 
                              : Icons.keyboard_rounded),
                      color: Colors.white,
                      size: 22,
                    ),
                  ),
                ),
              ],
            ),
          ],
        ),
      );
    }
    
    // SHELL mode
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
                    GestureDetector(
                      onTap: _toggleListening,
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        margin: const EdgeInsets.only(right: 4, bottom: 4),
                        child: Icon(
                          _isListening ? Icons.mic_rounded : Icons.mic_none_rounded,
                          color: _isListening ? AppTokens.accent : AppTokens.textSecondary(isDark),
                          size: 20,
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
print("Features restored.")
