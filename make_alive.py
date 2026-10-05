import sys
import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update AppTokens
old_tokens = '''class AppTokens {
  static const Color accent = Color(0xFF6366F1); // Indigo
  static const Color accentSecondary = Color(0xFFF97316); // Coral Orange
  
  static Color bg(bool isDark) => isDark ? const Color(0xFF0F172A) : const Color(0xFFF8FAFC);
  static Color card(bool isDark) => isDark ? const Color(0xFF1E293B) : Colors.white;
  static Color cardAlt(bool isDark) => isDark ? const Color(0xFF334155) : const Color(0xFFF1F5F9);
  
  static Color textPrimary(bool isDark) => isDark ? const Color(0xFFF9FAFB) : const Color(0xFF0F172A);
  static Color textSecondary(bool isDark) => isDark ? const Color(0xFF94A3B8) : const Color(0xFF64748B);
  
  static Color border(bool isDark) => isDark ? const Color(0xFF334155) : const Color(0xFFE2E8F0);'''

new_tokens = '''class AppTokens {
  static const Color accent = Color(0xFFFF4500); // Blazing Orange / Coral
  static const Color accentSecondary = Color(0xFF00E5FF); // Electric Cyan
  
  static Color bg(bool isDark) => isDark ? const Color(0xFF09090B) : const Color(0xFFF4F4F5);
  static Color card(bool isDark) => isDark ? const Color(0xFF18181B) : Colors.white;
  static Color cardAlt(bool isDark) => isDark ? const Color(0xFF27272A) : const Color(0xFFE4E4E7);
  
  static Color textPrimary(bool isDark) => isDark ? const Color(0xFFFAFAFA) : const Color(0xFF09090B);
  static Color textSecondary(bool isDark) => isDark ? const Color(0xFFA1A1AA) : const Color(0xFF71717A);
  
  static Color border(bool isDark) => isDark ? const Color(0xFF3F3F46) : const Color(0xFFD4D4D8);'''

content = content.replace(old_tokens, new_tokens)

# 2. Update Header Title to be BOLD Space Grotesk
old_title = '''              Text(
                'Voila Voice',
                style: GoogleFonts.outfit(fontSize: 18, fontWeight: FontWeight.bold, letterSpacing: -0.5, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
              ),'''
new_title = '''              Text(
                'VOILA VOICE',
                style: GoogleFonts.spaceGrotesk(fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: -1.0, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
              ),'''
content = content.replace(old_title, new_title)

# 3. Update AGENT/SHELL toggle to be bolder
old_toggle_agent = '''                'AGENT',
                style: GoogleFonts.outfit(
                  color: isAgent ? Colors.white : AppTokens.textSecondary(isDark),
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                  letterSpacing: 1.0,
                ),'''
new_toggle_agent = '''                'AGENT',
                style: GoogleFonts.spaceGrotesk(
                  color: isAgent ? Colors.white : AppTokens.textSecondary(isDark),
                  fontWeight: FontWeight.w800,
                  fontSize: 14,
                  letterSpacing: 1.5,
                ),'''
old_toggle_shell = '''                'SHELL',
                style: GoogleFonts.outfit(
                  color: !isAgent ? AppTokens.textPrimary(isDark) : AppTokens.textSecondary(isDark),
                  fontWeight: FontWeight.bold,
                  fontSize: 13,
                  letterSpacing: 1.0,
                ),'''
new_toggle_shell = '''                'SHELL',
                style: GoogleFonts.spaceGrotesk(
                  color: !isAgent ? AppTokens.textPrimary(isDark) : AppTokens.textSecondary(isDark),
                  fontWeight: FontWeight.w800,
                  fontSize: 14,
                  letterSpacing: 1.5,
                ),'''
content = content.replace(old_toggle_agent, new_toggle_agent).replace(old_toggle_shell, new_toggle_shell)

# 4. Enhance Chat Bubbles (Add thick left border to AI bubbles)
old_ai_bubble = '''          Flexible(
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
              ),'''

new_ai_bubble = '''          Flexible(
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
                border: Border(
                  top: BorderSide(color: isUser ? AppTokens.accent : (isError ? const Color(0xFFFCA5A5) : AppTokens.border(isDark)), width: 1.5),
                  right: BorderSide(color: isUser ? AppTokens.accent : (isError ? const Color(0xFFFCA5A5) : AppTokens.border(isDark)), width: 1.5),
                  bottom: BorderSide(color: isUser ? AppTokens.accent : (isError ? const Color(0xFFFCA5A5) : AppTokens.border(isDark)), width: 1.5),
                  left: BorderSide(color: isUser ? AppTokens.accent : (isError ? const Color(0xFFEF4444) : AppTokens.accentSecondary), width: isUser ? 1.5 : 4.0),
                ),
                boxShadow: AppTokens.shadow(isDark),
              ),'''

content = content.replace(old_ai_bubble, new_ai_bubble)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print("Made alive.")
