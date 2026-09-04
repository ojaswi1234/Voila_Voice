import 'dart:math';
import 'dart:ui';
import 'package:flutter/material.dart';

class AudioVisualizer extends StatefulWidget {
  final bool isListening;
  final bool isSpeaking;
  final double soundLevel;

  const AudioVisualizer({
    Key? key,
    required this.isListening,
    required this.isSpeaking,
    required this.soundLevel,
  }) : super(key: key);

  @override
  State<AudioVisualizer> createState() => _AudioVisualizerState();
}

class _AudioVisualizerState extends State<AudioVisualizer> with SingleTickerProviderStateMixin {
  late AnimationController _controller;
  
  @override
  void initState() {
    super.initState();
    // 4 second rotation for the smooth liquid gleaming effect
    _controller = AnimationController(vsync: this, duration: const Duration(seconds: 4))..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    bool isActive = widget.isListening || widget.isSpeaking;
    
    // Scale intensity based on sound level or AI speaking state
    double intensity = 1.0;
    if (widget.isSpeaking) {
      intensity = 1.5 + (sin(_controller.value * 2 * pi * 10) * 0.5); // Pulse effect for AI speaking
    } else if (widget.isListening) {
      intensity = 1.0 + (widget.soundLevel * 2.0); // Mic level impact
    } else {
      intensity = 0.3; // Idle state
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      height: 100,
      width: double.infinity,
      child: Center(
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, child) {
            return Stack(
              alignment: Alignment.center,
              children: [
                // Base dark pill for contrast
                Container(
                  width: 180,
                  height: 40,
                  decoration: BoxDecoration(
                    color: Colors.black.withOpacity(0.4),
                    borderRadius: BorderRadius.circular(20),
                  ),
                ),
                
                // The Liquid Glowing Mesh Layer (BackdropFilter for mesh blending)
                ClipRRect(
                  borderRadius: BorderRadius.circular(30),
                  child: BackdropFilter(
                    filter: ImageFilter.blur(sigmaX: 15, sigmaY: 15),
                    child: Container(
                      width: 220,
                      height: 60,
                      color: Colors.transparent,
                      child: Stack(
                        children: [
                          // Orb 1 (Cyan/Blue)
                          Positioned(
                            left: 50 + sin(_controller.value * 2 * pi) * 40 * intensity,
                            top: 10 + cos(_controller.value * 2 * pi) * 10 * intensity,
                            child: _buildGlowingOrb(
                                color: const Color(0xFF00E5FF).withOpacity(isActive ? 0.8 : 0.0), 
                                size: 35 * intensity),
                          ),
                          // Orb 2 (Purple/Magenta)
                          Positioned(
                            right: 50 + cos(_controller.value * 2 * pi) * 40 * intensity,
                            bottom: 10 + sin(_controller.value * 2 * pi) * 10 * intensity,
                            child: _buildGlowingOrb(
                                color: const Color(0xFFD500F9).withOpacity(isActive ? 0.8 : 0.0), 
                                size: 45 * intensity),
                          ),
                          // Orb 3 (Deep Blue/Indigo)
                          Positioned(
                            left: 90 + cos(_controller.value * 2 * pi + pi) * 20 * intensity,
                            top: 15 + sin(_controller.value * 2 * pi + pi) * 10 * intensity,
                            child: _buildGlowingOrb(
                                color: const Color(0xFF2962FF).withOpacity(isActive ? 0.8 : 0.0), 
                                size: 40 * intensity),
                          ),
                        ],
                      ),
                    ),
                  ),
                ),
                
                // Overlay sharp gleaming line (acts as the core waveform)
                Opacity(
                  opacity: isActive ? 1.0 : 0.2,
                  child: Container(
                    width: isActive ? (140 * (intensity.clamp(0.5, 2.0) / 2.0)) : 40,
                    height: isActive ? 2 : 1,
                    decoration: BoxDecoration(
                      color: Colors.white,
                      boxShadow: [
                        if (isActive)
                          BoxShadow(color: Colors.white.withOpacity(0.9), blurRadius: 6, spreadRadius: 2)
                      ],
                      borderRadius: BorderRadius.circular(2),
                    ),
                  ),
                ),
              ],
            );
          }
        ),
      ),
    );
  }

  Widget _buildGlowingOrb({required Color color, required double size}) {
    return Container(
      width: size,
      height: size,
      decoration: BoxDecoration(
        shape: BoxShape.circle,
        color: color,
        boxShadow: [
          BoxShadow(
            color: color,
            blurRadius: size * 1.5,
            spreadRadius: size,
          )
        ],
      ),
    );
  }
}
