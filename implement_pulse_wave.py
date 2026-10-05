import sys
import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

pulse_wave_class = '''
// ==========================================
// Claude/ChatGPT Style Pulse Wave Visualizer
// ==========================================
class PulseWaveVisualizer extends StatefulWidget {
  final bool isListening;
  final bool isSpeaking;
  final VoidCallback onTap;

  const PulseWaveVisualizer({
    Key? key,
    required this.isListening,
    required this.isSpeaking,
    required this.onTap,
  }) : super(key: key);

  @override
  _PulseWaveVisualizerState createState() => _PulseWaveVisualizerState();
}

class _PulseWaveVisualizerState extends State<PulseWaveVisualizer> with SingleTickerProviderStateMixin {
  late AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2000),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    Color baseColor = widget.isSpeaking ? AppTokens.accentSecondary : AppTokens.accent;

    return GestureDetector(
      onTap: widget.onTap,
      child: AnimatedBuilder(
        animation: _controller,
        builder: (context, child) {
          // Multiple overlapping circle scales to create the 'wavy ping' effect
          double wave1 = 1.0 + (_controller.value * 1.5);
          double wave2 = 1.0 + (((_controller.value + 0.3) % 1.0) * 1.2);
          double wave3 = 1.0 + (((_controller.value + 0.6) % 1.0) * 0.9);
          
          double corePulse = widget.isListening || widget.isSpeaking 
              ? 10 + (math.sin(_controller.value * math.pi * 2) * 5) 
              : 5;

          return SizedBox(
            width: 220,
            height: 220,
            child: Stack(
              alignment: Alignment.center,
              children: [
                if (widget.isListening || widget.isSpeaking) ...[
                  // Wavy outer circles of different sizes
                  Transform.scale(
                    scale: wave1,
                    child: Container(
                      width: 90, height: 90,
                      decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: baseColor.withOpacity(0.05 * (1.0 - _controller.value)), width: 2)),
                    ),
                  ),
                  Transform.scale(
                    scale: wave2,
                    child: Container(
                      width: 90, height: 90,
                      decoration: BoxDecoration(shape: BoxShape.circle, color: baseColor.withOpacity(0.1 * (1.0 - ((_controller.value + 0.3) % 1.0)))),
                    ),
                  ),
                  Transform.scale(
                    scale: wave3,
                    child: Container(
                      width: 90, height: 90,
                      decoration: BoxDecoration(shape: BoxShape.circle, color: baseColor.withOpacity(0.15 * (1.0 - ((_controller.value + 0.6) % 1.0)))),
                    ),
                  ),
                ],
                
                // Central core button
                Container(
                  width: 90,
                  height: 90,
                  decoration: BoxDecoration(
                    color: baseColor,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: baseColor.withOpacity(0.4),
                        blurRadius: 30,
                        spreadRadius: corePulse,
                      )
                    ]
                  ),
                  child: Center(
                    child: Icon(
                      widget.isSpeaking ? Icons.graphic_eq_rounded : Icons.mic_rounded,
                      color: Colors.white,
                      size: 40,
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}
'''

# Find the end of the file or just before the last class
if 'class _VoiceHomePageState' in content:
    content = content.replace('class _VoiceHomePageState', pulse_wave_class + '\nclass _VoiceHomePageState')

old_mic_button = '''// Massive pulsing mic button
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
                  ),'''

new_mic_button = '''// Claude/ChatGPT-style Wavy Pulsing Mic Button
                  PulseWaveVisualizer(
                    isListening: _isListening,
                    isSpeaking: _isAiSpeaking,
                    onTap: () {
                      _stopListening();
                      flutterTts.stop();
                      if (mounted) setState(() { _isAiSpeaking = false; _isLiveSession = false; _showTextInput = true; });
                    },
                  ),'''

content = content.replace(old_mic_button, new_mic_button)

# Also ensure import 'dart:math' as math; is added at the top if missing
if 'import \'dart:math\' as math;' not in content:
    content = content.replace("import 'package:flutter/material.dart';", "import 'package:flutter/material.dart';\nimport 'dart:math' as math;")

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print("PulseWaveVisualizer injected.")
