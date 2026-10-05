import sys

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update _buildMainContent to include Theme Toggle
old_header = '''              if (_currentMode.toUpperCase() == 'AGENT')
                IconButton(
                  icon: Icon(Icons.auto_awesome, size: 22, color: _selectedModel.isNotEmpty ? colorScheme.secondary : colorScheme.onSurface.withOpacity(0.7)),
                  onPressed: _showModelSelector,
                ),
              

              GestureDetector('''

new_header = '''              if (_currentMode.toUpperCase() == 'AGENT')
                IconButton(
                  icon: Icon(Icons.auto_awesome, size: 22, color: _selectedModel.isNotEmpty ? AppTokens.accent : AppTokens.textSecondary(appThemeMode.value == ThemeMode.dark)),
                  onPressed: _showModelSelector,
                ),
              IconButton(
                icon: Icon(appThemeMode.value == ThemeMode.dark ? Icons.light_mode_rounded : Icons.dark_mode_rounded, size: 22, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
                onPressed: () {
                  appThemeMode.value = appThemeMode.value == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark;
                },
              ),
              const SizedBox(width: 4),
              GestureDetector('''
content = content.replace(old_header, new_header)

# 2. Fix the Scaffold background
old_scaffold = '''      backgroundColor: _isAssistant ? Colors.transparent : AppTokens.bgDark,
      body: _isAssistant'''
new_scaffold = '''      backgroundColor: _isAssistant ? Colors.transparent : AppTokens.bg(appThemeMode.value == ThemeMode.dark),
      body: _isAssistant'''
content = content.replace(old_scaffold, new_scaffold)

# 3. Fix the title text style in the header
old_title = '''              const Text(
                'Voila Voice',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, letterSpacing: -0.5),
              ),'''
new_title = '''              Text(
                'Voila Voice',
                style: GoogleFonts.outfit(fontSize: 18, fontWeight: FontWeight.bold, letterSpacing: -0.5, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
              ),'''
content = content.replace(old_title, new_title)

# 4. Fix device selector style
old_selector = '''                  decoration: BoxDecoration(
                    color: const Color(0xFF1A1A1F),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: Colors.white.withOpacity(0.1)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.computer, size: 14, color: colorScheme.secondary),
                      const SizedBox(width: 6),
                      Text(
                        _activeDevice.isEmpty ? 'Select Device' : (_devices[_activeDevice]?['name'] ?? 'Desktop'),
                        style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
                      ),
                      const SizedBox(width: 4),
                      const Icon(Icons.keyboard_arrow_down, size: 14, color: Colors.white54),'''
new_selector = '''                  decoration: BoxDecoration(
                    color: AppTokens.cardAlt(appThemeMode.value == ThemeMode.dark),
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(color: AppTokens.border(appThemeMode.value == ThemeMode.dark)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.computer_rounded, size: 14, color: AppTokens.accent),
                      const SizedBox(width: 6),
                      Text(
                        _activeDevice.isEmpty ? 'Select Device' : (_devices[_activeDevice]?['name'] ?? 'Desktop'),
                        style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w500, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
                      ),
                      const SizedBox(width: 4),
                      Icon(Icons.keyboard_arrow_down_rounded, size: 14, color: AppTokens.textSecondary(appThemeMode.value == ThemeMode.dark)),'''
content = content.replace(old_selector, new_selector)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print("Header patched.")
