import 'package:flutter/material.dart';
import 'package:siri_wave/siri_wave.dart';

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

class _AudioVisualizerState extends State<AudioVisualizer> {
  late IOS9SiriWaveformController _controller;

  @override
  void initState() {
    super.initState();
    _controller = IOS9SiriWaveformController(
      amplitude: 0.05,
      speed: 0.05,
    );
  }

  @override
  void didUpdateWidget(AudioVisualizer oldWidget) {
    super.didUpdateWidget(oldWidget);
    
    // Smoothly adjust amplitude and speed based on state
    if (widget.isSpeaking) {
      _controller.amplitude = 0.7; 
      _controller.speed = 0.12; 
    } else if (widget.isListening) {
      double targetAmp = 0.1 + (widget.soundLevel * 1.5).clamp(0.0, 1.0);
      _controller.amplitude = targetAmp; 
      _controller.speed = 0.1;
    } else {
      _controller.amplitude = 0.05; 
      _controller.speed = 0.03; 
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 60,
      width: double.infinity,
      alignment: Alignment.center,
      child: SiriWaveform.ios9(
        controller: _controller,
      ),
    );
  }
}
