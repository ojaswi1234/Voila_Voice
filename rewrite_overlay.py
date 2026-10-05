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

new_subtitle = '''  Widget _buildSubtitleOverlay(ColorScheme colorScheme, bool isOverlayMode) {
    if (!_showSubtitles || _currentAiSubtitle.isEmpty) return const SizedBox.shrink();
    
    bool isDark = appThemeMode.value == ThemeMode.dark;

    if (isOverlayMode) {
      // Floating pill for system overlay (highly readable, strict bento style)
      return Container(
        margin: const EdgeInsets.only(left: 16, right: 16, top: 10, bottom: 20),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
        width: double.infinity,
        constraints: const BoxConstraints(maxHeight: 250),
        decoration: BoxDecoration(
          color: AppTokens.card(isDark),
          borderRadius: BorderRadius.circular(40),
          border: Border.all(color: AppTokens.border(isDark), width: 1.5),
          boxShadow: AppTokens.shadow(isDark),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Flexible(
              child: SingleChildScrollView(
                physics: const BouncingScrollPhysics(),
                child: Text(
                  _currentAiSubtitle,
                  style: GoogleFonts.outfit(
                    fontSize: 18,
                    height: 1.5,
                    fontWeight: FontWeight.w600,
                    color: AppTokens.textPrimary(isDark),
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
            if (!_isAiSpeaking)
              Padding(
                padding: const EdgeInsets.only(top: 16.0),
                child: InkWell(
                  onTap: () => _speak(_currentAiSubtitle),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      color: AppTokens.accentSecondary.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(100),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.replay_circle_filled_rounded, size: 18, color: AppTokens.accentSecondary),
                        const SizedBox(width: 6),
                        Text("REPEAT AUDIO", style: GoogleFonts.spaceGrotesk(color: AppTokens.accentSecondary, fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 1.0)),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      );
    } else {
      // Full screen mode: raw beautiful typography, no card bounds
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
        width: double.infinity,
        constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.4),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Container(
                  width: 10,
                  height: 10,
                  decoration: const BoxDecoration(
                    color: AppTokens.accentSecondary,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  'AI SUBTITLE',
                  style: GoogleFonts.spaceGrotesk(
                    color: AppTokens.accentSecondary,
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 2.0,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Flexible(
              child: SingleChildScrollView(
                physics: const BouncingScrollPhysics(),
                child: Text(
                  _currentAiSubtitle,
                  style: GoogleFonts.outfit(
                    fontSize: 28,
                    height: 1.4,
                    letterSpacing: 0.2,
                    fontWeight: FontWeight.w600,
                    color: AppTokens.textPrimary(isDark),
                  ),
                  textAlign: TextAlign.left,
                ),
              ),
            ),
            if (!_isAiSpeaking)
              Padding(
                padding: const EdgeInsets.only(top: 24.0),
                child: Align(
                  alignment: Alignment.centerRight,
                  child: InkWell(
                    onTap: () => _speak(_currentAiSubtitle),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                      decoration: BoxDecoration(
                        color: AppTokens.accentSecondary.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(100),
                        border: Border.all(color: AppTokens.accentSecondary.withOpacity(0.3)),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.replay_circle_filled_rounded, size: 20, color: AppTokens.accentSecondary),
                          const SizedBox(width: 8),
                          Text("REPEAT AUDIO", style: GoogleFonts.spaceGrotesk(color: AppTokens.accentSecondary, fontSize: 13, fontWeight: FontWeight.bold, letterSpacing: 1.0)),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      );
    }
  }'''
replace_method('_buildSubtitleOverlay', new_subtitle)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print("Overlay fixed.")
