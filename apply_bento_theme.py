import sys
import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Globals and AppTokens
tokens_replacement = '''final ValueNotifier<ThemeMode> appThemeMode = ValueNotifier(ThemeMode.light);

class AppTokens {
  static const Color accent = Color(0xFF6366F1); // Indigo
  static const Color accentSecondary = Color(0xFFF97316); // Coral Orange
  
  static Color bg(bool isDark) => isDark ? const Color(0xFF0F172A) : const Color(0xFFF8FAFC);
  static Color card(bool isDark) => isDark ? const Color(0xFF1E293B) : Colors.white;
  static Color cardAlt(bool isDark) => isDark ? const Color(0xFF334155) : const Color(0xFFF1F5F9);
  
  static Color textPrimary(bool isDark) => isDark ? const Color(0xFFF9FAFB) : const Color(0xFF0F172A);
  static Color textSecondary(bool isDark) => isDark ? const Color(0xFF94A3B8) : const Color(0xFF64748B);
  
  static Color border(bool isDark) => isDark ? const Color(0xFF334155) : const Color(0xFFE2E8F0);
  
  static List<BoxShadow> shadow(bool isDark) => [
    BoxShadow(
      color: isDark ? Colors.black.withOpacity(0.3) : const Color(0xFFCBD5E1).withOpacity(0.4),
      blurRadius: 16,
      offset: const Offset(0, 4),
    )
  ];
  
  static BoxDecoration bentoBox(bool isDark, {double radius = 24}) => BoxDecoration(
    color: card(isDark),
    borderRadius: BorderRadius.circular(radius),
    border: Border.all(color: border(isDark), width: 1.5),
    boxShadow: shadow(isDark),
  );
}
// --- END TOKENS ---'''

content = re.sub(r'// --- DESIGN TOKENS ---.*?// --- END TOKENS ---', tokens_replacement, content, flags=re.DOTALL)

# 2. VoiceCliApp setup
voice_cli_app_old = '''class VoiceCliApp extends StatelessWidget {
  const VoiceCliApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Voice CLI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        scaffoldBackgroundColor: Colors.transparent,
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF7C6CFF),
          primary: const Color(0xFF7C6CFF),
          secondary: const Color(0xFF3DDC97),
          surface: const Color(0xFF1A1A1F),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        textTheme: GoogleFonts.interTextTheme(ThemeData.dark().textTheme),
        appBarTheme: const AppBarTheme(
          backgroundColor: Color(0xFF0F0F12),
          elevation: 0,
          scrolledUnderElevation: 0,
        ),
      ),
      themeMode: ThemeMode.dark,
      home: const VoiceHomePage(),
    );
  }
}'''

voice_cli_app_new = '''class VoiceCliApp extends StatelessWidget {
  const VoiceCliApp({super.key});

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<ThemeMode>(
      valueListenable: appThemeMode,
      builder: (context, currentMode, child) {
        return MaterialApp(
          title: 'Voila Voice',
          debugShowCheckedModeBanner: false,
          themeMode: currentMode,
          theme: ThemeData(
            scaffoldBackgroundColor: Colors.transparent,
            brightness: Brightness.light,
            useMaterial3: true,
          ),
          darkTheme: ThemeData(
            scaffoldBackgroundColor: Colors.transparent,
            brightness: Brightness.dark,
            useMaterial3: true,
          ),
          home: const VoiceHomePage(),
        );
      }
    );
  }
}'''
content = content.replace(voice_cli_app_old, voice_cli_app_new)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print("Phase 1 Complete.")
