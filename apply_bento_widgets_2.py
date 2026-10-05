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

# 1. Update _buildModeToggle
new_toggle = '''  Widget _buildModeToggle(ColorScheme colorScheme) {
    bool isAgent = _currentMode == 'agent';
    bool isDark = appThemeMode.value == ThemeMode.dark;
    return Container(
      decoration: BoxDecoration(
        color: AppTokens.cardAlt(isDark),
        borderRadius: BorderRadius.circular(100),
        border: Border.all(color: AppTokens.border(isDark)),
        boxShadow: AppTokens.shadow(isDark),
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
              duration: const Duration(milliseconds: 200),
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
              decoration: BoxDecoration(
                color: isAgent ? AppTokens.accent : Colors.transparent,
                borderRadius: BorderRadius.circular(100),
                boxShadow: isAgent ? [
                  BoxShadow(color: AppTokens.accent.withOpacity(0.3), blurRadius: 8, offset: const Offset(0, 2))
                ] : [],
              ),
              child: Text(
                'AGENT',
                style: GoogleFonts.outfit(
                  color: isAgent ? Colors.white : AppTokens.textSecondary(isDark),
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
              duration: const Duration(milliseconds: 200),
              padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 10),
              decoration: BoxDecoration(
                color: !isAgent ? AppTokens.card(isDark) : Colors.transparent,
                borderRadius: BorderRadius.circular(100),
                border: Border.all(color: !isAgent ? AppTokens.border(isDark) : Colors.transparent),
                boxShadow: !isAgent ? [
                  BoxShadow(color: Colors.black.withOpacity(0.05), blurRadius: 4, offset: const Offset(0, 2))
                ] : [],
              ),
              child: Text(
                'SHELL',
                style: GoogleFonts.outfit(
                  color: !isAgent ? AppTokens.textPrimary(isDark) : AppTokens.textSecondary(isDark),
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

# 2. Update _buildJobStrip
new_job = '''  Widget _buildJobStrip(ColorScheme colorScheme) {
    if (_activeJobId == null || _activeJobStatus == '') return const SizedBox.shrink();
    
    bool isDark = appThemeMode.value == ThemeMode.dark;
    Color statusColor = AppTokens.accent;
    IconData icon = Icons.sync;
    bool spinner = false;
    
    switch (_activeJobStatus) {
      case 'running':
        statusColor = AppTokens.accentSecondary;
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
        statusColor = AppTokens.textSecondary(isDark);
        spinner = true;
        break;
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: AppTokens.bentoBox(isDark, radius: 24).copyWith(
        border: Border.all(color: statusColor.withOpacity(0.3), width: 1.5),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: statusColor.withOpacity(0.15),
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
                Text('BACKGROUND JOB', style: GoogleFonts.outfit(color: statusColor, fontSize: 10, fontWeight: FontWeight.bold, letterSpacing: 1.2)),
                const SizedBox(height: 2),
                Text(_activeJobSummary, style: GoogleFonts.inter(color: AppTokens.textPrimary(isDark), fontSize: 13, fontWeight: FontWeight.w500), maxLines: 1, overflow: TextOverflow.ellipsis),
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
                  color: AppTokens.cardAlt(isDark),
                ),
                child: Icon(Icons.close_rounded, color: AppTokens.textSecondary(isDark), size: 16),
              ),
            ),
        ],
      ),
    );
  }'''
replace_method('_buildJobStrip', new_job)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write('\n'.join(lines))
print("Toggle and Job Strip patched.")
