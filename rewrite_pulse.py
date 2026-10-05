import sys
import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

pulse_wave_class = '''class PulseWaveVisualizer extends StatefulWidget {
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

  Widget _buildRipple(double delay, Color color) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        double progress = (_controller.value + delay) % 1.0;
        // Physics of water ripple: Expands outward, loses energy (opacity and thickness) over distance
        double scale = 1.0 + (progress * 2.5); 
        double opacity = (1.0 - progress) * 0.8; // High visibility fading to 0
        
        return Transform.scale(
          scale: scale,
          child: Container(
            width: 70, height: 70,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              border: Border.all(
                color: color.withOpacity(opacity), 
                width: 2.0 + (1.0 - progress) * 4.0 // Thicker at origin
              ),
              color: color.withOpacity(opacity * 0.15), // Slight droplet fill
            ),
          ),
        );
      },
    );
  }

  @override
  Widget build(BuildContext context) {
    Color baseColor = widget.isSpeaking ? AppTokens.accentSecondary : AppTokens.accent;

    return GestureDetector(
      onTap: widget.onTap,
      child: SizedBox(
        width: 250,
        height: 250,
        child: Stack(
          alignment: Alignment.center,
          children: [
            if (widget.isListening || widget.isSpeaking) ...[
              _buildRipple(0.0, baseColor),
              _buildRipple(0.33, baseColor),
              _buildRipple(0.66, baseColor),
            ],
            
            // Central core button
            AnimatedBuilder(
              animation: _controller,
              builder: (context, child) {
                double coreScale = widget.isListening || widget.isSpeaking 
                    ? 1.0 + (math.sin(_controller.value * math.pi * 2) * 0.05) // Subtle breathing
                    : 1.0;
                    
                double shadowSpread = widget.isListening || widget.isSpeaking 
                    ? 15 + (math.sin(_controller.value * math.pi * 2) * 10) 
                    : 10;

                return Transform.scale(
                  scale: coreScale,
                  child: Container(
                    width: 70,
                    height: 70,
                    decoration: BoxDecoration(
                      color: baseColor,
                      shape: BoxShape.circle,
                      boxShadow: [
                        BoxShadow(
                          color: baseColor.withOpacity(0.5),
                          blurRadius: 30,
                          spreadRadius: shadowSpread,
                        )
                      ]
                    ),
                    child: Center(
                      child: Icon(
                        widget.isSpeaking ? Icons.graphic_eq_rounded : Icons.mic_rounded,
                        color: Colors.white,
                        size: 32,
                      ),
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }
}'''

# Replace the old class entirely
start = content.find('class PulseWaveVisualizer extends StatefulWidget {')
end = content.find('class _VoiceHomePageState extends State<VoiceHomePage> {')

if start != -1 and end != -1:
    content = content[:start] + pulse_wave_class + '\n\n' + content[end:]

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print("PulseWaveVisualizer physics updated.")
