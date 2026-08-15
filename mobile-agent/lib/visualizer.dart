import 'dart:math';
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
  final List<double> _heights = List.generate(5, (index) => 0.0);
  final Random _random = Random();

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(vsync: this, duration: const Duration(milliseconds: 100))..repeat();
    _controller.addListener(() {
      if (widget.isListening || widget.isSpeaking) {
        setState(() {
          for (int i = 0; i < _heights.length; i++) {
            // Base fluctuation + soundLevel impact
            double base = 10.0 + _random.nextDouble() * 20.0;
            double boost = widget.soundLevel > 0 ? (widget.soundLevel * 10 * _random.nextDouble()) : 0;
            if (widget.isSpeaking) {
                // If AI is speaking and we don't have exact sound levels, simulate it
                boost = 20.0 + _random.nextDouble() * 40.0;
            }
            _heights[i] = base + boost;
            if (_heights[i] > 100.0) _heights[i] = 100.0;
          }
        });
      } else {
        setState(() {
          for (int i = 0; i < _heights.length; i++) {
             _heights[i] = 4.0; // Flat line when inactive
          }
        });
      }
    });
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 120,
      padding: const EdgeInsets.symmetric(vertical: 10),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        crossAxisAlignment: CrossAxisAlignment.center,
        children: List.generate(_heights.length, (index) {
          return AnimatedContainer(
            duration: const Duration(milliseconds: 100),
            margin: const EdgeInsets.symmetric(horizontal: 4),
            width: 8,
            height: _heights[index],
            decoration: BoxDecoration(
              color: widget.isSpeaking ? Colors.blueAccent : (widget.isListening ? Colors.redAccent : Colors.grey),
              borderRadius: BorderRadius.circular(4),
              boxShadow: [
                 if (widget.isSpeaking || widget.isListening)
                   BoxShadow(
                     color: (widget.isSpeaking ? Colors.blueAccent : Colors.redAccent).withOpacity(0.5),
                     blurRadius: 10,
                     spreadRadius: 2,
                   )
              ],
            ),
          );
        }),
      ),
    );
  }
}
