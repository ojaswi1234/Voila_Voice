import sys
import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

tokens_code = '''
// --- DESIGN TOKENS ---
class AppTokens {
  static const Color bgDark = Color(0xFF070709);
  static const Color bgCard = Color(0xFF12121A);
  
  static const LinearGradient primaryGradient = LinearGradient(
    colors: [Color(0xFF2DD4BF), Color(0xFF0F766E)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
  
  static const LinearGradient accentGradient = LinearGradient(
    colors: [Color(0xFF8B5CF6), Color(0xFF3B82F6)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );
  
  static const LinearGradient warningGradient = LinearGradient(
    colors: [Color(0xFFFF5A5F), Color(0xFFE11D48)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static LinearGradient glassGradient = LinearGradient(
    colors: [Colors.white.withOpacity(0.08), Colors.white.withOpacity(0.02)],
    begin: Alignment.topLeft,
    end: Alignment.bottomRight,
  );

  static Color glassBorder = Colors.white.withOpacity(0.1);
  static Color textPrimary = Colors.white;
  static Color textSecondary = Colors.white.withOpacity(0.6);
  
  static BoxDecoration glassBox({double radius = 16}) => BoxDecoration(
    gradient: glassGradient,
    borderRadius: BorderRadius.circular(radius),
    border: Border.all(color: glassBorder, width: 1),
    boxShadow: [
      BoxShadow(color: Colors.black.withOpacity(0.3), blurRadius: 20, offset: const Offset(0, 10))
    ],
  );
}
// --- END TOKENS ---
'''

if 'class AppTokens' not in content:
    content = content.replace('void main() async {', tokens_code + '\nvoid main() async {')

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print("Tokens added.")
