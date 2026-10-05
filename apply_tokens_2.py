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

# 1. Update _buildJobStrip
new_job = '''  Widget _buildJobStrip(ColorScheme colorScheme) {
    if (_activeJobId == null || _activeJobStatus == '') return const SizedBox.shrink();
    
    Color statusColor = const Color(0xFF8B5CF6);
    IconData icon = Icons.sync;
    bool spinner = false;
    
    switch (_activeJobStatus) {
      case 'running':
        statusColor = const Color(0xFF2DD4BF);
        spinner = true;
        break;
      case 'waiting_approval':
        statusColor = const Color(0xFFF59E0B);
        icon = Icons.warning_amber_rounded;
        break;
      case 'done':
        statusColor = const Color(0xFF10B981);
        icon = Icons.check_circle_rounded;
        break;
      case 'failed':
      case 'cancelled':
        statusColor = const Color(0xFFEF4444);
        icon = Icons.error_outline_rounded;
        break;
      case 'cancelling':
        statusColor = Colors.grey;
        spinner = true;
        break;
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: AppTokens.glassBox(radius: 24).copyWith(
        color: statusColor.withOpacity(0.05),
        border: Border.all(color: statusColor.withOpacity(0.3)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: statusColor.withOpacity(0.15),
              boxShadow: [
                BoxShadow(color: statusColor.withOpacity(0.2), blurRadius: 10, offset: const Offset(0, 4))
              ]
            ),
            child: spinner 
              ? SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: statusColor))
              : Icon(icon, color: statusColor, size: 14),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('BACKGROUND JOB', style: GoogleFonts.spaceGrotesk(color: statusColor, fontSize: 10, fontWeight: FontWeight.bold, letterSpacing: 1.2)),
                const SizedBox(height: 2),
                Text(_activeJobSummary, style: GoogleFonts.inter(color: AppTokens.textPrimary, fontSize: 13, fontWeight: FontWeight.w500), maxLines: 1, overflow: TextOverflow.ellipsis),
              ],
            ),
          ),
          if (_activeJobStatus == 'running' || _activeJobStatus == 'waiting_approval')
            GestureDetector(
              onTap: _cancelJob,
              child: Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: Colors.white.withOpacity(0.05),
                ),
                child: const Icon(Icons.close_rounded, color: Colors.white54, size: 16),
              ),
            ),
        ],
      ),
    );
  }'''
replace_method('_buildJobStrip', new_job)

# 2. Update _buildSubtitleOverlay
new_subtitle = '''  Widget _buildSubtitleOverlay(ColorScheme colorScheme, bool isOverlayMode) {
    if (!_showSubtitles || _currentAiSubtitle.isEmpty) return const SizedBox.shrink();

    if (isOverlayMode) {
      return Container(
        margin: const EdgeInsets.only(left: 16, right: 16, top: 10, bottom: 20),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
        width: double.infinity,
        constraints: const BoxConstraints(maxHeight: 250),
        decoration: AppTokens.glassBox(radius: 40).copyWith(
          color: Colors.black.withOpacity(0.6),
          border: Border.all(color: AppTokens.glassBorder),
          boxShadow: [
            BoxShadow(color: Colors.black.withOpacity(0.6), blurRadius: 30, spreadRadius: 4, offset: const Offset(0, 10))
          ]
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(40),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 15, sigmaY: 15),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                Flexible(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    child: Text(
                      _currentAiSubtitle,
                      style: GoogleFonts.outfit(
                        fontSize: 16,
                        height: 1.5,
                        fontWeight: FontWeight.w500,
                        color: Colors.white.withOpacity(0.95),
                      ),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
                if (!_isAiSpeaking)
                  Padding(
                    padding: const EdgeInsets.only(top: 10.0),
                    child: InkWell(
                      onTap: () => _speak(_currentAiSubtitle),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const Icon(Icons.replay_circle_filled_rounded, size: 18, color: Color(0xFF2DD4BF)),
                          const SizedBox(width: 6),
                          Text("REPEAT AUDIO", style: GoogleFonts.spaceGrotesk(color: const Color(0xFF2DD4BF), fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 1.0)),
                        ],
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      );
    } else {
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
        padding: const EdgeInsets.all(32),
        width: double.infinity,
        constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.5),
        decoration: AppTokens.glassBox(radius: 32).copyWith(
          color: AppTokens.bgCard.withOpacity(0.8),
          boxShadow: [
             BoxShadow(color: const Color(0xFF8B5CF6).withOpacity(0.1), blurRadius: 40, offset: const Offset(0, 10))
          ]
        ),
        child: ClipRRect(
          borderRadius: BorderRadius.circular(32),
          child: BackdropFilter(
            filter: ImageFilter.blur(sigmaX: 20, sigmaY: 20),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Flexible(
                  child: SingleChildScrollView(
                    physics: const BouncingScrollPhysics(),
                    child: Text(
                      _currentAiSubtitle,
                      style: GoogleFonts.outfit(
                        fontSize: 28,
                        height: 1.4,
                        letterSpacing: 0.5,
                        fontWeight: FontWeight.w600,
                        color: Colors.white,
                      ),
                      textAlign: TextAlign.left,
                    ),
                  ),
                ),
                if (!_isAiSpeaking)
                  Padding(
                    padding: const EdgeInsets.only(top: 20.0),
                    child: Align(
                      alignment: Alignment.centerRight,
                      child: InkWell(
                        onTap: () => _speak(_currentAiSubtitle),
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                          decoration: BoxDecoration(
                            color: const Color(0xFF2DD4BF).withOpacity(0.1),
                            borderRadius: BorderRadius.circular(100),
                            border: Border.all(color: const Color(0xFF2DD4BF).withOpacity(0.3)),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              const Icon(Icons.replay_circle_filled_rounded, size: 18, color: Color(0xFF2DD4BF)),
                              const SizedBox(width: 8),
                              Text("REPEAT", style: GoogleFonts.spaceGrotesk(color: const Color(0xFF2DD4BF), fontSize: 12, fontWeight: FontWeight.bold, letterSpacing: 1.0)),
                            ],
                          ),
                        ),
                      ),
                    ),
                  ),
              ],
            ),
          ),
        ),
      );
    }
  }'''
replace_method('_buildSubtitleOverlay', new_subtitle)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print("Strips and Subtitles patched.")
