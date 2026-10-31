import 'dart:async';  // unawaited(), StreamSubscription, Timer
import 'dart:ui' show ImageFilter;
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart'; // For compute()
import 'package:flutter/material.dart';
import 'dart:math' as math;
import 'package:flutter/services.dart';
import 'crypto.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:permission_handler/permission_handler.dart';
import 'device_identity.dart';
import 'artifacts_page.dart';
import 'surveillance_ui.dart';
import 'rich_output_widgets.dart';
import 'package:uuid/uuid.dart';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_background/flutter_background.dart';
import 'connection_flowchart.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:path_provider/path_provider.dart';

// Top-level function for background JSON parsing via compute()
// Bug #13 Fix: Must take `dynamic` to satisfy compute() type constraints
dynamic parseJsonInBackground(dynamic text) {
  return jsonDecode(text as String);
}

// Helper specifically for JSON lists to satisfy Dart's type inference
List<dynamic> parseJsonListInBackground(dynamic text) {
  return jsonDecode(text as String) as List<dynamic>;
}

// Backend URL from build-time configuration (safe default + scheme fix)
const String _rawBackendUrl = String.fromEnvironment(
  'BACKEND_URL',
  defaultValue: 'wss://voila-voice.onrender.com/ws',
);

String get backendUrl {
  var url = _rawBackendUrl.trim();

  if (url.startsWith('https://')) {
    url = url.replaceFirst('https://', 'wss://');
  } else if (url.startsWith('http://')) {
    url = url.replaceFirst('http://', 'ws://');
  }

  if (!url.startsWith('ws://') && !url.startsWith('wss://')) {
    url = 'wss://voila-voice.onrender.com/ws';
  }

  if (!url.endsWith('/ws')) {
    url = url.endsWith('/') ? '${url}ws' : '$url/ws';
  }

  return url;
}


@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  // BUG-09 fix: Only init if not already initialized (prevents FirebaseException on Android)
  if (Firebase.apps.isEmpty) await Firebase.initializeApp();
  debugPrint("Handling a background message: ${message.messageId}");
}


final ValueNotifier<ThemeMode> appThemeMode = ValueNotifier(ThemeMode.light);

Future<void> saveThemeMode(ThemeMode mode) async {
  appThemeMode.value = mode;
  try {
    const storage = FlutterSecureStorage();
    await storage.write(key: 'app_theme_mode', value: mode == ThemeMode.dark ? 'dark' : 'light');
  } catch (e) {
    debugPrint('Error persisting theme mode: $e');
  }
}

Future<void> loadThemeMode() async {
  try {
    const storage = FlutterSecureStorage();
    final saved = await storage.read(key: 'app_theme_mode');
    if (saved == 'dark') {
      appThemeMode.value = ThemeMode.dark;
    } else if (saved == 'light') {
      appThemeMode.value = ThemeMode.light;
    }
  } catch (e) {
    debugPrint('Error loading saved theme mode: $e');
  }
}

class AppTokens {
  static const Color accent = Color(0xFFFF4500); // Blazing Orange / Coral
  static const Color accentSecondary = Color(0xFF00E5FF); // Electric Cyan
  
  static Color bg(bool isDark) => isDark ? const Color(0xFF09090B) : const Color(0xFFF4F4F5);
  static Color card(bool isDark) => isDark ? const Color(0xFF18181B) : Colors.white;
  static Color surface(bool isDark) => card(isDark);
  static Color cardAlt(bool isDark) => isDark ? const Color(0xFF27272A) : const Color(0xFFE4E4E7);
  
  static Color textPrimary(bool isDark) => isDark ? const Color(0xFFFAFAFA) : const Color(0xFF09090B);
  static Color textSecondary(bool isDark) => isDark ? const Color(0xFFA1A1AA) : const Color(0xFF71717A);
  
  static Color border(bool isDark) => isDark ? const Color(0xFF3F3F46) : const Color(0xFFD4D4D8);
  
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
// --- END TOKENS ---

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // Senior Optimization: Cap Flutter internal ImageCache to 35MB & 120 images (default: 100MB & 1000 images)
  PaintingBinding.instance.imageCache.maximumSizeBytes = 35 * 1024 * 1024;
  PaintingBinding.instance.imageCache.maximumSize = 120;

  // BUGFIX: Guard against duplicate-app exception if the engine is shared
  // and main() is somehow re-invoked (e.g., background isolate or cold-start via AssistantActivity)
  if (Firebase.apps.isEmpty) {
    await Firebase.initializeApp();
  }
  FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);
  await loadThemeMode();
  
  runApp(const VoiceCliApp());
}


class VoiceCliApp extends StatelessWidget {
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
}

class VoiceHomePage extends StatefulWidget {
  const VoiceHomePage({super.key});

  @override
  State<VoiceHomePage> createState() => _VoiceHomePageState();
}

class _TokenUsageRow extends StatelessWidget {
  final Map<String, dynamic> tokenData;
  const _TokenUsageRow({required this.tokenData});

  @override
  Widget build(BuildContext context) {
    if (tokenData.isEmpty) {
      return const Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: Row(
          children: [
            Icon(Icons.analytics_outlined, size: 16, color: Color(0xFF6B7280)),
            SizedBox(width: 8),
            Text(
              'Token usage: awaiting agent data...',
              style: TextStyle(color: Color(0xFF6B7280), fontSize: 13),
            ),
          ],
        ),
      );
    }
    final groqIn = tokenData['groq_session_in'] ?? 0;
    final groqOut = tokenData['groq_session_out'] ?? 0;
    final groqDayIn = tokenData['groq_day_in'] ?? 0;
    final groqDayOut = tokenData['groq_day_out'] ?? 0;
    final tpdLimit = tokenData['groq_tpd_limit'] ?? 0;
    final tpdRemain = tokenData['groq_tpd_remaining'] ?? 0;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.analytics_outlined, size: 16, color: Color(0xFF60A5FA)),
              const SizedBox(width: 8),
              Text(
                'Groq session: ${groqIn}in / ${groqOut}out tokens',
                style: const TextStyle(color: Color(0xFFE5E7EB), fontSize: 13),
              ),
            ],
          ),
          if (groqDayIn > 0 || groqDayOut > 0)
            Padding(
              padding: const EdgeInsets.only(left: 24, top: 2),
              child: Text(
                'Daily: ${groqDayIn}in / ${groqDayOut}out${tpdLimit > 0 ? " | ${tpdRemain}/${tpdLimit} remaining" : ""}',
                style: const TextStyle(color: Color(0xFF6B7280), fontSize: 11),
              ),
            ),
        ],
      ),
    );
  }
}


// ==========================================
// Claude/ChatGPT Style Pulse Wave Visualizer
// ==========================================
class PulseWaveVisualizer extends StatefulWidget {
  final bool isListening;
  final bool isSpeaking;
  final VoidCallback onTap;
  final double size;
  final double coreSize;

  const PulseWaveVisualizer({
    Key? key,
    required this.isListening,
    required this.isSpeaking,
    required this.onTap,
    this.size = 220.0,
    this.coreSize = 90.0,
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
    );
    if (widget.isListening || widget.isSpeaking) {
      _controller.repeat();
    }
  }

  @override
  void didUpdateWidget(PulseWaveVisualizer oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isListening || widget.isSpeaking) {
      if (!_controller.isAnimating) {
        _controller.repeat();
      }
    } else {
      if (_controller.isAnimating) {
        _controller.stop();
        _controller.reset();
      }
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    Color baseColor = widget.isSpeaking ? AppTokens.accentSecondary : AppTokens.accent;
    final double cSize = widget.coreSize;
    final double boxSize = widget.size;
    final double iconSize = cSize * 0.44;

    final coreButton = Container(
      width: cSize,
      height: cSize,
      decoration: BoxDecoration(
        color: baseColor,
        shape: BoxShape.circle,
        boxShadow: [
          BoxShadow(
            color: baseColor.withOpacity(0.35),
            blurRadius: cSize * 0.22,
            spreadRadius: 4,
          )
        ],
      ),
      child: Center(
        child: Icon(
          widget.isSpeaking ? Icons.graphic_eq_rounded : Icons.mic_rounded,
          color: Colors.white,
          size: iconSize,
        ),
      ),
    );

    // ZERO IDLE OVERHEAD: Return static button directly when not listening or speaking
    if (!widget.isListening && !widget.isSpeaking) {
      return GestureDetector(
        behavior: HitTestBehavior.opaque,
        onTap: widget.onTap,
        child: SizedBox(
          width: boxSize,
          height: boxSize,
          child: Center(child: coreButton),
        ),
      );
    }

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: widget.onTap,
      child: RepaintBoundary(
        child: AnimatedBuilder(
          animation: _controller,
          builder: (context, child) {
            double wave1 = 1.0 + (_controller.value * 1.5);
            double wave2 = 1.0 + (((_controller.value + 0.3) % 1.0) * 1.2);
            double wave3 = 1.0 + (((_controller.value + 0.6) % 1.0) * 0.9);
            double corePulse = (cSize * 0.11) + (math.sin(_controller.value * math.pi * 2) * 5);

            return SizedBox(
              width: boxSize,
              height: boxSize,
              child: Stack(
                alignment: Alignment.center,
                children: [
                Transform.scale(
                  scale: wave1,
                  child: Container(
                    width: cSize, height: cSize,
                    decoration: BoxDecoration(shape: BoxShape.circle, border: Border.all(color: baseColor.withOpacity(0.05 * (1.0 - _controller.value)), width: 2)),
                  ),
                ),
                Transform.scale(
                  scale: wave2,
                  child: Container(
                    width: cSize, height: cSize,
                    decoration: BoxDecoration(shape: BoxShape.circle, color: baseColor.withOpacity(0.1 * (1.0 - ((_controller.value + 0.3) % 1.0)))),
                  ),
                ),
                Transform.scale(
                  scale: wave3,
                  child: Container(
                    width: cSize, height: cSize,
                    decoration: BoxDecoration(shape: BoxShape.circle, color: baseColor.withOpacity(0.15 * (1.0 - ((_controller.value + 0.6) % 1.0)))),
                  ),
                ),
                Container(
                  width: cSize,
                  height: cSize,
                  decoration: BoxDecoration(
                    color: baseColor,
                    shape: BoxShape.circle,
                    boxShadow: [
                      BoxShadow(
                        color: baseColor.withOpacity(0.4),
                        blurRadius: cSize * 0.33,
                        spreadRadius: corePulse,
                      )
                    ]
                  ),
                  child: Center(
                    child: Icon(
                      widget.isSpeaking ? Icons.graphic_eq_rounded : Icons.mic_rounded,
                      color: Colors.white,
                      size: iconSize,
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    ),
  );
}
}




// ─── LIGHTWEIGHT FLUID & RIPPLE PHYSICS ENGINE ───

class FluidPhysicsScope extends InheritedWidget {
  final Animation<double> animation;
  final bool isListening;
  final bool isSpeaking;
  final bool isThinking;
  final bool isDark;

  const FluidPhysicsScope({
    Key? key,
    required this.animation,
    required this.isListening,
    required this.isSpeaking,
    required this.isThinking,
    required this.isDark,
    required Widget child,
  }) : super(key: key, child: child);

  static FluidPhysicsScope? of(BuildContext context) {
    return context.dependOnInheritedWidgetOfExactType<FluidPhysicsScope>();
  }

  @override
  bool updateShouldNotify(FluidPhysicsScope oldWidget) {
    return animation != oldWidget.animation ||
        isListening != oldWidget.isListening ||
        isSpeaking != oldWidget.isSpeaking ||
        isThinking != oldWidget.isThinking ||
        isDark != oldWidget.isDark;
  }
}

class FloatingWaterElement extends StatelessWidget {
  final double distanceFactor; // -1.0 (top) to +1.0 (bottom), 0.0 is center
  final Widget child;

  const FloatingWaterElement({
    Key? key,
    required this.distanceFactor,
    required this.child,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final scope = FluidPhysicsScope.of(context);
    if (scope == null) return child;

    return AnimatedBuilder(
      animation: scope.animation,
      builder: (context, _) {
        final double t = scope.animation.value;
        final bool active = scope.isListening || scope.isSpeaking || scope.isThinking;

        // Dynamic wave physics parameters:
        final double amp = active ? 3.5 : 1.2;
        final double maxTilt = active ? 0.015 : 0.005;

        // Wave propagation phase lag from mic center:
        final double phase = (t * 2 * math.pi) - (distanceFactor.abs() * 2.2);

        final double dy = math.sin(phase) * amp;
        final double tilt = math.cos(phase) * maxTilt * (distanceFactor < 0 ? -1.0 : 1.0);
        final double dx = math.sin(phase * 0.5) * (amp * 0.35);

        return Transform(
          transform: Matrix4.identity()
            ..translate(dx, dy)
            ..rotateZ(tilt),
          alignment: Alignment.center,
          child: child,
        );
      },
    );
  }
}

class FluidWaterOverlayContainer extends StatefulWidget {
  final bool isDark;
  final bool isListening;
  final bool isSpeaking;
  final bool isThinking;
  final Widget child;

  const FluidWaterOverlayContainer({
    Key? key,
    required this.isDark,
    required this.isListening,
    required this.isSpeaking,
    required this.isThinking,
    required this.child,
  }) : super(key: key);

  @override
  _FluidWaterOverlayContainerState createState() => _FluidWaterOverlayContainerState();
}

class _FluidWaterOverlayContainerState extends State<FluidWaterOverlayContainer>
    with SingleTickerProviderStateMixin, WidgetsBindingObserver {
  late AnimationController _fluidController;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _fluidController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 2800),
    )..repeat();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive ||
        state == AppLifecycleState.detached ||
        state.name == 'hidden') {
      if (_fluidController.isAnimating) {
        _fluidController.stop();
      }
    } else if (state == AppLifecycleState.resumed) {
      if (!_fluidController.isAnimating) {
        _fluidController.repeat();
      }
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _fluidController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return FluidPhysicsScope(
      animation: _fluidController,
      isListening: widget.isListening,
      isSpeaking: widget.isSpeaking,
      isThinking: widget.isThinking,
      isDark: widget.isDark,
      child: Stack(
        children: [
          // Background liquid canvas with water ripples and caustic refractions
          Positioned.fill(
            child: RepaintBoundary(
              child: AnimatedBuilder(
                animation: _fluidController,
                builder: (context, _) {
                  return CustomPaint(
                    painter: FluidLiquidPainter(
                      progress: _fluidController.value,
                      isListening: widget.isListening,
                      isSpeaking: widget.isSpeaking,
                      isThinking: widget.isThinking,
                      isDark: widget.isDark,
                    ),
                  );
                },
              ),
            ),
          ),
          // Content layer with floating buoyant elements
          widget.child,
        ],
      ),
    );
  }
}

class FluidLiquidPainter extends CustomPainter {
  final double progress;
  final bool isListening;
  final bool isSpeaking;
  final bool isThinking;
  final bool isDark;

  static final Paint _glowPaint = Paint();
  static final Paint _crestPaint = Paint()
    ..style = PaintingStyle.stroke
    ..strokeWidth = 1.4;
  static final Paint _tintPaint = Paint()
    ..style = PaintingStyle.stroke
    ..strokeWidth = 2.8;
  static final Paint _causticPaint = Paint()
    ..style = PaintingStyle.stroke
    ..strokeWidth = 1.0;
  static final Path _wavePath = Path();
  static final Path _causticPath = Path();

  FluidLiquidPainter({
    required this.progress,
    required this.isListening,
    required this.isSpeaking,
    required this.isThinking,
    required this.isDark,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final bool active = isListening || isSpeaking || isThinking;
    final Offset center = Offset(size.width / 2, size.height * 0.52);

    // 1. Ambient fluid glow radiating from the mic position
    final Color glowColor = isThinking
        ? const Color(0xFFEF4444)
        : (isSpeaking
            ? AppTokens.accentSecondary
            : (isListening ? AppTokens.accent : (isDark ? const Color(0xFF6366F1) : const Color(0xFF00E5FF))));

    _glowPaint.shader = RadialGradient(
      colors: [
        glowColor.withOpacity(active ? (isDark ? 0.22 : 0.16) : (isDark ? 0.08 : 0.05)),
        Colors.transparent,
      ],
      radius: 0.75,
    ).createShader(Rect.fromCircle(center: center, radius: size.width * 0.65));
    canvas.drawRect(Offset.zero & size, _glowPaint);

    // 2. Concentric harmonic water ripples with fluid turbulence
    final double maxRadius = size.width * 0.62;
    const double minRadius = 36.0;

    for (int i = 0; i < 3; i++) {
      final double ringProgress = (progress + (i / 3.0)) % 1.0;
      final double r = minRadius + (ringProgress * (maxRadius - minRadius));
      final double alpha = (1.0 - ringProgress) * (active ? 0.36 : 0.16);

      _wavePath.reset();
      const int segments = 28;
      for (int s = 0; s <= segments; s++) {
        final double theta = (s / segments) * 2 * math.pi;
        final double wobble = math.sin((theta * 4) + (progress * 2 * math.pi)) * (active ? 3.0 : 1.2) +
            math.cos((theta * 2) - (progress * 2 * math.pi)) * (active ? 1.8 : 0.8);
        final double rad = r + wobble;
        final double px = center.dx + rad * math.cos(theta);
        final double py = center.dy + rad * math.sin(theta);
        if (s == 0) {
          _wavePath.moveTo(px, py);
        } else {
          _wavePath.lineTo(px, py);
        }
      }
      _wavePath.close();

      // Specular highlight crest
      _crestPaint.color = isDark
          ? Colors.white.withOpacity(alpha * 0.70)
          : Colors.white.withOpacity(alpha * 0.90);
      canvas.drawPath(_wavePath, _crestPaint);

      // Liquid refraction body
      _tintPaint.color = glowColor.withOpacity(alpha * 0.35);
      canvas.drawPath(_wavePath, _tintPaint);
    }

    // 3. Gentle fluid caustic contour lines across the water surface
    for (int w = 0; w < 2; w++) {
      final double waveY = (size.height * (0.32 + (w * 0.40))) + math.sin((progress * 2 * math.pi) + w) * 3.5;
      _causticPath.reset();
      _causticPath.moveTo(0, waveY);
      for (double x = 0; x <= size.width; x += 16) {
        final double cy = waveY + math.sin((x / size.width * 3 * math.pi) + (progress * 2 * math.pi) + (w * 1.5)) * 3.8;
        _causticPath.lineTo(x, cy);
      }
      _causticPaint.color = (isDark ? Colors.white : Colors.cyanAccent).withOpacity(isDark ? 0.04 : 0.10);
      canvas.drawPath(_causticPath, _causticPaint);
    }
  }

  @override
  bool shouldRepaint(covariant FluidLiquidPainter oldDelegate) {
    return oldDelegate.progress != progress ||
        oldDelegate.isListening != isListening ||
        oldDelegate.isSpeaking != isSpeaking ||
        oldDelegate.isThinking != isThinking ||
        oldDelegate.isDark != isDark;
  }
}

class Volumetric3DMicButton extends StatefulWidget {
  final bool isListening;
  final bool isSpeaking;
  final bool isThinking;
  final bool isDark;
  final VoidCallback onTap;

  const Volumetric3DMicButton({
    Key? key,
    required this.isListening,
    required this.isSpeaking,
    required this.isThinking,
    required this.isDark,
    required this.onTap,
  }) : super(key: key);

  @override
  _Volumetric3DMicButtonState createState() => _Volumetric3DMicButtonState();
}

class _Volumetric3DMicButtonState extends State<Volumetric3DMicButton> with SingleTickerProviderStateMixin {
  late AnimationController _pulseController;
  bool _isPressed = false;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1800),
    );
    if (widget.isListening || widget.isSpeaking || widget.isThinking) {
      _pulseController.repeat();
    }
  }

  @override
  void didUpdateWidget(Volumetric3DMicButton oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (widget.isListening || widget.isSpeaking || widget.isThinking) {
      if (!_pulseController.isAnimating) {
        _pulseController.repeat();
      }
    } else {
      if (_pulseController.isAnimating) {
        _pulseController.stop();
        _pulseController.reset();
      }
    }
  }

  @override
  void dispose() {
    _pulseController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bool active = widget.isListening || widget.isSpeaking || widget.isThinking;
    final Color activeAccent = widget.isThinking
        ? const Color(0xFFEF4444)
        : (widget.isSpeaking ? AppTokens.accentSecondary : AppTokens.accent);

    const double outerBoxSize = 120.0;
    const double domeSize = 64.0;

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTapDown: (_) => setState(() => _isPressed = true),
      onTapUp: (_) {
        setState(() => _isPressed = false);
        widget.onTap();
      },
      onTapCancel: () => setState(() => _isPressed = false),
      child: RepaintBoundary(
        child: AnimatedBuilder(
          animation: _pulseController,
        builder: (context, _) {
          final double t = _pulseController.value;

          return SizedBox(
            width: outerBoxSize,
            height: outerBoxSize,
            child: Stack(
              alignment: Alignment.center,
              children: [
                // Layer 1: Expanding underwater shockwaves / ripples
                if (active) ...[
                  for (int i = 0; i < 2; i++)
                    Transform.scale(
                      scale: 1.0 + (((t + (i * 0.5)) % 1.0) * 0.75),
                      child: Container(
                        width: domeSize + 10,
                        height: domeSize + 10,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          border: Border.all(
                            color: activeAccent.withOpacity((1.0 - ((t + (i * 0.5)) % 1.0)) * 0.35),
                            width: 2.0,
                          ),
                        ),
                      ),
                    ),
                ],

                // Layer 2: 3D Outer Bevel Ring & Deep Fluid Ambient Shadow
                AnimatedScale(
                  scale: _isPressed ? 0.92 : 1.0,
                  duration: const Duration(milliseconds: 120),
                  curve: Curves.easeOutCubic,
                  child: Container(
                    width: domeSize + 10,
                    height: domeSize + 10,
                    decoration: BoxDecoration(
                      shape: BoxShape.circle,
                      gradient: LinearGradient(
                        begin: Alignment.topLeft,
                        end: Alignment.bottomRight,
                        colors: widget.isDark
                            ? [
                                Colors.white.withOpacity(0.35),
                                Colors.white.withOpacity(0.05),
                                Colors.black.withOpacity(0.65),
                              ]
                            : [
                                Colors.white.withOpacity(0.95),
                                Colors.white.withOpacity(0.40),
                                const Color(0xFF94A3B8).withOpacity(0.60),
                              ],
                        stops: const [0.0, 0.4, 1.0],
                      ),
                      boxShadow: [
                        BoxShadow(
                          color: Colors.black.withOpacity(widget.isDark ? 0.55 : 0.22),
                          blurRadius: 18,
                          offset: const Offset(0, 8),
                        ),
                        if (active)
                          BoxShadow(
                            color: activeAccent.withOpacity(0.45),
                            blurRadius: 22,
                            spreadRadius: 2 + (math.sin(t * 2 * math.pi) * 3),
                          ),
                      ],
                    ),
                    child: Center(
                      // Layer 3: 3D Spherical Dome Body
                      child: Container(
                        width: domeSize,
                        height: domeSize,
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          gradient: RadialGradient(
                            center: const Alignment(-0.35, -0.42),
                            radius: 0.88,
                            colors: widget.isDark
                                ? (active
                                    ? [
                                        activeAccent.withOpacity(0.95),
                                        activeAccent,
                                        activeAccent.withRed(activeAccent.red ~/ 1.4).withGreen(activeAccent.green ~/ 1.4),
                                        const Color(0xFF0F111A),
                                      ]
                                    : [
                                        const Color(0xFF4A526D),
                                        const Color(0xFF282D3E),
                                        const Color(0xFF181B26),
                                        const Color(0xFF0C0E14),
                                      ])
                                : (active
                                    ? [
                                        Colors.white,
                                        activeAccent.withOpacity(0.92),
                                        activeAccent,
                                        activeAccent.withOpacity(0.85),
                                      ]
                                    : [
                                        Colors.white,
                                        const Color(0xFFF1F5F9),
                                        const Color(0xFFCBD5E1),
                                        const Color(0xFF94A3B8),
                                      ]),
                            stops: const [0.0, 0.32, 0.72, 1.0],
                          ),
                        ),
                        child: Stack(
                          alignment: Alignment.center,
                          children: [
                            // Layer 4: Glass specular curved crest reflection
                            Positioned(
                              top: 6,
                              child: Container(
                                width: domeSize * 0.52,
                                height: domeSize * 0.24,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(100),
                                  gradient: LinearGradient(
                                    begin: Alignment.topCenter,
                                    end: Alignment.bottomCenter,
                                    colors: [
                                      Colors.white.withOpacity(widget.isDark ? 0.45 : 0.85),
                                      Colors.white.withOpacity(0.0),
                                    ],
                                  ),
                                ),
                              ),
                            ),

                            // Layer 5: Embossed 3D Center Icon
                            Icon(
                              widget.isThinking
                                  ? Icons.stop_rounded
                                  : (widget.isSpeaking ? Icons.graphic_eq_rounded : Icons.mic_rounded),
                              color: active
                                  ? Colors.white
                                  : (widget.isDark ? Colors.white70 : const Color(0xFF334155)),
                              size: 28,
                              shadows: [
                                Shadow(
                                  color: Colors.black.withOpacity(0.55),
                                  offset: const Offset(0, 1.5),
                                  blurRadius: 4,
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    ),
  );
}
}




// ─── HIGH-PERFORMANCE STATIC REGEX SPEECH NORMALIZER ───
class SpeechNormalizer {
  static final RegExp _urlRegex = RegExp(r'https?://[^\s)\]]+');
  static final RegExp _winPathRegex = RegExp(r'[a-zA-Z]:\\[^\s)\]]+');
  static final RegExp _unixPathRegex = RegExp(r'/(?:[a-zA-Z0-9_.-]+/)+[a-zA-Z0-9_.-]+');
  static final RegExp _uuidRegex = RegExp(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b');
  static final RegExp _hexHashRegex = RegExp(r'\b[0-9a-fA-F]{12,}\b');
  static final RegExp _dashRegex = RegExp(r'\s+[-]+\s+');
  static final RegExp _leadingDashRegex = RegExp(r'^\s*[-]+\s*');
  static final RegExp _ellipsisRegex = RegExp(r'\.{2,}');
  static final RegExp _bracketRegex = RegExp(r'[\[\]{}|\\<>]');
  static final RegExp _spaceRegex = RegExp(r'\s+');
  static final RegExp _fullStopRegex = RegExp(r'\.([A-Za-z])');
  static final RegExp chunkRegex = RegExp(r'([^.?!]+[.?!]*)');

  static String normalize(String text) {
    String normalized = text;
    normalized = normalized.replaceAll(_urlRegex, 'the link');
    normalized = normalized.replaceAll(_winPathRegex, 'the file path');
    normalized = normalized.replaceAll(_unixPathRegex, 'the file path');
    normalized = normalized.replaceAll(_uuidRegex, 'an ID');
    normalized = normalized.replaceAll(_hexHashRegex, 'a hash');

    normalized = normalized.replaceAll('**', '');
    normalized = normalized.replaceAll('*', '');
    normalized = normalized.replaceAll('__', '');
    normalized = normalized.replaceAll('_', ' ');
    normalized = normalized.replaceAll('#', '');

    normalized = normalized.replaceAll(_dashRegex, ' ');
    normalized = normalized.replaceAll(_leadingDashRegex, ' ');
    normalized = normalized.replaceAll(_ellipsisRegex, '. ');
    normalized = normalized.replaceAll(_bracketRegex, ' ');
    normalized = normalized.replaceAll(_spaceRegex, ' ');

    normalized = normalized.replaceAll('&&', ' and ');
    normalized = normalized.replaceAll('||', ' or ');
    normalized = normalized.replaceAll('!=', ' not equal to ');
    normalized = normalized.replaceAll('==', ' equals ');
    normalized = normalized.replaceAll('>=', ' greater than or equal to ');
    normalized = normalized.replaceAll('<=', ' less than or equal to ');

    normalized = normalized.replaceAll(' | ', ' or ');
    normalized = normalized.replaceAll(' + ', ' plus ');
    normalized = normalized.replaceAll(' - ', ' minus ');
    normalized = normalized.replaceAll(' = ', ' equals ');
    normalized = normalized.replaceAll(' < ', ' less than ');
    normalized = normalized.replaceAll(' > ', ' greater than ');
    normalized = normalized.replaceAll('/', ' slash ');
    normalized = normalized.replaceAll('\\', ' backslash ');

    normalized = normalized.replaceAllMapped(_fullStopRegex, (match) => '. ${match.group(1)}');
    normalized = normalized.replaceAll('\n', '. ');
    normalized = normalized.replaceAll(_spaceRegex, ' ').trim();

    return normalized;
  }
}

class _VoiceHomePageState extends State<VoiceHomePage> with WidgetsBindingObserver {
  WebSocketChannel? _channel;  // nullable - prevents LateInitializationError before first connect
  StreamSubscription? _wsSubscription;  // stored so we can cancel on dispose/reconnect
  StreamSubscription? _fcmRefreshSubscription;  // BUG-15 fix: FCM refresh listener cancellation
  StreamSubscription? _fcmOpenedAppSubscription;
  StreamSubscription? _fcmMessageSubscription;  // FCM-02 fix

  static const platform = MethodChannel('com.voila/intent');
  bool _showFlowchart = false;
  bool _showTextInput = false;
  bool _isAssistant = false;
  String? _temporaryAssistantImage;
  Timer? _assistantImageTimer;
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  final GlobalKey<ScaffoldState> _scaffoldKey = GlobalKey<ScaffoldState>();
  final _storage = const FlutterSecureStorage();
  List<String> _modelsList = [];
  String _selectedModel = '';
  bool _isFetchingModels = false;
  String _cachedSecurityPhrase = '';
  final List<Map<String, dynamic>> _messagesShell = [];
  final List<Map<String, dynamic>> _messagesAgent = [];
  List<Map<String, dynamic>> get _messages => _currentMode.toUpperCase() == 'AGENT' ? _messagesAgent : _messagesShell;
  bool _isThinking = false;
  final Set<String> _thinkingSessions = <String>{};
  String _currentStatus = 'Processing...';
  bool _isDataDeparting = false;
  bool _isDataArriving = false;
  bool _willTalk = true;
  bool _graphifyEnabled = false;
  bool _quietHoursEnabled = false;
  int _quietHoursStartHour = 22; // 10 PM
  int _quietHoursEndHour = 7;    // 7 AM

  bool _isQuietHoursActive() {
    if (!_quietHoursEnabled) return false;
    final now = DateTime.now();
    final hour = now.hour;
    if (_quietHoursStartHour > _quietHoursEndHour) {
      return hour >= _quietHoursStartHour || hour < _quietHoursEndHour;
    } else {
      return hour >= _quietHoursStartHour && hour < _quietHoursEndHour;
    }
  }
  Timer? _standbyGraceTimer;
  bool _isInForeground = true;
  bool _isStandbyActive = false;
  String? _activeJobId;
  String _activeJobStatus = '';
  String _activeJobSummary = '';
  FlutterTts flutterTts = FlutterTts();
  
  String _activeDevice = '';
  String _previousDictationText = "";
  bool _isConnected = false;
  bool _isHealthy = false;
  bool _localAgentConnected = false;
  String _currentAiSubtitle = "";
  bool _showSubtitles = true;
  Timer? _silenceTimer;
  int _silenceWarningCount = 0;
  int _lastWordCount = 0;
  DateTime _lastSpeechTime = DateTime.now();
  int _overlapTriggers = 0;

  void _addMessage(Map<String, dynamic> msg) {
    final content = (msg['content'] as String? ?? '').trim();
    final summary = (msg['summary'] as String? ?? '').trim();
    // Drop ghost empty bubble if response content and summary are both empty
    if (msg['type'] == 'response' && content.isEmpty && !content.startsWith('__IMAGE__:')) {
      if (summary.isNotEmpty) {
        msg['content'] = summary;
      } else {
        return; // Drop empty ghost message completely
      }
    }
    if (msg['type'] == 'error') {
      HapticFeedback.heavyImpact();
    }
    if (_currentMode.toUpperCase() == 'AGENT') {
      _messagesAgent.add(msg);
      if (_messagesAgent.length > 200) _messagesAgent.removeAt(0);
      if (_currentConversationId.isNotEmpty) {
        _setConversationCache(_currentConversationId, List.from(_messagesAgent));
        _saveConversationHistoryToDiskCache(_currentConversationId, _messagesAgent);
      }
    } else {
      _messagesShell.add(msg);
      if (_messagesShell.length > 200) _messagesShell.removeAt(0);
    }
  }

  void _triggerDataDeparting() {
    if (mounted) setState(() => _isDataDeparting = true);
    Future.delayed(const Duration(milliseconds: 1500), () {
      if (mounted) setState(() => _isDataDeparting = false);
    });
  }

  void _triggerDataArriving() {
    setState(() => _isDataArriving = true);
    Future.delayed(const Duration(milliseconds: 1500), () {
      if (mounted) setState(() => _isDataArriving = false);
    });
  }
  String _backendStatus = 'Checking...';
  Timer? _healthCheckTimer;
  Timer? _bgTaskTimer;
  List<dynamic> _bgTasks = [];
  String? _dismissedWatchdogTaskId;
  Map<String, dynamic>? _activeClipboardSuggestion;
  Timer? _clipboardSuggestionTimer;
  Map<String, dynamic>? _activeWorkdayBriefing;
  Map<String, dynamic>? _activeNightlyAuditReport;
  int _reconnectAttempts = 0;
  Map<String, dynamic> _devices = {};
  String? _currentDeviceId;
  String? _currentDeviceName;
  String _sessionId = '';
  String _sessionToken = '';
  int? _sessionExpiresAt; // Unix timestamp
  String _currentMode = 'agent';
  Map<String, dynamic> _savedDevices = {};
  String _currentConversationId = '';
  List<Map<String, String>> _conversations = [];
  final Map<String, List<Map<String, dynamic>>> _conversationMessagesCache = {};

  void _setConversationCache(String id, List<Map<String, dynamic>> messages) {
    if (id.isEmpty) return;
    _conversationMessagesCache.remove(id);
    _conversationMessagesCache[id] = messages;
    // Bounded L1 cache: Keep at most 6 recent conversations in RAM, older ones safely retained in disk cache
    while (_conversationMessagesCache.length > 6) {
      _conversationMessagesCache.remove(_conversationMessagesCache.keys.first);
    }
  }

  Future<File> _getCacheFile(String filename) async {
    final dir = await getApplicationDocumentsDirectory();
    return File('${dir.path}/$filename');
  }

  Future<void> _saveConversationsToDiskCache(List<dynamic> list) async {
    try {
      final file = await _getCacheFile('conversations_index_cache.json');
      await file.writeAsString(jsonEncode(list));
    } catch (e) {
      debugPrint('Failed to save conversations to disk cache: $e');
    }
  }

  Future<void> _loadConversationsFromDiskCache() async {
    try {
      final file = await _getCacheFile('conversations_index_cache.json');
      if (await file.exists()) {
        final raw = await file.readAsString();
        final decoded = jsonDecode(raw);
        if (decoded is List && mounted) {
          setState(() {
            _conversations = decoded.map((x) {
              try {
                return Map<String, String>.from(
                  (x as Map).map((k, v) => MapEntry(k.toString(), v?.toString() ?? '')));
              } catch (_) { return <String, String>{}; }
            }).where((m) => m.isNotEmpty && m.containsKey('id')).toList();
          });
        }
      }
    } catch (e) {
      debugPrint('Failed to load conversations from disk cache: $e');
    }
  }

  Future<void> _saveConversationHistoryToDiskCache(String convId, List<Map<String, dynamic>> msgs) async {
    try {
      final file = await _getCacheFile('conv_history_${convId}.json');
      await file.writeAsString(jsonEncode(msgs));
    } catch (e) {
      debugPrint('Failed to save conv history cache: $e');
    }
  }

  Future<List<Map<String, dynamic>>> _loadConversationHistoryFromDiskCache(String convId) async {
    try {
      final file = await _getCacheFile('conv_history_${convId}.json');
      if (await file.exists()) {
        final raw = await file.readAsString();
        final decoded = jsonDecode(raw);
        if (decoded is List) {
          final list = decoded.map((x) => Map<String, dynamic>.from(x as Map)).toList();
          _setConversationCache(convId, list);
          return list;
        }
      }
    } catch (e) {
      debugPrint('Failed to load conv history cache: $e');
    }
    return [];
  }

  Future<void> _removeConversationFromCache(String convId) async {
    _conversationMessagesCache.remove(convId);
    try {
      final file = await _getCacheFile('conv_history_${convId}.json');
      if (await file.exists()) {
        await file.delete();
      }
    } catch (_) {}
  }

  void _closeDrawerSafely() {
    if (_scaffoldKey.currentState?.isDrawerOpen ?? false) {
      _scaffoldKey.currentState?.closeDrawer();
    } else if (Navigator.of(context).canPop()) {
      Navigator.of(context).pop();
    }
  }

  void _upsertActiveConversation(String userText) {
    if (_currentConversationId.isEmpty) {
      _currentConversationId = 'conv_' + const Uuid().v4().substring(0, 8);
    }
    final cleanPrompt = userText.trim().replaceAll('\n', ' ');
    final shortTitle = cleanPrompt.length > 35 ? cleanPrompt.substring(0, 32) + '...' : cleanPrompt;
    final snippet = cleanPrompt.length > 55 ? cleanPrompt.substring(0, 52) + '...' : cleanPrompt;
    final nowMs = DateTime.now().millisecondsSinceEpoch.toString();

    final existingIndex = _conversations.indexWhere((c) => c['id'] == _currentConversationId);
    if (existingIndex >= 0) {
      final existing = Map<String, String>.from(_conversations[existingIndex]);
      existing['updated_at'] = nowMs;
      existing['last_snippet'] = snippet;
      final count = int.tryParse(existing['message_count'] ?? '1') ?? 1;
      existing['message_count'] = (count + 1).toString();
      _conversations.removeAt(existingIndex);
      _conversations.insert(0, existing);
    } else {
      _conversations.insert(0, {
        'id': _currentConversationId,
        'title': shortTitle.isNotEmpty ? shortTitle : 'New Conversation',
        'updated_at': nowMs,
        'created_at': nowMs,
        'message_count': '1',
        'last_snippet': snippet,
      });
    }
    _saveConversationsToDiskCache(_conversations);
  }

  void _updateActiveConversationSnippet(String assistantResponse) {
    if (_currentConversationId.isEmpty) return;
    final cleanResp = assistantResponse.trim().replaceAll('\n', ' ');
    final snippet = cleanResp.length > 60 ? cleanResp.substring(0, 57) + '...' : cleanResp;
    final nowMs = DateTime.now().millisecondsSinceEpoch.toString();

    final idx = _conversations.indexWhere((c) => c['id'] == _currentConversationId);
    if (idx >= 0) {
      final item = Map<String, String>.from(_conversations[idx]);
      item['last_snippet'] = snippet;
      item['updated_at'] = nowMs;
      final count = int.tryParse(item['message_count'] ?? '1') ?? 1;
      item['message_count'] = (count + 1).toString();
      if (mounted) {
        setState(() {
          _conversations.removeAt(idx);
          _conversations.insert(0, item);
        });
      }
      _saveConversationsToDiskCache(_conversations);
    }
  }

  String _getActiveConversationTitle() {
    if (_currentConversationId.isEmpty) return 'Active Chat';
    final found = _conversations.firstWhere((c) => c['id'] == _currentConversationId, orElse: () => {});
    if (found.isNotEmpty && found['title'] != null && found['title']!.isNotEmpty) {
      return found['title']!;
    }
    return 'Chat ' + (_currentConversationId.length > 10 ? _currentConversationId.substring(0, 9) : _currentConversationId);
  }

  DateTime _parseConversationDate(String? raw) {
    if (raw == null || raw.isEmpty) return DateTime.now();
    final ms = int.tryParse(raw);
    if (ms != null && ms > 0) {
      if (ms < 10000000000) {
        return DateTime.fromMillisecondsSinceEpoch(ms * 1000);
      }
      return DateTime.fromMillisecondsSinceEpoch(ms);
    }
    return DateTime.tryParse(raw) ?? DateTime.now();
  }

  void _sortConversations() {
    _conversations.sort((a, b) {
      final aPinned = a['is_pinned'] == 'true';
      final bPinned = b['is_pinned'] == 'true';
      if (aPinned != bPinned) {
        return aPinned ? -1 : 1;
      }
      final aTime = _parseConversationDate(a['updated_at'] ?? a['created_at']);
      final bTime = _parseConversationDate(b['updated_at'] ?? b['created_at']);
      return bTime.compareTo(aTime);
    });
  }

  Map<String, List<Map<String, String>>> _categorizeConversations() {
    final now = DateTime.now();
    final todayStart = DateTime(now.year, now.month, now.day);
    final yesterdayStart = todayStart.subtract(const Duration(days: 1));
    final sevenDaysAgo = todayStart.subtract(const Duration(days: 7));

    final Map<String, List<Map<String, String>>> categorized = {
      'Pinned': [],
      'Today': [],
      'Yesterday': [],
      'Previous 7 Days': [],
      'Older': [],
    };

    for (final conv in _conversations) {
      if (conv['is_pinned'] == 'true') {
        categorized['Pinned']!.add(conv);
        continue;
      }
      final d = _parseConversationDate(conv['updated_at'] ?? conv['created_at']);
      if (d.isAfter(todayStart) || d.isAtSameMomentAs(todayStart)) {
        categorized['Today']!.add(conv);
      } else if (d.isAfter(yesterdayStart)) {
        categorized['Yesterday']!.add(conv);
      } else if (d.isAfter(sevenDaysAgo)) {
        categorized['Previous 7 Days']!.add(conv);
      } else {
        categorized['Older']!.add(conv);
      }
    }

    return categorized;
  }
  List<Map<String, dynamic>> _securityAlerts = [];
  bool _isHostIsolated = false;
  double _sentinelPostureScore = 100.0;
  Map<String, dynamic> _lastTokenUsage = {};
  
  // Speech-to-text state
  final SpeechToText _speechToText = SpeechToText();
  bool _isListening = false;
  bool _isLiveSession = false;
  bool _isAiSpeaking = false;
  double _currentSoundLevel = 0.0;
  bool _speechAvailable = false;
  bool _speechInitialized = false;
  
  // Security phrase for backend operations
  String _securityPhrase = '';

  String? _fcmToken;
  final FlutterLocalNotificationsPlugin _flutterLocalNotificationsPlugin = FlutterLocalNotificationsPlugin();

  Future<void> _setupFCM() async {
    // REMAIN-09 fix: initialize local notifications plugin before use
    const initSettings = InitializationSettings(
      android: AndroidInitializationSettings('@mipmap/ic_launcher'),
    );
    await _flutterLocalNotificationsPlugin.initialize(initSettings);

    NotificationSettings settings = await FirebaseMessaging.instance.requestPermission(
      alert: true, announcement: false, badge: true, carPlay: false, criticalAlert: false, provisional: false, sound: true,
    );
    debugPrint('User granted permission: ${settings.authorizationStatus}');

    const AndroidNotificationChannel channel = AndroidNotificationChannel(
      'security_alerts_channel', 
      'High Severity Security Alerts', 
      description: 'This channel is used for important security alerts.',
      importance: Importance.max,
    );
    await _flutterLocalNotificationsPlugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);

    const AndroidNotificationChannel taskChannel = AndroidNotificationChannel(
      'bg_tasks_channel',
      'Autonomous Tasks & Watchdog',
      description: 'Real-time proactive notifications for background commands and builds.',
      importance: Importance.max,
    );
    await _flutterLocalNotificationsPlugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(taskChannel);

    String? token = await FirebaseMessaging.instance.getToken();
    if (token != null && mounted) {  // FCM-03 fix: widget may be gone by the time token arrives
      _fcmToken = token;
      _sendFCMToken(token);  // safe: _sendFCMToken checks _isConnected internally
    }

    _fcmRefreshSubscription = FirebaseMessaging.instance.onTokenRefresh.listen((newToken) {
      _fcmToken = newToken;
      _sendFCMToken(newToken);
    });

    _fcmOpenedAppSubscription = FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
      if (message.data['type'] == 'security_alert' && mounted) {  // FCM-04 fix
        _showSecurityAlerts();
      }
      if (message.data['type'] == 'task_finished' && message.data['summary'] != null) {
        final String? artifactPath = message.data['artifact_path']?.toString();
        final String summary = message.data['summary'].toString();
        String title = summary;
        if (artifactPath != null && artifactPath.isNotEmpty) {
          final segments = artifactPath.replaceAll('\\', '/').split('/');
          if (segments.isNotEmpty && segments.last.isNotEmpty) {
            title = segments.last;
          } else {
            title = 'Task result';
          }
        }
        if (artifactPath != null && artifactPath.isNotEmpty) {
        ArtifactsManager.addArtifact(
          title: title,
          content: artifactPath,
          source: 'fcm_task_finished',
        );
      }
        if (artifactPath != null && artifactPath.isNotEmpty) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const ArtifactsPage()),
              );
            }
          });
        }
      }
    });

    _fcmMessageSubscription = FirebaseMessaging.onMessage.listen((RemoteMessage message) {
      RemoteNotification? notification = message.notification;
      AndroidNotification? android = message.notification?.android;
      if (notification != null && android != null) {
        _flutterLocalNotificationsPlugin.show(
          notification.hashCode,
          notification.title,
          notification.body,
          const NotificationDetails(
            android: AndroidNotificationDetails(
              'security_alerts_channel',
              'High Severity Security Alerts',
              importance: Importance.max,
              priority: Priority.high,
            ),
          ),
        );
      }
      
      if (message.data['type'] == 'task_finished' && message.data['summary'] != null) {
        _speakSummary(message.data['summary']);
        
        final String? artifactPath = message.data['artifact_path']?.toString();
        final String summary = message.data['summary'].toString();
        
        String title = summary;
        if (artifactPath != null && artifactPath.isNotEmpty) {
          final segments = artifactPath.replaceAll('\\', '/').split('/');
          if (segments.isNotEmpty && segments.last.isNotEmpty) {
            title = segments.last;
          } else {
            title = 'Task result';
          }
        }
        
        if (artifactPath != null && artifactPath.isNotEmpty) {
        ArtifactsManager.addArtifact(
          title: title,
          content: artifactPath,
          source: 'fcm_task_finished',
        );
      }

        // Navigate to Artifacts if artifact_path is present
        if (artifactPath != null && artifactPath.isNotEmpty) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const ArtifactsPage()),
              );
            }
          });
        }
      }

      if (message.data['type'] == 'approval_required' && message.data['job_id'] != null) {
        _speakSummary("Security permission required: " + (message.data['summary'] ?? "Unknown"), isCritical: true);
        if (mounted) {
          _showApprovalDialog(message.data);
        }
      }
    });

    RemoteMessage? initialMessage = await FirebaseMessaging.instance.getInitialMessage();
    if (initialMessage != null) {
      if (initialMessage.data['type'] == 'security_alert' && mounted) {  // FCM-05 fix
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (mounted) _showSecurityAlerts();  // double-check inside callback
        });
      }
      if (initialMessage.data['type'] == 'task_finished' && initialMessage.data['summary'] != null) {
        final String? artifactPath = initialMessage.data['artifact_path']?.toString();
        final String summary = initialMessage.data['summary'].toString();
        String title = summary;
        if (artifactPath != null && artifactPath.isNotEmpty) {
          final segments = artifactPath.replaceAll('\\', '/').split('/');
          if (segments.isNotEmpty && segments.last.isNotEmpty) {
            title = segments.last;
          } else {
            title = 'Task result';
          }
        }
        if (artifactPath != null && artifactPath.isNotEmpty) {
        ArtifactsManager.addArtifact(
          title: title,
          content: artifactPath,
          source: 'fcm_task_finished',
        );
      }
        if (artifactPath != null && artifactPath.isNotEmpty) {
          WidgetsBinding.instance.addPostFrameCallback((_) {
            if (mounted) {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const ArtifactsPage()),
              );
            }
          });
        }
      }
    }
  }

  void _sendFCMToken(String token) {
    if (_activeDevice.isNotEmpty && _isConnected) {
      _channel?.sink.add(jsonEncode({
        'type': 'register_fcm_token',
        'device_id': _activeDevice,
        'token': token,
        'session_token': _sessionToken,
      }));
    }
  }

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadConversationsFromDiskCache();
    
    // FIX Bug #3: This is now the PRIMARY mechanism for AssistantActivity to signal
    // overlay mode. AssistantActivity.configureFlutterEngine invokes "onIntentChanged"
    // with true; AssistantActivity.onDestroy invokes it with false.
    platform.setMethodCallHandler((call) async {
      if (call.method == 'onIntentChanged') {
        // Null-safe: call.arguments may be null if the channel is called without args
        final bool isAssistant = (call.arguments as bool?) ?? false;
        if (mounted) {
          setState(() {
            _isAssistant = isAssistant;
          });
          // BUGFIX: Disable FlutterBackground foreground service when in overlay mode
          // to prevent Android system conflicts and audio focus issues.
          if (Platform.isAndroid) {
            if (_isAssistant) {
              FlutterBackground.disableBackgroundExecution();
            } else {
              _initBackground();
            }
          }
        }
      }
    });

    _checkIntent();
    _initBackground();
    _initTts();
    _loadSession();
    loadThemeMode();
    _storage.read(key: 'security_phrase').then((val) => _cachedSecurityPhrase = val ?? '');
    _storage.read(key: 'quiet_hours_enabled').then((val) {
      if (val != null && mounted) {
        setState(() => _quietHoursEnabled = val == 'true');
      }
    });
    _storage.read(key: 'show_subtitles').then((val) {
      if (val != null && mounted) {
        setState(() => _showSubtitles = val == 'true');
      }
    });
    _storage.read(key: 'will_talk').then((val) {
      if (val != null && mounted) {
        setState(() => _willTalk = val == 'true');
      }
    });
    _storage.read(key: 'graphify_enabled').then((val) {
      if (val != null && mounted) {
        setState(() => _graphifyEnabled = val == 'true');
      }
    });

    // Load cached token usage
    _storage.read(key: 'last_token_usage').then((cachedTokenUsage) {
      if (cachedTokenUsage != null && mounted) {
        try {
          setState(() {
            _lastTokenUsage = Map<String, dynamic>.from(jsonDecode(cachedTokenUsage));
          });
        } catch (_) {}
      }
    });

    // Load persisted security alerts
    _storage.read(key: 'security_alerts').then((cachedAlerts) {
      if (cachedAlerts != null && mounted) {
        try {
          final list = jsonDecode(cachedAlerts) as List;
          setState(() {
            _securityAlerts = list.map((e) => Map<String, dynamic>.from(e)).toList();
          });
        } catch (_) {}
      }
    });
    _setupWebSocket();
    _initializeSpeech();
    _setupFCM().catchError((e) => debugPrint('FCM setup error: $e'));  // FCM-01: errors now visible
  }

  Future<void> _checkIntent() async {
    try {
      final bool isAssistant = await platform.invokeMethod('isAssistantIntent');
      if (!mounted) return;  // REMAIN-07 fix
      setState(() {
        _isAssistant = isAssistant;
      });
    } catch (e) {
      debugPrint("Failed to get intent: $e");
    }
  }

  bool _isTaskOrCommandActive() {
    if (_isThinking || _thinkingSessions.isNotEmpty) return true;
    if (_activeJobId != null && _activeJobId!.isNotEmpty) {
      if (_activeJobStatus == 'running' || _activeJobStatus == 'queued' || _activeJobStatus == 'cancelling') {
        return true;
      }
    }
    if (_bgTasks.any((t) => t['status'] == 'running' || t['status'] == 'queued')) return true;
    if (_isListening || _isAiSpeaking || _isLiveSession) return true;
    return false;
  }

  Future<void> _ensureBackgroundExecutionEnabled({String? reason}) async {
    if (!Platform.isAndroid) return;
    if (_isAssistant) return; // Assistant overlay handles its own transparent window lifecycle
    
    _standbyGraceTimer?.cancel();
    _standbyGraceTimer = null;
    _isStandbyActive = false;

    try {
      final hasPermission = await FlutterBackground.hasPermissions;
      if (!hasPermission) return;

      if (!FlutterBackground.isBackgroundExecutionEnabled) {
        final androidConfig = FlutterBackgroundAndroidConfig(
          notificationTitle: "Voila Agent",
          notificationText: reason ?? "Task running in background...",
          notificationImportance: AndroidNotificationImportance.normal,
          notificationIcon: const AndroidResource(name: 'ic_launcher', defType: 'mipmap'),
        );
        await FlutterBackground.initialize(androidConfig: androidConfig);
        await FlutterBackground.enableBackgroundExecution();
        debugPrint('Voila: Foreground service enabled (${reason ?? "active task"})');
      }
    } catch (e) {
      debugPrint('Background execution error: $e');
    }
  }

  void _scheduleStandbyGracePeriod() {
    if (!Platform.isAndroid) return;
    if (_isInForeground) return; // User is active in app, no standby needed
    if (_isTaskOrCommandActive()) return; // Task running, keep alive

    _standbyGraceTimer?.cancel();

    // In quiet hours (10 PM - 7 AM), drop into deep standby in 30 seconds
    final graceDuration = _isQuietHoursActive() 
        ? const Duration(seconds: 30) 
        : const Duration(minutes: 4);

    debugPrint('Voila: Scheduling standby grace period (${graceDuration.inSeconds}s)');
    _standbyGraceTimer = Timer(graceDuration, () async {
      if (_isInForeground || _isTaskOrCommandActive()) {
        debugPrint('Voila: Standby aborted because app returned to foreground or task started');
        return;
      }
      await _enterDeepStandby();
    });
  }

  Future<void> _enterDeepStandby() async {
    if (!Platform.isAndroid) return;
    try {
      if (FlutterBackground.isBackgroundExecutionEnabled) {
        debugPrint('Voila: Entering Deep Standby - disabling foreground execution & releasing WakeLock');
        await FlutterBackground.disableBackgroundExecution();
        _isStandbyActive = true;
      }
      // Memory purge: Clear Flutter internal image caches upon entering standby
      PaintingBinding.instance.imageCache.clear();
      PaintingBinding.instance.imageCache.clearLiveImages();
    } catch (e) {
      debugPrint('Error entering deep standby: $e');
    }
  }

  Future<void> _initBackground() async {
    if (!Platform.isAndroid) return;  // BUG-25 fix: flutter_background is Android-only
    try {
      const androidConfig = FlutterBackgroundAndroidConfig(
        notificationTitle: "Voila Agent",
        notificationText: "Standby",
        notificationImportance: AndroidNotificationImportance.normal,
        notificationIcon: AndroidResource(name: 'ic_launcher', defType: 'mipmap'),
      );
      await FlutterBackground.initialize(androidConfig: androidConfig);
      // Progressive Background Architecture: do not force permanent 24/7 background execution
      // on initial launch while user is in the foreground.
    } catch (e) {
      debugPrint('Background execution initialization error: $e');
    }
  }


  void _fetchConversations() {
    if (_channel != null && _isConnected) {
      String targetDevice = _activeDevice;
      if (targetDevice.isEmpty && _devices.isNotEmpty) {
        targetDevice = _devices.keys.firstWhere((k) => k.startsWith('desktop-'), orElse: () => '');
        if (targetDevice.isNotEmpty) {
          _activeDevice = targetDevice;
        }
      }
      if (targetDevice.isEmpty && _savedDevices.isNotEmpty) {
        targetDevice = _savedDevices.keys.firstWhere((k) => k.startsWith('desktop-'), orElse: () => '');
        if (targetDevice.isNotEmpty) {
          _activeDevice = targetDevice;
        }
      }
      final msg = jsonEncode({
        "type": "get_conversations",
        "device_id": targetDevice,
        "session_token": _sessionToken
      });
      _channel?.sink.add(msg);
    }
  }
  
  void _startNewConversation() {
    _closeDrawerSafely();
    if (mounted) setState(() {
      _currentConversationId = 'conv_' + const Uuid().v4().substring(0, 8);
      _messagesAgent.clear();
      _messagesAgent.insert(0, {
        'type': 'system',
        'content': 'Started a new conversation. What would you like help with?',
        'timestamp': DateTime.now().toString(),
      });
    });
  }
  
  void _resumeConversation(String id, String title) async {
    if (!mounted) return;
    setState(() {
      _currentConversationId = id;
      _isThinking = _thinkingSessions.contains(id);
    });

    // 1. Instant L1 memory cache hit (0ms)
    if (_conversationMessagesCache.containsKey(id) && _conversationMessagesCache[id]!.isNotEmpty) {
      final cached = _conversationMessagesCache[id]!;
      _setConversationCache(id, cached); // Refresh LRU recency
      setState(() {
        _messagesAgent.clear();
        _messagesAgent.addAll(cached);
      });
      _scrollToBottom();
    } else {
      // 2. Instant L2 disk cache check (<2ms)
      final diskMsgs = await _loadConversationHistoryFromDiskCache(id);
      if (diskMsgs.isNotEmpty && mounted && _currentConversationId == id) {
        setState(() {
          _messagesAgent.clear();
          _messagesAgent.addAll(diskMsgs);
        });
        _scrollToBottom();
      } else {
        setState(() {
          _messagesAgent.clear();
          _messagesAgent.insert(0, {
            'type': 'system',
            'content': 'Loading messages for "$title"...',
            'timestamp': DateTime.now().toString(),
          });
        });
      }
    }

    // 3. Network fetch to ensure we have latest turns from server
    if (_channel != null && _isConnected) {
      final msg = jsonEncode({
        "type": "get_conversation_messages",
        "device_id": _activeDevice,
        "conversation_id": id,
        "session_token": _sessionToken,
      });
      _channel?.sink.add(msg);
    }

    _closeDrawerSafely();
  }

  void _deleteConversation(String id) {
    if (_channel != null && _isConnected) {
      final msg = jsonEncode({
        "type": "delete_conversation",
        "device_id": _activeDevice,
        "conversation_id": id,
        "session_token": _sessionToken,
      });
      _channel?.sink.add(msg);
    }
    _removeConversationFromCache(id);
    if (mounted) {
      setState(() {
        _conversations.removeWhere((c) => c['id'] == id);
        if (_currentConversationId == id) {
          _startNewConversation();
        }
      });
      _saveConversationsToDiskCache(_conversations);
    }
  }

  void _confirmDeleteConversation(String id, String title) {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppTokens.card(appThemeMode.value == ThemeMode.dark),
        title: Text('Delete Conversation?', style: GoogleFonts.spaceGrotesk(fontWeight: FontWeight.w700)),
        content: Text('Are you sure you want to delete "$title"? This cannot be undone.', style: GoogleFonts.inter(fontSize: 14)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              _deleteConversation(id);
            },
            child: const Text('Delete', style: TextStyle(color: Colors.redAccent)),
          ),
        ],
      ),
    );
  }

  Future<void> _clearAllConversations() async {
    if (_channel != null && _isConnected) {
      final msg = jsonEncode({
        "type": "clear_all_conversations",
        "device_id": _activeDevice,
        "session_token": _sessionToken,
      });
      _channel?.sink.add(msg);
    }

    _conversationMessagesCache.clear();
    if (mounted) {
      setState(() {
        _conversations.clear();
        _currentConversationId = '';
        _messagesAgent.clear();
        _messagesAgent.insert(0, {
          'type': 'system',
          'content': 'Fresh session started. All past conversation history has been cleared.',
          'timestamp': DateTime.now().toString(),
        });
      });
    }

    try {
      final dir = await getApplicationDocumentsDirectory();
      final indexFile = File('${dir.path}/conversations_index_cache.json');
      if (await indexFile.exists()) await indexFile.delete();

      final files = dir.listSync();
      for (final f in files) {
        if (f is File && f.path.contains('conv_history_')) {
          await f.delete();
        }
      }
    } catch (e) {
      debugPrint('Error clearing local cache files: $e');
    }
  }

  void _confirmClearAllConversations() {
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: AppTokens.card(appThemeMode.value == ThemeMode.dark),
        title: Text('Clear All Conversations?', style: GoogleFonts.spaceGrotesk(fontWeight: FontWeight.w700)),
        content: Text('Are you sure you want to delete all conversation history across both mobile and desktop? This cannot be undone.', style: GoogleFonts.inter(fontSize: 14)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              _closeDrawerSafely();
              _clearAllConversations();
            },
            child: const Text('Clear All', style: TextStyle(color: Colors.redAccent, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }
  void _loadSession() async {
    final savedToken = await _storage.read(key: 'session_token');
    final savedExpiresAt = await _storage.read(key: 'session_expires_at');
    if (!mounted) return;  // BUG-04 fix
    if (savedToken != null && savedToken.isNotEmpty) {
      setState(() {
        _sessionToken = savedToken;
        if (savedExpiresAt != null) {
          _sessionExpiresAt = int.tryParse(savedExpiresAt);
        }
      });
      debugPrint('Loaded session token from secure storage');
    }
  }

  void _setupWebSocket() {
    _initializeDeviceIdentity();
    _connectToBackend();
    _startHealthChecks();
    _startBgTaskChecks();
    // BUG-18 fix: _initializeSpeech() removed - called once from initState()

    Future.delayed(const Duration(seconds: 1), _getDevices);
  }

  Future<void> _initTts() async {
    // 100% Legal, Native, Free OS-Level Neural Voices
    await flutterTts.setLanguage("en-US");
    
    // Set awaitSpeakCompletion to strictly block speak() calls natively
    await flutterTts.awaitSpeakCompletion(true);
    await flutterTts.setSpeechRate(0.5);
    await flutterTts.setVolume(1.0);
    await flutterTts.setPitch(1.0);
    
    // Intentionally omitting setStartHandler and setCompletionHandler 
    // because they conflict with awaitSpeakCompletion(true) natively on Android!
  }

  Future<void> _initializeSpeech() async {
    if (_speechInitialized) return;
    
    _speechAvailable = await _speechToText.initialize();
    _speechInitialized = true;
    
    if (!_speechAvailable) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Speech recognition not available on this device')),
        );
      }
    } else {
      // AUTO-LISTEN TRIGGER ON LAUNCH
      Future.delayed(const Duration(milliseconds: 600), () {
        if (mounted) {
           setState(() => _isLiveSession = true);
           _startListening();
        }
      });
    }
  }

  Future<bool> _requestMicrophonePermission() async {
    final status = await Permission.microphone.request();
    
    if (status.isDenied) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Microphone permission denied')),
        );
      }
      return false;
    }
    
    if (status.isPermanentlyDenied) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Microphone permission permanently denied. Please enable in app settings.')),
        );
      }
      return false;
    }
    
    return true;
  }

  String _normalizeGenZSlang(String text) {
    String t = text;
    // Fix common speech-to-text misrecognitions for Gen Z slang
    t = t.replaceAll(RegExp(r'\b(riz|ris|wrist)\b', caseSensitive: false), 'rizz');
    t = t.replaceAll(RegExp(r'\b(skip itty|skipity|skibbidy)\b', caseSensitive: false), 'skibidi');
    t = t.replaceAll(RegExp(r'\b(gabum|guy at|gyat)\b', caseSensitive: false), 'gyatt');
    t = t.replaceAll(RegExp(r'\b(no cab|know cap)\b', caseSensitive: false), 'no cap');
    t = t.replaceAll(RegExp(r'\b(busting)\b', caseSensitive: false), 'bussin');
    t = t.replaceAll(RegExp(r'\b(sauce|soos)\b', caseSensitive: false), 'sus');
    t = t.replaceAll(RegExp(r'\b(loki)\b', caseSensitive: false), 'lowkey');
    t = t.replaceAll(RegExp(r'\b(sail is)\b', caseSensitive: false), 'say less');
    t = t.replaceAll(RegExp(r'\b(cap in)\b', caseSensitive: false), 'cappin');
    t = t.replaceAll(RegExp(r'\b(fin a)\b', caseSensitive: false), 'finna');
    t = t.replaceAll(RegExp(r'\b(dead as)\b', caseSensitive: false), 'deadass');
    return t;
  }

  String _parseSpokenPunctuation(String text) {
    if (text.isEmpty) return text;
    String t = text;

    // Brackets, Parentheses, Braces
    t = t.replaceAll(RegExp(r'\b(open|left)\s+(parenthesis|paren|round\s+bracket)\b', caseSensitive: false), '(');
    t = t.replaceAll(RegExp(r'\b(close|right|closed)\s+(parenthesis|paren|round\s+bracket)\b', caseSensitive: false), ')');
    t = t.replaceAll(RegExp(r'\b(open|left)\s+(bracket|square\s+bracket)\b', caseSensitive: false), '[');
    t = t.replaceAll(RegExp(r'\b(close|right|closed)\s+(bracket|square\s+bracket)\b', caseSensitive: false), ']');
    t = t.replaceAll(RegExp(r'\b(open|left)\s+(brace|curly\s+bracket|curly\s+brace)\b', caseSensitive: false), '{');
    t = t.replaceAll(RegExp(r'\b(close|right|closed)\s+(brace|curly\s+bracket|curly\s+brace)\b', caseSensitive: false), '}');

    // Quotes
    t = t.replaceAll(RegExp(r'\b(open|start)\s+(quote|quotation|double\s+quote)\b', caseSensitive: false), '"');
    t = t.replaceAll(RegExp(r'\b(close|end)\s+(quote|quotation|double\s+quote)\b', caseSensitive: false), '"');
    t = t.replaceAll(RegExp(r'\b(single\s+quote|apostrophe)\b', caseSensitive: false), '\'');

    // Standard Punctuation Marks
    t = t.replaceAll(RegExp(r'\b(comma)\b', caseSensitive: false), ',');
    t = t.replaceAll(RegExp(r'\b(full\s+stop|period|dot)\b', caseSensitive: false), '.');
    t = t.replaceAll(RegExp(r'\b(question\s+mark)\b', caseSensitive: false), '?');
    t = t.replaceAll(RegExp(r'\b(exclamation\s+mark|exclamation\s+point)\b', caseSensitive: false), '!');
    t = t.replaceAll(RegExp(r'\b(colon)\b', caseSensitive: false), ':');
    t = t.replaceAll(RegExp(r'\b(semicolon|semi-colon)\b', caseSensitive: false), ';');
    t = t.replaceAll(RegExp(r'\b(hyphen|dash)\b', caseSensitive: false), '-');
    t = t.replaceAll(RegExp(r'\b(underscore)\b', caseSensitive: false), '_');
    t = t.replaceAll(RegExp(r'\b(forward\s+slash|slash)\b', caseSensitive: false), '/');
    t = t.replaceAll(RegExp(r'\b(backslash|back\s+slash)\b', caseSensitive: false), '\\');
    t = t.replaceAll(RegExp(r'\b(newline|new\s+line|next\s+line)\b', caseSensitive: false), '\n');

    // Whitespace cleanup around punctuation
    t = t.replaceAll(RegExp(r'\s+([,.:;?!])'), r'$1');
    t = t.replaceAllMapped(RegExp(r'([,.:;?!])([A-Za-z0-9])'), (m) => '${m[1]} ${m[2]}');
    t = t.replaceAll(RegExp(r'\(\s+'), '(');
    t = t.replaceAll(RegExp(r'\s+\)'), ')');
    t = t.replaceAll(RegExp(r'\[\s+'), '[');
    t = t.replaceAll(RegExp(r'\s+\]'), ']');
    t = t.replaceAll(RegExp(r'\{\s+'), '{');
    t = t.replaceAll(RegExp(r'\s+\}'), '}');

    return t;
  }

  String _normalizeDictatedSpeech(String text) {
    String t = _normalizeGenZSlang(text);
    t = _parseSpokenPunctuation(t);
    return t;
  }

  Future<void> _startListening() async {
    final hasPermission = await _requestMicrophonePermission();
    if (!hasPermission) return;
    if (!mounted) return;  // BUG-13 fix
    
    _previousDictationText = _controller.text;
    if (_previousDictationText.isNotEmpty && !_previousDictationText.endsWith(' ')) {
        _previousDictationText += ' ';
    }
    if (mounted) setState(() {
      _isListening = true;
      _silenceWarningCount = 0;
      _currentAiSubtitle = ""; // Clear previous subtitle when starting new query
    });
    
    // SMART ML-LIKE HEURISTICS: Silence and Noise Detection (No AI required)
    _silenceTimer?.cancel();
    _silenceTimer = Timer.periodic(const Duration(seconds: 3), (timer) {
      if (!_isListening) {
        timer.cancel();
        return;
      }
      if (_isAiSpeaking) return; // Don't interrupt if AI is talking
      
      // If user hasn't spoken any valid words yet
      if (_controller.text.trim().isEmpty) {
        if (_currentSoundLevel < -20.0 || _currentSoundLevel == 0.0) {
           // Silence condition
           _silenceWarningCount++;
           if (_silenceWarningCount >= 2) {
             // BUG-17 fix: Timer.periodic callback is sync; _speak is async.
             // unawaited() prevents multiple concurrent TTS calls on each 3s tick.
             unawaited(_speak("Boss.......BOSS......Are you there ??"));
             _stopListening();
             timer.cancel();
           }
        } else if (_currentSoundLevel > 15.0) {
           // Loud Noise condition but no recognized words
           _silenceWarningCount++;
           if (_silenceWarningCount >= 2) {
             unawaited(_speak("Boss, I can't understand what you saying, your background is too loud... what is it ?? crowd or something else"));  // BUG-17 fix
             _stopListening();
             timer.cancel();
           }
        }
      }
    });
    
    try {
      await _speechToText.listen(
        onResult: (result) {
          final text = result.recognizedWords.trim().toUpperCase();
          
          // SMART HEURISTIC: 2 Person / Overlapping Voice Detection
          // Enhanced edge-case handling: STT chunking can send multiple words at once (batching bottleneck). 
          // We need to look for larger jumps over a slightly longer period, and require more consistent triggers.
          int currentWords = result.recognizedWords.split(' ').length;
          DateTime now = DateTime.now();
          
          // Fix: Increase word jump threshold to 8 words, timeframe to 800ms, and require 3 consistent triggers.
          if (currentWords > _lastWordCount + 8 && now.difference(_lastSpeechTime).inMilliseconds < 800) {
            _overlapTriggers++;
            if (_overlapTriggers >= 3) {
               _speak("boss, is any one there with you?");
               _overlapTriggers = 0; // reset
            }
          } else {
            // Decay the trigger if normal speech pacing (slower decay to catch intermittent overlapping)
            if (now.difference(_lastSpeechTime).inSeconds > 2) {
                if (_overlapTriggers > 0) _overlapTriggers--; 
            }
          }
          _lastWordCount = currentWords;
          _lastSpeechTime = now;

          // Use a highly specific trigger word to prevent accidental UX degradation
          bool isMuteCommand = text.contains("VMUTE") || text.contains("V MUTE");
          if (isMuteCommand) {
             _stopListening();
             flutterTts.stop();
             if (mounted) setState(() {
               _isLiveSession = false;
               _isAiSpeaking = false;
               _controller.text = "Muted by voice command";
             });
             _silenceTimer?.cancel();
             return;
          }
          
          if (result.finalResult) {
            String finalWords = _normalizeDictatedSpeech(result.recognizedWords);
            if (mounted) setState(() {
              _controller.text = _previousDictationText + finalWords;
              _isListening = false;
            });
            
            if (_isLiveSession && finalWords.isNotEmpty) {
               // SMART NLP ADDRESSEE DETECTION HEURISTIC
               // Enhanced to prevent false positives while still catching actual side-conversations
               final String lowerWords = finalWords.toLowerCase();
               int conversationalMarkers = 0;
               
               // Filler words get penalized but are not enough to trigger on their own
               if (lowerWords.contains(" um ") || lowerWords.startsWith("um ")) conversationalMarkers++;
               if (lowerWords.contains(" uh ") || lowerWords.startsWith("uh ")) conversationalMarkers++;
               if (lowerWords.contains(" you know ")) conversationalMarkers += 2;
               if (lowerWords.contains(" like ") && finalWords.split(' ').length > 6) conversationalMarkers++;
               if (lowerWords.contains(" yeah ") || lowerWords.startsWith("yeah ")) conversationalMarkers++;
               
               // Stronger markers of a side conversation
               if (lowerWords.contains(" so anyways ")) conversationalMarkers += 3;
               if (lowerWords.contains(" i was telling ")) conversationalMarkers += 3;
               if (lowerWords.contains(" he said ") || lowerWords.contains(" she said ")) conversationalMarkers += 2;
               
               // Look for clear command intents (whitelist) which cancel out conversational markers
               bool hasCommandIntent = lowerWords.contains("open") || lowerWords.contains("create") || 
                                       lowerWords.contains("execute") || lowerWords.contains("run") || 
                                       lowerWords.contains("search") || lowerWords.contains("tell me") ||
                                       lowerWords.contains("what is") || lowerWords.contains("boss") ||
                                       lowerWords.startsWith("yeah but") || lowerWords.startsWith("no ");
                                       
               if (hasCommandIntent) {
                  conversationalMarkers -= 3; // Heavily reduce the marker score if there's a clear command
               }
               
               // Rule-based decision threshold (Enhanced edge-case handling)
               // Only trigger if score is very high (>=4) or it's a very long sentence with no command intent and some markers
               if (conversationalMarkers >= 4 || (conversationalMarkers >= 2 && finalWords.split(' ').length > 25 && !hasCommandIntent)) {
                  _speak("Are you talking to me, or someone else?");
                  _silenceTimer?.cancel();
                  return; // Intercept and DO NOT send to the AI
               }
               
               // _sendMessage();
            }
          } else {
            // Partial result - update text field live
            if (mounted) setState(() {
              _controller.text = _previousDictationText + _normalizeDictatedSpeech(result.recognizedWords);
            });
          }
        },
        onSoundLevelChange: (level) {
          _currentSoundLevel = level;
        },
        listenFor: const Duration(seconds: 60),
        pauseFor: const Duration(seconds: 10),
        partialResults: true,
        localeId: 'en_US',
        cancelOnError: true,
      );
    } catch (e) {
      if (mounted) setState(() {
        _isListening = false;
        _isLiveSession = false;
      });
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Speech recognition error: $e')),
        );
      }
    }
  }

  Future<void> _stopListening() async {
    await _speechToText.stop();
    if (mounted) setState(() {
      _isListening = false;
      _isLiveSession = false;
      _currentSoundLevel = 0.0;
    });
  }

  void _cancelBackendTask() {
    if (_isConnected && _activeDevice.isNotEmpty && _activeDevice.startsWith('desktop-')) {
      final message = {
        'type': 'stop_command',
        'device_id': _activeDevice,
        'job_id': _activeJobId ?? '',
        'session_token': _sessionToken,
      };
      _channel?.sink.add(jsonEncode(message));
      
      if (_activeJobId != null && _activeJobId!.isNotEmpty) {
        _channel?.sink.add(jsonEncode({
          'type': 'cancel_job',
          'device_id': _activeDevice,
          'job_id': _activeJobId,
          'session_token': _sessionToken,
        }));
      }
      
      if (mounted) setState(() {
        _isThinking = false;
        _triggerDataArriving();
        _activeJobStatus = 'cancelled';
        for (var t in _bgTasks) {
          if (t['status'] == 'running') {
            t['status'] = 'cancelling';
          }
        }
        _addMessage({
          'type': 'system',
          'content': '⏹️ Force stop signal dispatched to local agent. Running processes and tasks terminated.',
          'timestamp': DateTime.now().toString(),
        });
      });
      _scrollToBottom();
    }
  }

  void _killSpecificBgTask(String taskId) {
    if (taskId.isEmpty) return;
    if (_isConnected && _activeDevice.isNotEmpty && _activeDevice.startsWith('desktop-')) {
      final message = {
        'type': 'kill_task',
        'device_id': _activeDevice,
        'task_id': taskId,
        'job_id': taskId,
        'session_token': _sessionToken,
      };
      _channel?.sink.add(jsonEncode(message));
      
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('⏹️ Sent kill signal for task $taskId'),
            duration: const Duration(seconds: 2),
          ),
        );
        setState(() {
          for (var t in _bgTasks) {
            if (t['id'] == taskId) {
              t['status'] = 'cancelling';
            }
          }
        });
      }
    }
  }

  Future<void> _notifyTaskCompletion(Map<String, dynamic> task) async {
    final status = task['status']?.toString() ?? '';
    final isSuccess = status == 'completed';
    final isFailed = status == 'failed';
    if (!isSuccess && !isFailed) return;

    final id = task['id']?.toString() ?? 'Task';
    final label = task['label']?.toString().isNotEmpty == true ? task['label'] : id;
    final duration = task['duration']?.toString() ?? '';
    final snapshot = task['snapshot']?.toString() ?? '';

    String rootCause = '';
    String recFix = '';
    if (snapshot.contains('ROOT_CAUSE:')) {
      final parts = snapshot.split('ROOT_CAUSE:');
      if (parts.length > 1) {
        final fixParts = parts[1].split('RECOMMENDED_FIX:');
        rootCause = fixParts[0].trim();
        if (fixParts.length > 1) {
          recFix = fixParts[1].trim();
        }
      }
    }

    final title = isSuccess
        ? '✓ Task Completed: $label'
        : '⚠️ Task Failed: $label';
    final body = isSuccess
        ? 'Command finished successfully${duration.isNotEmpty ? ' in $duration' : ''}.'
        : (rootCause.isNotEmpty
            ? 'Root cause: $rootCause'
            : 'Exit code: ${task['exit_code'] ?? 'non-zero'}. Tap to view diagnosis.');

    try {
      const AndroidNotificationDetails androidDetails = AndroidNotificationDetails(
        'bg_tasks_channel',
        'Autonomous Tasks & Watchdog',
        channelDescription: 'Real-time proactive notifications for background commands and builds.',
        importance: Importance.max,
        priority: Priority.high,
        playSound: true,
        enableVibration: true,
      );
      const NotificationDetails details = NotificationDetails(android: androidDetails);
      await _flutterLocalNotificationsPlugin.show(
        id.hashCode,
        title,
        body,
        details,
      );
    } catch (e) {
      debugPrint('Local notification error: $e');
    }

    // Proactive voice announcement if enabled
    if (_willTalk) {
      if (isSuccess) {
        _speakSummary("$label has finished successfully.");
      } else {
        final speechText = rootCause.isNotEmpty
            ? "Alert: $label failed. Root cause: $rootCause."
            : "Alert: $label failed with an error.";
        _speakSummary(speechText, isCritical: true);
      }
    }

    // In-app SnackBar if mounted
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Row(
            children: [
              Icon(
                isSuccess ? Icons.check_circle_outline : Icons.error_outline,
                color: isSuccess ? const Color(0xFF10B981) : const Color(0xFFEF4444),
                size: 20,
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  '$title - $body',
                  maxLines: 2,
                  overflow: TextOverflow.ellipsis,
                  style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                ),
              ),
            ],
          ),
          backgroundColor: isSuccess ? const Color(0xFF1E293B) : const Color(0xFF450A0A),
          duration: Duration(seconds: isFailed ? 6 : 4),
          action: isFailed
              ? SnackBarAction(
                  label: 'DIAGNOSE',
                  textColor: Colors.amberAccent,
                  onPressed: () => _showTaskDetailsDialog(task),
                )
              : null,
        ),
      );
    }
  }

  void _showTaskDetailsDialog(Map<String, dynamic> task) {
    final bool isDark = appThemeMode.value == ThemeMode.dark;
    final bool isRunning = task['status'] == 'running';
    final bool isFailed = task['status'] == 'failed';
    final String snapshot = task['snapshot']?.toString() ?? task['latest_log']?.toString() ?? '';
    
    // Extract root cause and recommended fix if present
    String rootCause = '';
    String recFix = '';
    if (snapshot.contains('ROOT_CAUSE:')) {
      final parts = snapshot.split('ROOT_CAUSE:');
      if (parts.length > 1) {
        final fixParts = parts[1].split('RECOMMENDED_FIX:');
        rootCause = fixParts[0].trim();
        if (fixParts.length > 1) {
          recFix = fixParts[1].trim();
        }
      }
    }

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: AppTokens.bg(isDark),
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(20),
          side: BorderSide(color: AppTokens.border(isDark)),
        ),
        title: Row(
          children: [
            Icon(
              isRunning
                  ? Icons.play_circle_fill_rounded
                  : (isFailed ? Icons.error_rounded : Icons.check_circle_rounded),
              color: isRunning
                  ? AppTokens.accentSecondary
                  : (isFailed ? const Color(0xFFEF4444) : const Color(0xFF10B981)),
              size: 22,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Task: ${task["label"] ?? task["id"] ?? "Details"}',
                style: GoogleFonts.spaceGrotesk(color: AppTokens.textPrimary(isDark), fontSize: 16, fontWeight: FontWeight.bold),
                overflow: TextOverflow.ellipsis,
              ),
            ),
          ],
        ),
        content: SizedBox(
          width: double.maxFinite,
          child: SingleChildScrollView(
            physics: const BouncingScrollPhysics(),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: (isFailed ? const Color(0xFFEF4444) : (isRunning ? AppTokens.accentSecondary : const Color(0xFF10B981))).withOpacity(0.15),
                        borderRadius: BorderRadius.circular(6),
                      ),
                      child: Text(
                        task["status"].toString().toUpperCase(),
                        style: GoogleFonts.inter(
                          color: isFailed ? const Color(0xFFEF4444) : (isRunning ? AppTokens.accentSecondary : const Color(0xFF10B981)),
                          fontSize: 11,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    if (task["duration"] != null)
                      Text('Duration: ${task["duration"]}', style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark), fontSize: 11)),
                  ],
                ),
                if (task["workdir"] != null && task["workdir"].toString().isNotEmpty) ...[
                  const SizedBox(height: 6),
                  Text('Directory: ${task["workdir"]}', style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark), fontSize: 11)),
                ],
                const SizedBox(height: 12),
                Text('Command:', style: GoogleFonts.inter(color: AppTokens.textPrimary(isDark), fontSize: 12, fontWeight: FontWeight.bold)),
                const SizedBox(height: 4),
                Container(
                  width: double.infinity,
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: AppTokens.cardAlt(isDark),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: AppTokens.border(isDark)),
                  ),
                  child: SelectableText(
                    task["command"] ?? '',
                    style: GoogleFonts.jetBrainsMono(color: AppTokens.accent, fontSize: 11),
                  ),
                ),
                if (rootCause.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      const Icon(Icons.psychology_rounded, size: 16, color: Colors.amberAccent),
                      const SizedBox(width: 6),
                      Text('Watchdog AI Diagnosis:', style: GoogleFonts.inter(color: Colors.amberAccent, fontSize: 12, fontWeight: FontWeight.bold)),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: Colors.amber.withOpacity(0.08),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: Colors.amber.withOpacity(0.3)),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Root Cause: $rootCause', style: GoogleFonts.inter(color: AppTokens.textPrimary(isDark), fontSize: 11, fontWeight: FontWeight.w600)),
                        if (recFix.isNotEmpty) ...[
                          const SizedBox(height: 6),
                          Text('Recommended Fix: $recFix', style: GoogleFonts.inter(color: AppTokens.accentSecondary, fontSize: 11)),
                        ],
                      ],
                    ),
                  ),
                ],
                if (snapshot.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  Text('Log Output & Diagnostics:', style: GoogleFonts.inter(color: AppTokens.textPrimary(isDark), fontSize: 12, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Container(
                    width: double.infinity,
                    constraints: const BoxConstraints(maxHeight: 220),
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: isDark ? const Color(0xFF090D16) : const Color(0xFFF1F5F9),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: AppTokens.border(isDark)),
                    ),
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      child: SelectableText(
                        snapshot,
                        style: GoogleFonts.jetBrainsMono(
                          color: isDark ? const Color(0xFFE2E8F0) : const Color(0xFF1E293B),
                          fontSize: 10.5,
                          height: 1.4,
                        ),
                      ),
                    ),
                  ),
                ],
              ],
            ),
          ),
        ),
        actions: [
          if (isFailed && (recFix.isNotEmpty || rootCause.isNotEmpty))
            ElevatedButton.icon(
              onPressed: () {
                Navigator.pop(context);
                final fixPrompt = "Fix background task error (${task['id']}): $rootCause. Suggestion: $recFix";
                _controller.text = fixPrompt;
                _sendMessage();
              },
              icon: const Icon(Icons.auto_fix_high_rounded, size: 14),
              label: const Text('Auto-Fix with AI', style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold)),
              style: ElevatedButton.styleFrom(
                backgroundColor: AppTokens.accentSecondary,
                foregroundColor: Colors.white,
                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
              ),
            ),
          if (isRunning)
            TextButton(
              onPressed: () {
                Navigator.pop(context);
                _killSpecificBgTask(task['id']?.toString() ?? '');
              },
              child: const Text('Kill Task', style: TextStyle(color: Color(0xFFEF4444), fontWeight: FontWeight.bold)),
            ),
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Close', style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark))),
          ),
        ],
      ),
    );
  }

  Widget _buildProactiveWatchdogCard(Map<String, dynamic> task, bool isDark) {
    final status = task['status']?.toString() ?? 'running';
    final isRunning = status == 'running';
    final isFailed = status == 'failed';
    final id = task['id']?.toString() ?? '';
    final label = task['label']?.toString().isNotEmpty == true ? task['label'] : id;
    final snapshot = task['snapshot']?.toString() ?? task['latest_log']?.toString() ?? '';
    final duration = task['duration']?.toString() ?? '';

    String rootCause = '';
    String recFix = '';
    if (snapshot.contains('ROOT_CAUSE:')) {
      final parts = snapshot.split('ROOT_CAUSE:');
      if (parts.length > 1) {
        final fixParts = parts[1].split('RECOMMENDED_FIX:');
        rootCause = fixParts[0].trim();
        if (fixParts.length > 1) {
          recFix = fixParts[1].trim();
        }
      }
    }

    final accentColor = isFailed
        ? const Color(0xFFEF4444)
        : (isRunning ? const Color(0xFF10B981) : const Color(0xFF6366F1));

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 4),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF141923).withOpacity(0.92) : Colors.white.withOpacity(0.92),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: accentColor.withOpacity(0.35),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: accentColor.withOpacity(0.12),
            blurRadius: 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 8,
                height: 8,
                decoration: BoxDecoration(
                  color: accentColor,
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(color: accentColor.withOpacity(0.6), blurRadius: 4, spreadRadius: 1),
                  ],
                ),
              ),
              const SizedBox(width: 6),
              Text(
                'WATCHDOG • ${status.toUpperCase()}',
                style: GoogleFonts.spaceGrotesk(
                  fontSize: 10,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.8,
                  color: accentColor,
                ),
              ),
              if (duration.isNotEmpty) ...[
                const SizedBox(width: 6),
                Text(
                  '($duration)',
                  style: GoogleFonts.inter(
                    fontSize: 10,
                    color: AppTokens.textSecondary(isDark),
                  ),
                ),
              ],
              const Spacer(),
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  setState(() {
                    _dismissedWatchdogTaskId = id;
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.all(2.0),
                  child: Icon(Icons.close_rounded, size: 14, color: AppTokens.textSecondary(isDark)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Row(
            children: [
              Expanded(
                child: Text(
                  isFailed && rootCause.isNotEmpty
                      ? 'Error: $rootCause'
                      : (task['command'] ?? label),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                  style: GoogleFonts.jetBrainsMono(
                    fontSize: 11,
                    fontWeight: FontWeight.w600,
                    color: isFailed ? const Color(0xFFFCA5A5) : AppTokens.textPrimary(isDark),
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              if (isFailed) ...[
                GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () {
                    final fixPrompt = "Fix background task error ($id): ${rootCause.isNotEmpty ? rootCause : snapshot}. Suggestion: $recFix";
                    _controller.text = fixPrompt;
                    _sendMessage();
                  },
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)],
                      ),
                      borderRadius: BorderRadius.circular(8),
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFF6366F1).withOpacity(0.3),
                          blurRadius: 4,
                          offset: const Offset(0, 1),
                        ),
                      ],
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.auto_fix_high_rounded, size: 12, color: Colors.white),
                        const SizedBox(width: 4),
                        Text(
                          'Auto-Fix',
                          style: GoogleFonts.inter(
                            fontSize: 10.5,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 6),
              ],
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () => _showTaskDetailsDialog(task),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: isDark ? Colors.white12 : Colors.black12),
                  ),
                  child: Text(
                    'Details & Logs',
                    style: GoogleFonts.inter(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w600,
                      color: AppTokens.textPrimary(isDark),
                    ),
                  ),
                ),
              ),
              if (isRunning) ...[
                const SizedBox(width: 6),
                GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () => _killSpecificBgTask(id),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xFFEF4444).withOpacity(0.12),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: const Color(0xFFEF4444).withOpacity(0.3)),
                    ),
                    child: Text(
                      'Kill',
                      style: GoogleFonts.inter(
                        fontSize: 10.5,
                        fontWeight: FontWeight.w700,
                        color: const Color(0xFFEF4444),
                      ),
                    ),
                  ),
                ),
              ],
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildAmbientClipboardCard(Map<String, dynamic> suggestion, bool isDark) {
    final lang = suggestion['language']?.toString() ?? 'Code';
    final summary = suggestion['summary']?.toString() ?? suggestion['error_type']?.toString() ?? 'Error detected';
    final recFix = suggestion['recommended_fix']?.toString() ?? '';
    final snippet = suggestion['snippet']?.toString() ?? '';

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 4),
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF161228).withOpacity(0.94) : Colors.white.withOpacity(0.94),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
          color: const Color(0xFF8B5CF6).withOpacity(0.4),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF8B5CF6).withOpacity(0.16),
            blurRadius: 10,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  color: const Color(0xFF8B5CF6).withOpacity(0.18),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(Icons.content_paste_search_rounded, size: 13, color: Color(0xFFA78BFA)),
              ),
              const SizedBox(width: 8),
              Text(
                'SMART CLIPBOARD • ${lang.toUpperCase()}',
                style: GoogleFonts.spaceGrotesk(
                  fontSize: 10,
                  fontWeight: FontWeight.w800,
                  letterSpacing: 0.8,
                  color: const Color(0xFFA78BFA),
                ),
              ),
              const Spacer(),
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  setState(() {
                    _activeClipboardSuggestion = null;
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.all(2.0),
                  child: Icon(Icons.close_rounded, size: 14, color: AppTokens.textSecondary(isDark)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 5),
          Text(
            summary,
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
            style: GoogleFonts.inter(
              fontSize: 11.5,
              fontWeight: FontWeight.w600,
              color: AppTokens.textPrimary(isDark),
              height: 1.3,
            ),
          ),
          const SizedBox(height: 6),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  final prompt = "Fix this copied $lang error: $summary.\nSuggestion: $recFix\nSnippet:\n```\n$snippet\n```";
                  _controller.text = prompt;
                  setState(() {
                    _activeClipboardSuggestion = null;
                  });
                  _sendMessage();
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4.5),
                  decoration: BoxDecoration(
                    gradient: const LinearGradient(
                      colors: [Color(0xFF6366F1), Color(0xFF9333EA)],
                    ),
                    borderRadius: BorderRadius.circular(8),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF6366F1).withOpacity(0.3),
                        blurRadius: 4,
                        offset: const Offset(0, 1),
                      ),
                    ],
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.auto_fix_high_rounded, size: 12, color: Colors.white),
                      const SizedBox(width: 4),
                      Text(
                        '1-Tap Auto-Fix',
                        style: GoogleFonts.inter(
                          fontSize: 10.5,
                          fontWeight: FontWeight.bold,
                          color: Colors.white,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
              const SizedBox(width: 6),
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  showDialog(
                    context: context,
                    builder: (context) => AlertDialog(
                      backgroundColor: AppTokens.bg(isDark),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(16),
                        side: BorderSide(color: AppTokens.border(isDark)),
                      ),
                      title: Row(
                        children: [
                          const Icon(Icons.content_paste_rounded, color: Color(0xFFA78BFA), size: 20),
                          const SizedBox(width: 8),
                          Text('$lang Error Analysis', style: GoogleFonts.spaceGrotesk(color: AppTokens.textPrimary(isDark), fontSize: 16, fontWeight: FontWeight.bold)),
                        ],
                      ),
                      content: SingleChildScrollView(
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text('Root Cause:', style: GoogleFonts.inter(color: AppTokens.textPrimary(isDark), fontSize: 12, fontWeight: FontWeight.bold)),
                            const SizedBox(height: 4),
                            Text(summary, style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark), fontSize: 12)),
                            if (recFix.isNotEmpty) ...[
                              const SizedBox(height: 10),
                              Text('Recommended Fix:', style: GoogleFonts.inter(color: Colors.amberAccent, fontSize: 12, fontWeight: FontWeight.bold)),
                              const SizedBox(height: 4),
                              Text(recFix, style: GoogleFonts.inter(color: AppTokens.textPrimary(isDark), fontSize: 12)),
                            ],
                            const SizedBox(height: 10),
                            Text('Copied Snippet:', style: GoogleFonts.inter(color: AppTokens.textPrimary(isDark), fontSize: 12, fontWeight: FontWeight.bold)),
                            const SizedBox(height: 4),
                            Container(
                              padding: const EdgeInsets.all(8),
                              decoration: BoxDecoration(
                                color: AppTokens.cardAlt(isDark),
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(color: AppTokens.border(isDark)),
                              ),
                              child: SelectableText(snippet, style: GoogleFonts.jetBrainsMono(fontSize: 10.5, color: AppTokens.accent)),
                            ),
                          ],
                        ),
                      ),
                      actions: [
                        TextButton(
                          onPressed: () => Navigator.pop(context),
                          child: Text('Close', style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark))),
                        ),
                      ],
                    ),
                  );
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4.5),
                  decoration: BoxDecoration(
                    color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: isDark ? Colors.white12 : Colors.black12),
                  ),
                  child: Text(
                    'View Snippet',
                    style: GoogleFonts.inter(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w600,
                      color: AppTokens.textPrimary(isDark),
                    ),
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildWorkdayBriefingCard(Map<String, dynamic> briefing, bool isDark) {
    final date = briefing['date']?.toString() ?? 'Today';
    final branch = briefing['git_branch']?.toString() ?? 'main';
    final uncommitted = briefing['uncommitted_count'] ?? 0;
    final freeRam = briefing['free_ram_gb'] != null ? (briefing['free_ram_gb'] as num).toStringAsFixed(1) : null;
    final freeDisk = briefing['free_disk_gb'] != null ? (briefing['free_disk_gb'] as num).toStringAsFixed(0) : null;
    final summary = briefing['summary_text']?.toString() ?? '';

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 4),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF1B1710).withOpacity(0.94) : Colors.white.withOpacity(0.94),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: const Color(0xFFF59E0B).withOpacity(0.4),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFFF59E0B).withOpacity(0.14),
            blurRadius: 12,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  color: const Color(0xFFF59E0B).withOpacity(0.2),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(Icons.wb_sunny_rounded, size: 14, color: Color(0xFFF59E0B)),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'WORKDAY BRIEFING • $date',
                  style: GoogleFonts.spaceGrotesk(
                    fontSize: 10,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.8,
                    color: const Color(0xFFF59E0B),
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  setState(() {
                    _activeWorkdayBriefing = null;
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.all(2.0),
                  child: Icon(Icons.close_rounded, size: 14, color: AppTokens.textSecondary(isDark)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          // Badges row: Git branch & System stats
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            physics: const BouncingScrollPhysics(),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                  decoration: BoxDecoration(
                    color: const Color(0xFF10B981).withOpacity(0.14),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      const Icon(Icons.call_split_rounded, size: 11, color: Color(0xFF10B981)),
                      const SizedBox(width: 4),
                      Text(
                        branch,
                        style: GoogleFonts.jetBrainsMono(
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                          color: const Color(0xFF10B981),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                  decoration: BoxDecoration(
                    color: (uncommitted > 0 ? const Color(0xFFF59E0B) : const Color(0xFF6366F1)).withOpacity(0.14),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    uncommitted > 0 ? '$uncommitted changed' : 'clean tree',
                    style: GoogleFonts.inter(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: uncommitted > 0 ? const Color(0xFFF59E0B) : const Color(0xFF6366F1),
                    ),
                  ),
                ),
                if (freeRam != null) ...[
                  const SizedBox(width: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: isDark ? Colors.white.withOpacity(0.06) : Colors.black.withOpacity(0.05),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      'RAM: $freeRam GB',
                      style: GoogleFonts.inter(fontSize: 10, color: AppTokens.textSecondary(isDark)),
                    ),
                  ),
                ],
                if (freeDisk != null) ...[
                  const SizedBox(width: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: isDark ? Colors.white.withOpacity(0.06) : Colors.black.withOpacity(0.05),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      'Disk: $freeDisk GB',
                      style: GoogleFonts.inter(fontSize: 10, color: AppTokens.textSecondary(isDark)),
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (summary.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              summary,
              style: GoogleFonts.inter(
                fontSize: 11.5,
                fontWeight: FontWeight.w500,
                color: AppTokens.textPrimary(isDark),
                height: 1.35,
              ),
            ),
          ],
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              if (summary.isNotEmpty) ...[
                GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () {
                    _speakSummary(summary);
                  },
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                    decoration: BoxDecoration(
                      color: const Color(0xFFF59E0B).withOpacity(0.18),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(color: const Color(0xFFF59E0B).withOpacity(0.3)),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.volume_up_rounded, size: 12, color: Color(0xFFF59E0B)),
                        const SizedBox(width: 4),
                        Text(
                          'Listen',
                          style: GoogleFonts.inter(
                            fontSize: 10.5,
                            fontWeight: FontWeight.bold,
                            color: const Color(0xFFF59E0B),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 6),
              ],
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  _controller.text = "git status";
                  _sendMessage();
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: isDark ? Colors.white12 : Colors.black12),
                  ),
                  child: Text(
                    'Git Status',
                    style: GoogleFonts.inter(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w600,
                      color: AppTokens.textPrimary(isDark),
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 6),
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  if (_isConnected && _activeDevice.isNotEmpty && _activeDevice.startsWith('desktop-')) {
                    final message = {
                      'type': 'command',
                      'device_id': _activeDevice,
                      'command': '__GET_WORKDAY_BRIEFING__',
                      'session_token': _sessionToken,
                    };
                    _channel?.sink.add(jsonEncode(message));
                  }
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: isDark ? Colors.white12 : Colors.black12),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.refresh_rounded, size: 11, color: AppTokens.textSecondary(isDark)),
                      const SizedBox(width: 3),
                      Text(
                        'Refresh',
                        style: GoogleFonts.inter(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w600,
                          color: AppTokens.textSecondary(isDark),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildNightlyGuardianCard(Map<String, dynamic> report, bool isDark) {
    final cacheMB = report['cleanable_cache_mb'] != null ? (report['cleanable_cache_mb'] as num).toDouble() : 0.0;
    final depStatus = report['dependency_status']?.toString() ?? 'Healthy';
    final staleBranches = report['stale_branches'] is List ? (report['stale_branches'] as List).length : 0;
    final recommendation = report['recommendation']?.toString() ?? '';

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 4),
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: isDark ? const Color(0xFF0F172A).withOpacity(0.94) : Colors.white.withOpacity(0.94),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: const Color(0xFF06B6D4).withOpacity(0.4),
          width: 1.2,
        ),
        boxShadow: [
          BoxShadow(
            color: const Color(0xFF06B6D4).withOpacity(0.14),
            blurRadius: 12,
            offset: const Offset(0, 3),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: const EdgeInsets.all(4),
                decoration: BoxDecoration(
                  color: const Color(0xFF06B6D4).withOpacity(0.2),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: const Icon(Icons.shield_outlined, size: 14, color: Color(0xFF06B6D4)),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  'NIGHTLY GUARDIAN • AUDIT REPORT',
                  style: GoogleFonts.spaceGrotesk(
                    fontSize: 10,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 0.8,
                    color: const Color(0xFF06B6D4),
                  ),
                  overflow: TextOverflow.ellipsis,
                ),
              ),
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  setState(() {
                    _activeNightlyAuditReport = null;
                  });
                },
                child: Padding(
                  padding: const EdgeInsets.all(2.0),
                  child: Icon(Icons.close_rounded, size: 14, color: AppTokens.textSecondary(isDark)),
                ),
              ),
            ],
          ),
          const SizedBox(height: 6),
          // Badges row: Cleanable cache, dependencies, stale branches
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            physics: const BouncingScrollPhysics(),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                  decoration: BoxDecoration(
                    color: (cacheMB > 50 ? const Color(0xFFEF4444) : const Color(0xFF10B981)).withOpacity(0.14),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.cleaning_services_rounded, size: 11, color: cacheMB > 50 ? const Color(0xFFEF4444) : const Color(0xFF10B981)),
                      const SizedBox(width: 4),
                      Text(
                        cacheMB > 0 ? '${cacheMB.toStringAsFixed(0)} MB Cache' : '0 MB Clean',
                        style: GoogleFonts.jetBrainsMono(
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                          color: cacheMB > 50 ? const Color(0xFFEF4444) : const Color(0xFF10B981),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 6),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                  decoration: BoxDecoration(
                    color: const Color(0xFF6366F1).withOpacity(0.14),
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    depStatus,
                    style: GoogleFonts.inter(
                      fontSize: 10,
                      fontWeight: FontWeight.w600,
                      color: const Color(0xFF6366F1),
                    ),
                  ),
                ),
                if (staleBranches > 0) ...[
                  const SizedBox(width: 6),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                    decoration: BoxDecoration(
                      color: Colors.amber.withOpacity(0.14),
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      '$staleBranches stale branches',
                      style: GoogleFonts.inter(fontSize: 10, color: Colors.amber),
                    ),
                  ),
                ],
              ],
            ),
          ),
          if (recommendation.isNotEmpty) ...[
            const SizedBox(height: 6),
            Text(
              recommendation,
              style: GoogleFonts.inter(
                fontSize: 11.5,
                fontWeight: FontWeight.w500,
                color: AppTokens.textPrimary(isDark),
                height: 1.35,
              ),
            ),
          ],
          const SizedBox(height: 8),
          Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              if (cacheMB > 1.0) ...[
                GestureDetector(
                  behavior: HitTestBehavior.opaque,
                  onTap: () {
                    if (_isConnected && _activeDevice.isNotEmpty && _activeDevice.startsWith('desktop-')) {
                      final message = {
                        'type': 'command',
                        'device_id': _activeDevice,
                        'command': '__EXECUTE_CACHE_CLEANUP__',
                        'session_token': _sessionToken,
                      };
                      _channel?.sink.add(jsonEncode(message));
                    }
                  },
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                    decoration: BoxDecoration(
                      gradient: const LinearGradient(
                        colors: [Color(0xFF06B6D4), Color(0xFF0284C7)],
                      ),
                      borderRadius: BorderRadius.circular(8),
                      boxShadow: [
                        BoxShadow(
                          color: const Color(0xFF06B6D4).withOpacity(0.3),
                          blurRadius: 4,
                          offset: const Offset(0, 1),
                        ),
                      ],
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.cleaning_services_rounded, size: 12, color: Colors.white),
                        const SizedBox(width: 4),
                        Text(
                          '1-Tap Clean Cache',
                          style: GoogleFonts.inter(
                            fontSize: 10.5,
                            fontWeight: FontWeight.bold,
                            color: Colors.white,
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 6),
              ],
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  if (_isConnected && _activeDevice.isNotEmpty && _activeDevice.startsWith('desktop-')) {
                    final message = {
                      'type': 'command',
                      'device_id': _activeDevice,
                      'command': '__RUN_NIGHTLY_AUDIT__',
                      'session_token': _sessionToken,
                    };
                    _channel?.sink.add(jsonEncode(message));
                  }
                },
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: isDark ? Colors.white12 : Colors.black12),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(Icons.shield_outlined, size: 11, color: AppTokens.textSecondary(isDark)),
                      const SizedBox(width: 3),
                      Text(
                        'Run Audit',
                        style: GoogleFonts.inter(
                          fontSize: 10.5,
                          fontWeight: FontWeight.w600,
                          color: AppTokens.textSecondary(isDark),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }

  Future<void> _initializeDeviceIdentity() async {
    _currentDeviceId = await DeviceIdentity.getDeviceId();
    _currentDeviceName = await DeviceIdentity.getDeviceName();
    _sessionId = const Uuid().v4();
    _savedDevices = await DeviceIdentity.getSavedDevices();
    if (mounted) setState(() {});  // BUG-10 fix
  }

  void _connectToBackend() {
    try {
      final url = backendUrl;
      debugPrint('Connecting WebSocket to: $url');
      _channel = WebSocketChannel.connect(
        Uri.parse(url),
      );
      
      _wsSubscription = _channel!.stream.listen((message) async {
        if (!mounted) return;  // BUG-02 fix: widget may be disposed during async reconnect loop
        
        if (!_isConnected) {
          setState(() {
            _isConnected = true;
            _reconnectAttempts = 0;
          });
          _fetchConversations();
          if (_fcmToken != null && _activeDevice.isNotEmpty) {
            _sendFCMToken(_fcmToken!);
          }
        }
        
        try {
          // Bug #13 Fix: Heavy JSON parsing moved to a background isolate via compute()
          // to prevent stuttering/frame drops on large payload like conversations_list
          final jsonResponse = await compute(parseJsonInBackground, message);
            
            if (jsonResponse is Map && jsonResponse['type'] == 'session') {
              final sessionToken = jsonResponse['session_token'];
              final sessionExpiresAt = jsonResponse['expires_at'];
              
              // Save to storage outside setState
              await _storage.write(key: 'session_token', value: sessionToken);
              if (sessionExpiresAt != null) {
                await _storage.write(key: 'session_expires_at', value: sessionExpiresAt.toString());
              }
              
              // Save the security phrase used to unlock this session
              if (_securityPhrase.isNotEmpty) {
                _cachedSecurityPhrase = _securityPhrase;
                await _storage.write(key: 'security_phrase', value: _securityPhrase);
              }
              
              if (!mounted) return;  // REMAIN-01 fix: two awaits before this
              setState(() {
                _sessionToken = sessionToken;
                _sessionExpiresAt = sessionExpiresAt;
              });
              if (_fcmToken != null) _sendFCMToken(_fcmToken!);
              
              if (mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Session unlocked successfully.')),
                );
              }
              return;
            } else if (jsonResponse is List) {
              _devices = {};
              _localAgentConnected = false;
              String? firstOnlineDesktop;
              for (var device in jsonResponse) {
                final deviceId = device['id'];
                if (deviceId != null && deviceId.startsWith('desktop-')) {
                  // Only show desktop devices, prevent MITM with fingerprint verification
                  final deviceFingerprint = device['fingerprint'];
                  final deviceOnline = device['online'] == true;
                  final deviceReachable = device['reachable'] == true;
                  if (deviceFingerprint != null) {
                    _devices[deviceId] = device;
                    if (deviceId == _activeDevice && deviceOnline && deviceReachable) {
                      _localAgentConnected = true;
                    }
                    if (deviceId == _activeDevice && device['locked'] == true) {
                      _isThinking = true;
                      _triggerDataDeparting();
                    }
                    // Track first online desktop for auto-selection
                    if (deviceOnline && firstOnlineDesktop == null) {
                      firstOnlineDesktop = deviceId;
                    }
                    // Auto-save desktop devices for quick reconnect
                    DeviceIdentity.saveDevice(deviceId, device);
                    DeviceIdentity.getSavedDevices().then((devices) {
                      if (!mounted) return;  // BUG-14 fix
                      _savedDevices = devices;
                      setState(() {});
                    });
                  }
                }
              }
              // Auto-select first online desktop if no device selected or current not in list
              if (_activeDevice.isEmpty || !_devices.containsKey(_activeDevice)) {
                if (firstOnlineDesktop != null) {
                  _activeDevice = firstOnlineDesktop;
                  debugPrint('Auto-selected device: $_activeDevice');
                  _fetchConversations();
                } else {
                  _activeDevice = '';
                  debugPrint('No online desktop devices available');
                }
              }
              // Clear stale saved devices that aren't in current backend list
              if (_devices.isEmpty) {
                _savedDevices = {};
                _activeDevice = '';
                if (mounted) setState(() {});  // REMAIN-03 fix
              }
              final onlineCount = _devices.values.where((d) => d['online'] == true).length;
              final reachableCount = _devices.values.where((d) => d['reachable'] == true).length;
              _addMessage({
                'type': 'system',
                'content': 'Desktop devices updated: ${_devices.length} devices ($onlineCount online, $reachableCount reachable)',
                'timestamp': DateTime.now().toString(),
              });
            } else if (jsonResponse is Map && jsonResponse['type'] == 'conversations_list') {
              List<dynamic> parsedData = [];
              var payload = jsonResponse['data'] ?? jsonResponse['conversations'];
              if (payload is String) {
                try {
                  final dec = jsonDecode(payload);
                  if (dec is List) payload = dec;
                  else if (dec is Map) payload = dec;
                } catch (_) {}
              }
              if (payload is Map && payload['encrypted'] != null) {
                 final String phrase = _cachedSecurityPhrase;
                 String dec = CryptoUtils.decrypt(payload['encrypted'], phrase);
                 try {
                   parsedData = await compute(parseJsonListInBackground, dec);
                 } catch(e) {}
              } else if (payload is List) {
                 parsedData = payload;
              }
              final mapped = parsedData.map((x) {
                try {
                  return Map<String, String>.from(
                    (x as Map).map((k, v) => MapEntry(k.toString(), v?.toString() ?? '')));
                } catch (_) { return <String, String>{}; }
              }).where((m) => m.isNotEmpty && m.containsKey('id')).toList();

              if (mounted) setState(() {
                final existingMap = { for (var c in _conversations) c['id']!: c };
                for (var m in mapped) {
                  existingMap[m['id']!] = m;
                }
                _conversations = existingMap.values.toList();
                _sortConversations();
              });
              if (_conversations.isNotEmpty) {
                _saveConversationsToDiskCache(_conversations);
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'conversation_messages') {
              final convId = jsonResponse['conversation_id']?.toString() ?? '';
              Map<String, dynamic> detailMap = {};
              var payload = jsonResponse['data'] ?? jsonResponse['payload'];
              if (payload is Map && payload['encrypted'] != null) {
                final String phrase = _cachedSecurityPhrase;
                String dec = CryptoUtils.decrypt(payload['encrypted'], phrase);
                try {
                  detailMap = jsonDecode(dec) as Map<String, dynamic>;
                } catch(e) {}
              } else if (payload is Map<String, dynamic>) {
                detailMap = payload;
              } else if (jsonResponse['messages'] != null) {
                detailMap = Map<String, dynamic>.from(jsonResponse);
              }

              final rawMsgs = detailMap['messages'] as List<dynamic>? ?? [];
              final loadedMessages = rawMsgs.map((m) {
                if (m is Map) {
                  return Map<String, dynamic>.from(m);
                }
                return <String, dynamic>{};
              }).where((m) => m.isNotEmpty).toList();

              if (convId.isNotEmpty) {
                _setConversationCache(convId, loadedMessages);
                _saveConversationHistoryToDiskCache(convId, loadedMessages);
              }

              if (mounted && convId == _currentConversationId) {
                setState(() {
                  _messagesAgent.clear();
                  _messagesAgent.addAll(loadedMessages);
                  if (_messagesAgent.isEmpty) {
                    _messagesAgent.insert(0, {
                      'type': 'system',
                      'content': 'Conversation is ready.',
                      'timestamp': DateTime.now().toString(),
                    });
                  }
                });
                _scrollToBottom();
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'conversation_deleted') {
              final deletedId = jsonResponse['conversation_id']?.toString() ?? '';
              if (deletedId.isNotEmpty) {
                _removeConversationFromCache(deletedId);
                if (mounted) {
                  setState(() {
                    _conversations.removeWhere((c) => c['id'] == deletedId);
                    if (_currentConversationId == deletedId) {
                      _startNewConversation();
                    }
                  });
                }
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'all_conversations_cleared') {
              _conversationMessagesCache.clear();
              if (mounted) {
                setState(() {
                  _conversations.clear();
                  _currentConversationId = '';
                  _messagesAgent.clear();
                  _messagesAgent.insert(0, {
                    'type': 'system',
                    'content': 'All past conversations have been wiped clean.',
                    'timestamp': DateTime.now().toString(),
                  });
                });
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'surveillance_alert') {
              final alert = jsonResponse['alert'];
              final reason = alert != null ? (alert['reason'] ?? 'Intruder detected!') : 'Intruder detected!';
              if (mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('⚠️ INTRUDER ALERT: $reason'),
                    backgroundColor: Colors.redAccent,
                    duration: const Duration(seconds: 4),
                  ),
                );
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'surveillance_status') {
              final data = jsonResponse['data'];
              if (data is Map<String, dynamic>) {
                SurveillanceSheet.onStatusUpdate?.call(data);
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'bg_task_update') {
              final task = jsonResponse['task'];
              if (task is Map && mounted) {
                final taskMap = Map<String, dynamic>.from(task);
                final taskId = taskMap['id']?.toString() ?? '';
                final status = taskMap['status']?.toString() ?? '';
                String prevStatus = '';
                setState(() {
                  final existingIdx = _bgTasks.indexWhere((t) => t['id'] == taskId);
                  if (existingIdx != -1) {
                    prevStatus = _bgTasks[existingIdx]['status']?.toString() ?? '';
                    _bgTasks[existingIdx] = taskMap;
                  } else {
                    _bgTasks.insert(0, taskMap);
                  }
                  if (status == 'running' || status == 'failed') {
                    if (_dismissedWatchdogTaskId == taskId && status != prevStatus) {
                      _dismissedWatchdogTaskId = null;
                    }
                  }
                });
                if (status != prevStatus && (status == 'completed' || status == 'failed')) {
                  _notifyTaskCompletion(taskMap);
                  if (!_isInForeground) {
                    _scheduleStandbyGracePeriod();
                  }
                }
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'clipboard_suggestion') {
              final suggestion = jsonResponse['data'];
              if (suggestion is Map && mounted) {
                setState(() {
                  _activeClipboardSuggestion = Map<String, dynamic>.from(suggestion);
                });
                _clipboardSuggestionTimer?.cancel();
                _clipboardSuggestionTimer = Timer(const Duration(seconds: 40), () {
                  if (mounted) {
                    setState(() {
                      _activeClipboardSuggestion = null;
                    });
                  }
                });
                if (_willTalk) {
                  final lang = suggestion['language'] ?? 'Code';
                  _speakSummary("Copied $lang error detected in clipboard.");
                }
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'workday_briefing') {
              final briefing = jsonResponse['data'];
              if (briefing is Map && mounted) {
                setState(() {
                  _activeWorkdayBriefing = Map<String, dynamic>.from(briefing);
                });
                if (_willTalk) {
                  final summary = briefing['summary_text']?.toString() ?? '';
                  if (summary.isNotEmpty) {
                    _speakSummary(summary);
                  }
                }
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'nightly_audit_report') {
              final report = jsonResponse['data'];
              if (report is Map && mounted) {
                setState(() {
                  _activeNightlyAuditReport = Map<String, dynamic>.from(report);
                });
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'cache_cleanup_result') {
              final result = jsonResponse['data'];
              if (result is Map && mounted) {
                final msg = result['message']?.toString() ?? 'Cache cleaned';
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('🧹 $msg'),
                    backgroundColor: const Color(0xFF10B981),
                    duration: const Duration(seconds: 4),
                  ),
                );
                setState(() {
                  if (_activeNightlyAuditReport != null) {
                    _activeNightlyAuditReport!['cleanable_cache_mb'] = 0;
                    _activeNightlyAuditReport!['recommendation'] = msg;
                  }
                });
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'security_alert') {
              final alert = jsonResponse['alert'];
              if (alert != null) {
                if (mounted) setState(() {
                  _securityAlerts.add(alert);
                });
                
                // Persist alerts (keep last 50)
                final alertsToSave = _securityAlerts.length > 50
                    ? _securityAlerts.sublist(_securityAlerts.length - 50)
                    : _securityAlerts;
                await _storage.write(
                  key: 'security_alerts',
                  value: jsonEncode(alertsToSave),
                );

                // Show snackbar for high severity alerts
                final severity = alert['severity']?.toString() ?? 'low';
                if (severity == 'high' && mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('Security alert: ${alert['type']}'),
                      backgroundColor: Colors.red,
                    ),
                  );
                }
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'security_alerts_list') {
              final alerts = jsonResponse['alerts'];
              if (alerts is List) {
                if (mounted) setState(() {
                  _securityAlerts = List<Map<String, dynamic>>.from(alerts);
                });
                
                // Persist alerts (keep last 50)
                final alertsToSave = _securityAlerts.length > 50
                    ? _securityAlerts.sublist(_securityAlerts.length - 50)
                    : _securityAlerts;
                await _storage.write(
                  key: 'security_alerts',
                  value: jsonEncode(alertsToSave),
                );
              }
            } else if (jsonResponse is Map && jsonResponse['type'] == 'models_list') {
              List<dynamic> parsedData = [];
              var payload = jsonResponse['data'] ?? jsonResponse['models'];
              if (payload is Map && payload['encrypted'] != null) {
                 final String phrase = _cachedSecurityPhrase;
                 String dec = CryptoUtils.decrypt(payload['encrypted'], phrase);
                 try {
                   parsedData = await compute(parseJsonListInBackground, dec);
                 } catch(e) {}
              } else if (payload is List) {
                 parsedData = payload;
              }
              if (mounted) setState(() {
                _isFetchingModels = false;
                _modelsList = parsedData.map((e) => e.toString()).toList();
                if (_modelsList.isNotEmpty && _selectedModel.isEmpty) {
                  _selectedModel = _modelsList[0];
                }
              });
            } else if (jsonResponse is Map && jsonResponse['type'] == 'pong') {
              // Silently ignore pong responses
              return;
            } else if (jsonResponse is Map && jsonResponse['type'] == 'token_usage') {
              if (mounted) setState(() {
                _lastTokenUsage = Map<String, dynamic>.from(jsonResponse);
              });
              await _storage.write(
                key: 'last_token_usage',
                value: jsonEncode(jsonResponse),
              );
            } else if (jsonResponse is Map && jsonResponse['type'] == 'status_update') {
              // Silently ignore ping/status_update from backend
              return;
            } else if (jsonResponse is Map && jsonResponse['type'] == 'job_status') {
              if (!mounted) return;
              setState(() {
                _activeJobId = jsonResponse['job_id'];
                _activeJobStatus = jsonResponse['job_status'];
                _activeJobSummary = jsonResponse['summary'] ?? '';
              });
              
              if (_activeJobStatus == 'done' || _activeJobStatus == 'failed' || _activeJobStatus == 'cancelled') {
                final currentId = _activeJobId;
                Future.delayed(const Duration(seconds: 3), () {
                  if (mounted && _activeJobId == currentId) {
                    setState(() {
                      _activeJobId = null;
                      _activeJobStatus = '';
                    });
                    if (!_isInForeground) {
                      _scheduleStandbyGracePeriod();
                    }
                  }
                });
              }
              return;
            } else if (jsonResponse is Map && jsonResponse['type'] == 'queued') {
              // Task queued! Keep loader spinning.
              return;
            } else if (jsonResponse is Map && jsonResponse.containsKey('summary')) {
              // Always clear the thinking/processing state when any response
              // arrives — including screenshots. Previously the screenshot branch
              // only called _triggerDataArriving() but forgot to set
              // _isThinking = false, leaving the skeleton loader visible.
              final resConvId = jsonResponse['new_conversation_id']?.toString() ?? _currentConversationId;
              if (mounted) setState(() {
                _thinkingSessions.remove(resConvId);
                if (resConvId == _currentConversationId || _thinkingSessions.isEmpty) {
                  _isThinking = false;
                  _triggerDataArriving();
                  if (!_isInForeground) {
                    _scheduleStandbyGracePeriod();
                  }
                }
              });
              
              String summaryToSpeak = jsonResponse['summary'];
              if (jsonResponse['delayed'] == true) {
                summaryToSpeak = "Hey boss, last task that you gave me before you got disconnected, is now completed. " + summaryToSpeak;
              }
              
              if (_willTalk) {
                unawaited(_speak(summaryToSpeak));  // REMAIN-02 fix: async speak, don't block stream
              }
              
              if (jsonResponse.containsKey('new_conversation_id') && jsonResponse['new_conversation_id'] != null) {
                final newId = jsonResponse['new_conversation_id'].toString();
                if (newId.isNotEmpty && newId != _currentConversationId) {
                  _currentConversationId = newId;
                  _fetchConversations();
                }
              }

              final rawOutput = (jsonResponse['output'] as String? ?? '').trim();
              final rawSummary = (jsonResponse['summary'] as String? ?? '').trim();
              String contentStr = rawOutput.isNotEmpty
                  ? rawOutput
                  : (rawSummary.isNotEmpty ? rawSummary : 'Task completed successfully.');
              if (rawOutput.startsWith('__IMAGE__:')) {
                contentStr = rawOutput;
              }
              _updateActiveConversationSnippet(contentStr);
              _interceptImageForAssistant(contentStr);
              _addMessage({
                'type': 'response',
                'content': contentStr,
                'summary': summaryToSpeak,
                'status': jsonResponse['status'],
                'mode': jsonResponse['mode'],
                'timestamp': DateTime.now().toString(),
              });
              
              if (jsonResponse.containsKey('artifacts') && jsonResponse['artifacts'] is List) {
                for (var artifact in (jsonResponse['artifacts'] as List)) {
                  ArtifactsManager.addArtifact(
                    title: artifact['title'] ?? 'Artifact',
                    content: artifact['content'],
                    source: 'ai',
                  );
                }
                if (mounted && (jsonResponse['artifacts'] as List).isNotEmpty) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text('${(jsonResponse['artifacts'] as List).length} artifacts saved!'),
                      action: SnackBarAction(
                        label: 'VIEW',
                        onPressed: () {
                          Navigator.push(context, MaterialPageRoute(builder: (context) => const ArtifactsPage()));
                        },
                      ),
                    ),
                  );
                }
              }
            } else if (message.contains('OK: All devices cleared')) {
              _addMessage({
                'type': 'system',
                'content': 'Backend data cleared successfully',
                'timestamp': DateTime.now().toString(),
              });
              _devices = {};
              _savedDevices = {};
              DeviceIdentity.clearAllSavedDevices();
              if (mounted) setState(() {});
              _getDevices(); // Refresh device list
            } else if (message.contains('ERROR:')) {
              setState(() { 
                _isThinking = false; _triggerDataArriving(); 
                _isFetchingModels = false;
              });
              if (message.contains('Unauthorized')) {
                _sessionToken = ''; // Clear expired or invalid token
                _sessionExpiresAt = null;
                _storage.delete(key: 'session_token');
                _storage.delete(key: 'session_expires_at');
              }

              _addMessage({
                'type': 'error',
                'content': message.replaceFirst('ERROR: ', ''),
                'timestamp': DateTime.now().toString(),
              });
            } else {
              if (mounted) setState(() { _isThinking = false; _triggerDataArriving(); });
              _addMessage({
                'type': 'response',
                'content': message,
                'timestamp': DateTime.now().toString(),
              });
            }
          } catch (e) {
            if (!mounted) return;  // REMAIN-04 fix
            setState(() { 
              _isThinking = false; _triggerDataArriving(); 
              _isFetchingModels = false;
            });
            _addMessage({
              'type': 'response',
              'content': message,
              'timestamp': DateTime.now().toString(),
            });
          }
          
          _checkBackendHealth();
          _scrollToBottom();
      }, onError: (error) {
        if (!mounted) return;  // BUG-11b fix
        setState(() {
          _isThinking = false; _triggerDataArriving();
          _isConnected = false; _activeJobId = null; _activeJobStatus = '';
          _addMessage({
            'type': 'error',
            'content': 'Connection error: $error',
            'timestamp': DateTime.now().toString(),
          });
        });
      }, onDone: () {
        if (mounted) setState(() {  // BUG-11 fix
          _isConnected = false; _activeJobId = null; _activeJobStatus = '';
          _addMessage({
            'type': 'system',
            'content': 'Connection closed. Attempting to reconnect...',
            'timestamp': DateTime.now().toString(),
          });
        });
        
        // Exponential backoff reconnection
        _reconnectAttempts++;
        final delay = Duration(seconds: 1 << _reconnectAttempts.clamp(0, 10));
        // Bug #14 Fix: Explicitly close the old sink before reconnecting.
        // Without this, every reconnect orphans the old WebSocketChannel and its
        // stream listener, leaking memory indefinitely when disconnected.
        _wsSubscription?.cancel();
        try { _channel?.sink.close(); } catch (_) {}
        Future.delayed(delay, () {
          if (mounted) _connectToBackend();
        });
      });
    } catch (e) {
      if (!mounted) return;  // REMAIN-05 fix
      setState(() {
        _isConnected = false; _activeJobId = null; _activeJobStatus = '';
        _addMessage({
          'type': 'error',
          'content': 'Failed to connect: $e',
          'timestamp': DateTime.now().toString(),
        });
      });
    }
  }

  void _startBgTaskChecks() {
    // Relaxed fallback poll (15s) since gRPC streams task updates in real-time
    _bgTaskTimer = Timer.periodic(const Duration(seconds: 15), (_) {
      _checkBgTasks();
    });
    _checkBgTasks();
  }

  Future<void> _checkBgTasks() async {
    try {
      if (_activeDevice.isEmpty) return; // need a device to route to
      String httpUrl = backendUrl;
      httpUrl = httpUrl.replaceAll('ws://', 'http://');
      httpUrl = httpUrl.replaceAll('wss://', 'https://');
      httpUrl = httpUrl.replaceAll('/ws', '/proxy/$_activeDevice/bg-tasks'); // the backend proxy route
      
      final response = await http.get(Uri.parse(httpUrl)).timeout(const Duration(seconds: 5));
      if (response.statusCode == 200) {
        final data = jsonDecode(response.body);
        if (mounted) {
          setState(() {
            _bgTasks = data['tasks'] ?? [];
          });
        }
      }
    } catch (e) {
      // silent fail
    }
  }

  void _startHealthChecks() {
    _healthCheckTimer = Timer.periodic(const Duration(seconds: 15), (_) {
      _checkBackendHealth();
    });
    
    _checkBackendHealth();
  }

  Future<void> _checkBackendHealth() async {
    try {
      String httpUrl = backendUrl;
      httpUrl = httpUrl.replaceAll('ws://', 'http://');
      httpUrl = httpUrl.replaceAll('wss://', 'https://');
      httpUrl = httpUrl.replaceAll('/ws', '/health');
      
      final response = await http.get(Uri.parse(httpUrl)).timeout(
        const Duration(seconds: 10), // Add timeout to prevent hanging
      );
      
      if (response.statusCode == 200) {
        jsonDecode(response.body);
        
        // Now fetch detailed status with device information
        String statusUrl = backendUrl;
        statusUrl = statusUrl.replaceAll('ws://', 'http://');
        statusUrl = statusUrl.replaceAll('wss://', 'https://');
        statusUrl = statusUrl.replaceAll('/ws', '/status');
        
        final statusResponse = await http.get(Uri.parse(statusUrl)).timeout(
          const Duration(seconds: 10),
        );
        
        if (statusResponse.statusCode == 200) {
          final statusData = jsonDecode(statusResponse.body);
          
          // Check if active device is specifically online and reachable
          bool activeDeviceOnline = false;
          if (statusData['online_devices'] is List) {
            final onlineDevices = statusData['online_devices'] as List;
            for (var device in onlineDevices) {
              if (device['id'] == _activeDevice && device['online'] == true) {
                final reachable = device['reachable'] == true;
                activeDeviceOnline = reachable;
                break;
              }
            }
          }
          
          if (mounted) setState(() {
            _isHealthy = true;
            _localAgentConnected = activeDeviceOnline;
            _backendStatus = 'Healthy (${statusData['uptime']})';
          });
        } else {
          if (!mounted) return;  // BUG-06 fix
          setState(() {
            _isHealthy = false;
            _localAgentConnected = false;
            _backendStatus = 'Status endpoint failed (${statusResponse.statusCode})';
          });
        }
      } else {
        if (!mounted) return;  // BUG-06 fix
        setState(() {
          _isHealthy = false;
          _localAgentConnected = false;
          _backendStatus = 'Unhealthy (${response.statusCode})';
        });
      }
    } catch (e) {
      if (!mounted) return;  // BUG-06 fix
      setState(() {
        _isHealthy = false;
        _localAgentConnected = false;
        _backendStatus = 'Health check failed: $e';
      });
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollController.hasClients) {
        _scrollController.animateTo(
          _scrollController.position.maxScrollExtent,
          duration: const Duration(milliseconds: 300),
          curve: Curves.easeOut,
        );
      }
    });
  }


  void _interceptImageForAssistant(String content) {
    if (content.startsWith('__IMAGE__:') && _isAssistant) {
      String base64Str = content.substring(10).replaceAll(RegExp(r'\s+'), '');
      if (mounted) setState(() {
        _temporaryAssistantImage = base64Str;
      });
      _assistantImageTimer?.cancel();
      _assistantImageTimer = Timer(const Duration(seconds: 30), () {
        if (mounted) {
          setState(() {
            _temporaryAssistantImage = null;
          });
        }
      });
    }
  }
  
  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _assistantImageTimer?.cancel();
    _silenceTimer?.cancel();  // BUG-03 fix: was missing, caused setState-after-dispose
    _wsSubscription?.cancel();  // REMAIN-06 fix: cancel WS stream subscription
    _fcmRefreshSubscription?.cancel();  // BUG-15 fix
    _fcmOpenedAppSubscription?.cancel();
    _fcmMessageSubscription?.cancel();  // FCM-02 fix
    _healthCheckTimer?.cancel();
    _bgTaskTimer?.cancel();
    _standbyGraceTimer?.cancel();
    _channel?.sink.close();
    _controller.dispose();
    _scrollController.dispose();
    if (_isListening) {
      _speechToText.stop();
    }
    // BUGFIX: Stop TTS on dispose to prevent audio playing after widget is destroyed
    // and to prevent setState-after-dispose in async TTS completion callbacks.
    flutterTts.stop();
    super.dispose();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _isInForeground = true;
      _standbyGraceTimer?.cancel();
      _standbyGraceTimer = null;

      if (!_isAssistant) {
        _checkIntent();
      }
      // Resume background timers upon app foreground
      _startBgTaskChecks();
      _startHealthChecks();

      // If disconnected during deep standby, reconnect smoothly
      if (!_isConnected) {
        _connectToBackend();
      }
    } else if (state == AppLifecycleState.paused ||
        state == AppLifecycleState.inactive ||
        state == AppLifecycleState.detached ||
        state.name == 'hidden') {
      _isInForeground = false;
      // Pause polling timers to eliminate idle battery & network drain
      _bgTaskTimer?.cancel();
      _healthCheckTimer?.cancel();

      if (_isTaskOrCommandActive()) {
        _ensureBackgroundExecutionEnabled(reason: "Executing task in background...");
      } else {
        _scheduleStandbyGracePeriod();
      }
    }
  }

  @override
  void didHaveMemoryPressure() {
    super.didHaveMemoryPressure();
    debugPrint('Voila: Low memory pressure warning from Android - trimming caches');
    PaintingBinding.instance.imageCache.clear();
    PaintingBinding.instance.imageCache.clearLiveImages();
    if (_currentConversationId.isNotEmpty && _conversationMessagesCache.containsKey(_currentConversationId)) {
      final activeList = _conversationMessagesCache[_currentConversationId]!;
      _conversationMessagesCache.clear();
      _conversationMessagesCache[_currentConversationId] = activeList;
    } else {
      _conversationMessagesCache.clear();
    }
  }

  void _openLiveModeSheet() {
    FocusScope.of(context).unfocus();
    String host = '127.0.0.1';
    try {
      final uri = Uri.parse(backendUrl);
      if (uri.host.isNotEmpty && uri.host != 'voila-voice.onrender.com') {
        host = uri.host;
      }
    } catch (_) {}

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) => VoilaLiveModeSheet(
        host: host,
        onClose: () => Navigator.pop(ctx),
      ),
    );
  }

  void _showModelSelector() {
    FocusScope.of(context).unfocus();
    bool isDark = appThemeMode.value == ThemeMode.dark;
    
    showModalBottomSheet(
      context: context,
      backgroundColor: AppTokens.bg(isDark),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(32))),
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return SafeArea(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Center(
                      child: Container(
                        width: 40,
                        height: 4,
                        margin: const EdgeInsets.only(bottom: 24),
                        decoration: BoxDecoration(color: AppTokens.border(isDark), borderRadius: BorderRadius.circular(10)),
                      ),
                    ),
                    Text('AVAILABLE MODELS', style: GoogleFonts.spaceGrotesk(fontSize: 14, fontWeight: FontWeight.w800, color: AppTokens.textSecondary(isDark), letterSpacing: 1.5)),
                    const SizedBox(height: 16),
                    if (_isFetchingModels)
                      Center(child: CircularProgressIndicator(color: AppTokens.accentSecondary))
                    else if (_modelsList.isEmpty)
                      Text('No models available.', style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark)))
                    else
                      Container(
                        decoration: BoxDecoration(
                          color: AppTokens.card(isDark),
                          borderRadius: BorderRadius.circular(24),
                          border: Border.all(color: AppTokens.border(isDark)),
                        ),
                        child: ListView.separated(
                          shrinkWrap: true,
                          itemCount: _modelsList.length,
                          separatorBuilder: (context, index) => Divider(color: AppTokens.border(isDark), height: 1),
                          itemBuilder: (context, index) {
                            final model = _modelsList[index];
                            final isSelected = _selectedModel == model;
                            return ListTile(
                              contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
                              title: Text(model, style: GoogleFonts.inter(color: isSelected ? AppTokens.textPrimary(isDark) : AppTokens.textSecondary(isDark), fontWeight: isSelected ? FontWeight.w600 : FontWeight.w400)),
                              trailing: isSelected ? Icon(Icons.check_circle_rounded, color: AppTokens.accentSecondary) : null,
                              onTap: () {
                                if (mounted) setState(() => _selectedModel = model);
                                Navigator.pop(context);
                              },
                            );
                          },
                        ),
                      ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }
  void _sendMessage() async {
    final text = _controller.text.trim();
    if (text.isEmpty) return;

    if (!_isConnected) {
      if (mounted) {
        setState(() {
          _addMessage({
            'type': 'error',
            'content': 'Not connected to backend. Please wait for reconnection.',
            'timestamp': DateTime.now().toString(),
          });
        });
        _scrollToBottom();
      }
      return;
    }
    
    // Auto-select desktop if activeDevice is not set yet but devices are available
    if (_activeDevice.isEmpty && _devices.isNotEmpty) {
      final fallback = _devices.keys.firstWhere((k) => k.startsWith('desktop-'), orElse: () => '');
      if (fallback.isNotEmpty) {
        _activeDevice = fallback;
      }
    }

    if (_activeDevice.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('⚠️ No desktop connected yet. Please ensure Voila is running on PC.')),
        );
      }
      return;
    }
    
    // Ensure session is unlocked (prompts security phrase inline if expired/locked)
    if (!await _ensureUnlocked()) {
      return; // Kept in controller so user does not lose input
    }

    if (_currentConversationId.isEmpty) {
      _currentConversationId = 'conv_' + const Uuid().v4().substring(0, 8);
    }
    _upsertActiveConversation(text);

    final deviceInfo = await DeviceIdentity.getDeviceInfo();
    if (!mounted) return;

    final message = {
      ...deviceInfo,
      'type': 'command',
      'device_id': _activeDevice,
      'client_device_id': _currentDeviceId,
      'client_device_name': _currentDeviceName,
      'session_id': _sessionId,
      'session_token': _sessionToken,
      'command': text,
      'mode': _currentMode,
      'conversation_id': _currentConversationId,
      'graphify_enabled': _graphifyEnabled,
      'idempotency_key': const Uuid().v4(),
      'client_timestamp': DateTime.now().millisecondsSinceEpoch,
    };
    
    debugPrint('Sending command to device: $_activeDevice');
    debugPrint('Message: $message');
    
    _channel?.sink.add(jsonEncode(message));
    _ensureBackgroundExecutionEnabled(reason: "Running $_currentMode command...");
    if (mounted) {
      setState(() {
        if (text != '__SCREENSHOT__') {
          _isThinking = true;
          _thinkingSessions.add(_currentConversationId);
          _triggerDataDeparting();
        }
        _addMessage({
          'type': 'user',
          'content': text == '__SCREENSHOT__' ? '📸 Taking screenshot...' : text,
          'timestamp': DateTime.now().toString(),
        });
      });
    }
    _controller.clear();
    _scrollToBottom();
  }

  void _switchDevice(String deviceId) async {
    final message = {
      'type': 'switch_device',
        'session_token': _sessionToken,
      'device_id': deviceId,
      'client_device_id': _currentDeviceId,
      'client_device_name': _currentDeviceName,
      'session_id': _sessionId,
    };
    
    _channel?.sink.add(jsonEncode(message));
    if (mounted) setState(() {
      _activeDevice = deviceId;
      _addMessage({
        'type': 'system',
        'content': 'Switched to device: $deviceId',
        'timestamp': DateTime.now().toString(),
      });
      _fetchConversations();
    });
  }

  void _getDevices() async {
    final message = {
      'type': 'get_devices',
      'client_device_id': _currentDeviceId,
      'client_device_name': _currentDeviceName,
      'session_id': _sessionId,
    };
    
    _channel?.sink.add(jsonEncode(message));
  }

  
  Future<String?> _promptSecurityPhrase() async {
    return await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Enter Security Phrase'),
        content: TextField(
          obscureText: true,
          decoration: const InputDecoration(
            hintText: 'Security phrase',
          ),
          onChanged: (value) {
            _securityPhrase = value;
          },
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, null),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, _securityPhrase),
            child: const Text('Continue'),
          ),
        ],
      ),
    );
  }

  bool _isSessionValid({Duration skew = const Duration(seconds: 30)}) {
    if (_sessionToken.isEmpty || _sessionExpiresAt == null) {
      return false;
    }
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final expiresAt = _sessionExpiresAt!;
    final nowWithSkew = now - skew.inSeconds;
    return nowWithSkew < expiresAt;
  }

  String _getSessionStatusText() {
    if (!_isSessionValid()) {
      return 'Session expired';
    }
    if (_sessionExpiresAt == null) {
      return 'Locked';
    }
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final remaining = _sessionExpiresAt! - now;
    if (remaining <= 0) {
      return 'Session expired';
    }
    if (remaining < 60) {
      return 'Unlocked • ${remaining}s left';
    }
    final minutes = remaining ~/ 60;
    if (minutes < 60) {
      return 'Unlocked • ${minutes}m left';
    }
    final hours = minutes ~/ 60;
    if (hours < 24) {
      return 'Unlocked • ${hours}h left';
    }
    final days = hours ~/ 24;
    return 'Unlocked • ${days}d left';
  }

  bool _isSessionExpiringSoon() {
    if (_sessionExpiresAt == null) return false;
    final now = DateTime.now().millisecondsSinceEpoch ~/ 1000;
    final remaining = _sessionExpiresAt! - now;
    return remaining > 0 && remaining < 60;
  }

  Future<bool> _ensureUnlocked() async {
    if (_isSessionValid()) {
      // Check if expiring soon and show warning
      if (_isSessionExpiringSoon() && mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Session expiring soon - consider unlocking again')),
        );
      }
      return true;
    }
    
    if (_activeDevice.isEmpty) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Please select an active device first.')),
        );
      }
      return false;
    }
    
    final phrase = await _promptSecurityPhrase();
    if (phrase == null || phrase.isEmpty) return false;
    
    // Send unlock request
    final message = {
      'type': 'unlock',
      'device_id': _activeDevice,
      'client_device_id': _currentDeviceId,
      'security_phrase': phrase,
    };
    _channel?.sink.add(jsonEncode(message));
    
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Verifying security phrase...')),
      );
    }
    
    // Wait for session token
    for (int i = 0; i < 50; i++) {
      await Future.delayed(const Duration(milliseconds: 100));
      if (_isSessionValid()) {
        return true;
      }
    }
    return false;
  }

  void _clearBackendData() async {
    if (!await _ensureUnlocked()) return;
    if (!mounted) return;  // BUG-19 fix
    final securityPhrase = _securityPhrase;

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Clear Backend Data'),
        content: const Text('This will delete all devices and data from the backend. This action cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('Clear'),
          ),
        ],
      ),
    );
    
    if (confirmed == true) {
      final message = {
        'type': 'clear_all_devices',
        'session_token': _sessionToken,
        'security_phrase': securityPhrase,
      };
      
      _channel?.sink.add(jsonEncode(message));
      if (mounted) setState(() {
        _addMessage({
          'type': 'system',
          'content': 'Requesting backend data clear...',
          'timestamp': DateTime.now().toString(),
        });
      });
    }
    
    _securityPhrase = '';
  }


  String _formatTime(dynamic ts) {
    if (ts == null) return '';
    try {
      final d = DateTime.parse(ts.toString()).toLocal();
      return '${d.hour.toString().padLeft(2, '0')}:${d.minute.toString().padLeft(2, '0')}';
    } catch(e) {
      return ts.toString();
    }
  }

  void _showSecurityAlerts() async { if (!await _ensureUnlocked()) return;

    FocusScope.of(context).unfocus();
    bool isDark = appThemeMode.value == ThemeMode.dark;
    
    showModalBottomSheet(
      context: context,
      backgroundColor: AppTokens.bg(isDark),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(32))),
      isScrollControlled: true,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return DraggableScrollableSheet(
              expand: false,
              initialChildSize: 0.6,
              minChildSize: 0.3,
              maxChildSize: 0.9,
              builder: (_, scrollController) => Container(
                padding: const EdgeInsets.all(24),
                child: Column(
                  children: [
                    Center(
                      child: Container(
                        width: 40,
                        height: 4,
                        margin: const EdgeInsets.only(bottom: 24),
                        decoration: BoxDecoration(color: AppTokens.border(isDark), borderRadius: BorderRadius.circular(10)),
                      ),
                    ),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Text('SECURITY ALERTS', style: GoogleFonts.spaceGrotesk(fontSize: 14, fontWeight: FontWeight.w800, color: AppTokens.textSecondary(isDark), letterSpacing: 1.5)),
                        Row(
                          children: [
                            if (_securityAlerts.isNotEmpty)
                              IconButton(
                                icon: Icon(Icons.delete_sweep_rounded, size: 20, color: AppTokens.textSecondary(isDark)),
                                onPressed: () {
                                  if (mounted) setState(() {
                                    _securityAlerts.clear();
                                  });
                                  setModalState(() {});
                                },
                              ),
                            IconButton(
                              icon: Icon(Icons.refresh_rounded, size: 20, color: AppTokens.textSecondary(isDark)),
                              onPressed: () {
                                final message = {
                                  'type': 'get_security_alerts',
                                  'device_id': _activeDevice,
                                  'session_token': _sessionToken,
                                };
                                _channel?.sink.add(jsonEncode(message));
                              },
                            ),
                          ],
                        ),
                      ],
                    ),
                    const SizedBox(height: 16),
                    // Sentinel SOC Emergency HUD Bento Card
                    Container(
                      width: double.infinity,
                      margin: const EdgeInsets.only(bottom: 16),
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: AppTokens.cardAlt(isDark),
                        borderRadius: BorderRadius.circular(20),
                        border: Border.all(
                          color: _isHostIsolated ? Colors.redAccent.withOpacity(0.5) : AppTokens.border(isDark),
                          width: _isHostIsolated ? 2 : 1,
                        ),
                      ),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Container(
                                padding: const EdgeInsets.all(8),
                                decoration: BoxDecoration(
                                  color: (_isHostIsolated ? Colors.redAccent : AppTokens.accent).withOpacity(0.15),
                                  shape: BoxShape.circle,
                                ),
                                child: Icon(
                                  _isHostIsolated ? Icons.security_rounded : Icons.shield_rounded,
                                  size: 20,
                                  color: _isHostIsolated ? Colors.redAccent : AppTokens.accent,
                                ),
                              ),
                              const SizedBox(width: 12),
                              Expanded(
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      'SENTINEL SOC HUD',
                                      style: GoogleFonts.spaceGrotesk(fontSize: 13, fontWeight: FontWeight.w800, color: AppTokens.textPrimary(isDark), letterSpacing: 1.2),
                                    ),
                                    Text(
                                      'Posture: ${_sentinelPostureScore.toInt()}/100 • ${_isHostIsolated ? "ISOLATED" : "PROTECTED"}',
                                      style: GoogleFonts.inter(fontSize: 12, color: _isHostIsolated ? Colors.redAccent : Colors.green, fontWeight: FontWeight.w600),
                                    ),
                                  ],
                                ),
                              ),
                              Container(
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                decoration: BoxDecoration(
                                  color: (_isHostIsolated ? Colors.redAccent : Colors.green).withOpacity(0.15),
                                  borderRadius: BorderRadius.circular(20),
                                ),
                                child: Text(
                                  _isHostIsolated ? 'ISOLATED' : 'ONLINE',
                                  style: GoogleFonts.spaceGrotesk(fontSize: 10, fontWeight: FontWeight.bold, color: _isHostIsolated ? Colors.redAccent : Colors.green),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 12),
                          // Defense Pills
                          Wrap(
                            spacing: 6,
                            runSpacing: 4,
                            children: [
                              _buildDefensePill('EDR Active', Icons.monitor_heart_rounded, isDark),
                              _buildDefensePill('Anti-MITM', Icons.router_rounded, isDark),
                              _buildDefensePill('AES-256 Vault', Icons.lock_clock_rounded, isDark),
                              _buildDefensePill('Secret Radar', Icons.key_rounded, isDark),
                            ],
                          ),
                          const SizedBox(height: 16),
                          // Emergency Response Buttons
                          Row(
                            children: [
                              Expanded(
                                child: ElevatedButton.icon(
                                  onPressed: _remoteLockWorkstation,
                                  icon: const Icon(Icons.lock_outline_rounded, size: 16),
                                  label: Text('Remote Lock', style: GoogleFonts.inter(fontWeight: FontWeight.bold, fontSize: 12)),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: Colors.indigoAccent.withOpacity(0.15),
                                    foregroundColor: Colors.indigoAccent,
                                    elevation: 0,
                                    padding: const EdgeInsets.symmetric(vertical: 12),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                  ),
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: ElevatedButton.icon(
                                  onPressed: () => _toggleNetworkIsolation(setModalState),
                                  icon: Icon(_isHostIsolated ? Icons.wifi_rounded : Icons.wifi_off_rounded, size: 16),
                                  label: Text(_isHostIsolated ? 'Restore LAN' : '1-Tap Isolate', style: GoogleFonts.inter(fontWeight: FontWeight.bold, fontSize: 12)),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: (_isHostIsolated ? Colors.green : Colors.redAccent).withOpacity(0.15),
                                    foregroundColor: _isHostIsolated ? Colors.green : Colors.redAccent,
                                    elevation: 0,
                                    padding: const EdgeInsets.symmetric(vertical: 12),
                                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                                  ),
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 8),
                          // Secondary Breaker Reset
                          SizedBox(
                            width: double.infinity,
                            child: OutlinedButton.icon(
                              onPressed: _resetCircuitBreaker,
                              icon: const Icon(Icons.power_settings_new_rounded, size: 14),
                              label: Text('Reset Circuit Breaker', style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w600)),
                              style: OutlinedButton.styleFrom(
                                foregroundColor: AppTokens.textSecondary(isDark),
                                side: BorderSide(color: AppTokens.border(isDark)),
                                padding: const EdgeInsets.symmetric(vertical: 8),
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                    Expanded(
                      child: _securityAlerts.isEmpty
                          ? Center(child: Text('No security alerts.', style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark))))
                          : ListView.separated(
                              controller: scrollController,
                              itemCount: _securityAlerts.length,
                              separatorBuilder: (context, index) => const SizedBox(height: 12),
                              itemBuilder: (context, index) {
                                final alert = _securityAlerts[index];
                                return Container(
                                  padding: const EdgeInsets.all(16),
                                  decoration: BoxDecoration(
                                    color: AppTokens.cardAlt(isDark),
                                    borderRadius: BorderRadius.circular(16),
                                    border: Border.all(color: AppTokens.border(isDark)),
                                  ),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Row(
                                        children: [
                                          Icon(_getSeverityIcon(alert['severity']?.toString() ?? 'medium'), size: 18, color: _getSeverityColor(alert['severity']?.toString() ?? 'medium')),
                                          const SizedBox(width: 8),
                                          Expanded(
                                            child: Text(
                                              alert['alert_type'] ?? 'Unknown Alert',
                                              style: GoogleFonts.inter(color: AppTokens.textPrimary(isDark), fontWeight: FontWeight.bold, fontSize: 14),
                                            ),
                                          ),
                                          Text(
                                            _formatTime(alert['timestamp']),
                                            style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark), fontSize: 12),
                                          ),
                                        ],
                                      ),
                                      const SizedBox(height: 8),
                                      Text(
                                        alert['details'] ?? 'No details provided.',
                                        style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark), fontSize: 13),
                                      ),
                                    ],
                                  ),
                                );
                              },
                            ),
                    ),
                  ],
                ),
              ),
            );
          },
        );
      },
    );
  }

  Color _getSeverityColor(String severity) {
    switch (severity.toLowerCase()) {
      case 'high': return Colors.red;
      case 'medium': return Colors.orange;
      case 'low': return Colors.yellow;
      default: return Colors.grey;
    }
  }

  IconData _getSeverityIcon(String severity) {
    switch (severity.toLowerCase()) {
      case 'high': return Icons.warning;
      case 'medium': return Icons.info;
      case 'low': return Icons.info_outline;
      default: return Icons.notifications_none;
    }
  }

  void _resetCircuitBreaker() async {
    if (!await _ensureUnlocked()) return;
    if (!mounted) return;  // BUG-20 fix
    
    final phrase = await _promptSecurityPhrase();
    if (phrase == null || phrase.isEmpty) return;
    
    final message = {
      'type': 'circuit_reset',
      'device_id': _activeDevice,
      'session_token': _sessionToken,
      'security_phrase': phrase,
    };
    
    _channel?.sink.add(jsonEncode(message));
    
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Resetting circuit breaker...')),
      );
    }
  }

  void _remoteLockWorkstation() {
    if (_activeDevice.isEmpty || !_isConnected) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No active connected workstation to lock.')),
      );
      return;
    }
    final message = {
      'type': 'command',
      'device_id': _activeDevice,
      'command': '__SENTINEL_LOCK__',
      'session_token': _sessionToken,
    };
    _channel?.sink.add(jsonEncode(message));
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Workstation remote lock signal dispatched via Sentinel.'),
        backgroundColor: Colors.blueAccent,
      ),
    );
  }

  void _toggleNetworkIsolation(StateSetter setModalState) {
    if (_activeDevice.isEmpty || !_isConnected) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('No active connected workstation to isolate.')),
      );
      return;
    }
    final bool newIsolatedState = !_isHostIsolated;
    final message = {
      'type': 'command',
      'device_id': _activeDevice,
      'command': newIsolatedState ? '__SENTINEL_ISOLATE__' : '__SENTINEL_LIFT_ISOLATION__',
      'session_token': _sessionToken,
    };
    _channel?.sink.add(jsonEncode(message));
    setState(() {
      _isHostIsolated = newIsolatedState;
    });
    setModalState(() {});

    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(newIsolatedState
            ? 'Emergency host network isolation ACTIVATED.'
            : 'Host network isolation LIFTED.'),
        backgroundColor: newIsolatedState ? Colors.redAccent : Colors.green,
      ),
    );
  }

  Widget _buildDefensePill(String label, IconData icon, bool isDark) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: AppTokens.bg(isDark).withOpacity(0.6),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppTokens.border(isDark).withOpacity(0.6)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 11, color: AppTokens.accent),
          const SizedBox(width: 4),
          Text(
            label,
            style: GoogleFonts.inter(fontSize: 10, color: AppTokens.textSecondary(isDark), fontWeight: FontWeight.w600),
          ),
        ],
      ),
    );
  }

  void _clearLocalData() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Clear Local Data'),
        content: const Text('This will clear all locally cached device data. You will need to reconnect to devices.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: Colors.red),
            child: const Text('Clear'),
          ),
        ],
      ),
    );
    
    if (confirmed == true) {
      await DeviceIdentity.clearAllSavedDevices();
      if (!mounted) return;
      setState(() {
        _savedDevices = {};
        _devices = {};
        _addMessage({
          'type': 'system',
          'content': 'Local data cleared',
          'timestamp': DateTime.now().toString(),
        });
      });
    }
  }

  void _showSavedDevices() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Saved Devices'),
        content: SizedBox(
          width: double.maxFinite,
          child: ListView.builder(
            shrinkWrap: true,
            itemCount: _savedDevices.length,
            itemBuilder: (context, index) {
              final deviceId = _savedDevices.keys.elementAt(index);
              final device = _savedDevices[deviceId] as Map<String, dynamic>;
              return ListTile(
                leading: const Icon(Icons.computer),
                title: Text(device['device_name'] ?? deviceId),
                subtitle: Text(deviceId),
                trailing: IconButton(
                  icon: const Icon(Icons.delete),
                  onPressed: () {
                    DeviceIdentity.removeSavedDevice(deviceId);
                    if (mounted) setState(() {
                      _savedDevices.remove(deviceId);
                    });
                    Navigator.pop(context);
                  },
                ),
                onTap: () {
                  _switchDevice(deviceId);
                  Navigator.pop(context);
                },
              );
            },
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Close'),
          ),
        ],
      ),
    );
  }

  Widget _buildDrawer() {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    final categorized = _categorizeConversations();
    final totalCount = _conversations.length;

    // Active conversation object
    final activeConv = _conversations.firstWhere(
      (c) => c['id'] == _currentConversationId,
      orElse: () => <String, String>{},
    );

    return Drawer(
      backgroundColor: AppTokens.bg(isDark),
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            // 1. Fixed Header (VOILA VOICE + Sync button)
            Container(
              padding: const EdgeInsets.only(top: 16, bottom: 16, left: 20, right: 14),
              decoration: BoxDecoration(
                color: AppTokens.card(isDark),
                border: Border(bottom: BorderSide(color: AppTokens.border(isDark))),
              ),
              child: Row(
                children: [
                  const Icon(Icons.graphic_eq_rounded, color: AppTokens.accent, size: 26),
                  const SizedBox(width: 10),
                  Text(
                    'VOILA VOICE',
                    style: GoogleFonts.spaceGrotesk(
                      color: AppTokens.textPrimary(isDark),
                      fontSize: 19,
                      fontWeight: FontWeight.w800,
                      letterSpacing: -0.8,
                    ),
                  ),
                  const Spacer(),
                  IconButton(
                    icon: Icon(Icons.refresh, color: AppTokens.textSecondary(isDark), size: 20),
                    onPressed: _fetchConversations,
                    tooltip: 'Sync Conversations',
                  ),
                ],
              ),
            ),

            // 2. Fixed Prominent + New Conversation button
            Container(
              margin: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                gradient: const LinearGradient(
                  colors: [Color(0xFFFF4500), Color(0xFFFF6A00)],
                  begin: Alignment.topLeft,
                  end: Alignment.bottomRight,
                ),
                borderRadius: BorderRadius.circular(14),
                boxShadow: [
                  BoxShadow(
                    color: const Color(0xFFFF4500).withOpacity(0.3),
                    blurRadius: 8,
                    offset: const Offset(0, 3),
                  ),
                ],
              ),
              child: ListTile(
                dense: true,
                leading: const Icon(Icons.add_rounded, color: Colors.white, size: 22),
                title: Text(
                  'New Conversation',
                  style: GoogleFonts.spaceGrotesk(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                    fontSize: 14,
                    letterSpacing: 0.3,
                  ),
                ),
                onTap: () {
                  _startNewConversation();
                },
              ),
            ),

            // 3. Header Summary: CONVERSATIONS with Live Badge
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 4),
              child: Row(
                children: [
                  Text(
                    'CONVERSATIONS',
                    style: GoogleFonts.spaceGrotesk(
                      color: AppTokens.textSecondary(isDark),
                      fontSize: 11,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 1.2,
                    ),
                  ),
                  const Spacer(),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: AppTokens.accentSecondary.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: Text(
                      '$totalCount',
                      style: GoogleFonts.inter(
                        color: AppTokens.accentSecondary,
                        fontSize: 10,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ),
                ],
              ),
            ),

            // 4. Dedicated Scrollable Categorized Conversation List
            Expanded(
              child: totalCount == 0 && _currentConversationId.isEmpty
                ? Center(
                    child: SingleChildScrollView(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      child: Container(
                        padding: const EdgeInsets.all(16),
                        decoration: BoxDecoration(
                          color: AppTokens.card(isDark).withOpacity(0.5),
                          borderRadius: BorderRadius.circular(16),
                          border: Border.all(color: AppTokens.border(isDark).withOpacity(0.5)),
                        ),
                        child: Column(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Icon(Icons.chat_bubble_outline_rounded, size: 28, color: AppTokens.textSecondary(isDark).withOpacity(0.4)),
                            const SizedBox(height: 8),
                            Text(
                              'No conversations yet',
                              style: GoogleFonts.inter(
                                color: AppTokens.textPrimary(isDark),
                                fontWeight: FontWeight.w600,
                                fontSize: 13,
                              ),
                            ),
                            const SizedBox(height: 4),
                            Text(
                              'Tap "+ New Conversation" or speak to start chatting with Voila.',
                              textAlign: TextAlign.center,
                              style: GoogleFonts.inter(
                                color: AppTokens.textSecondary(isDark),
                                fontSize: 11,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  )
                : RawScrollbar(
                    thumbVisibility: true,
                    thickness: 4,
                    radius: const Radius.circular(8),
                    thumbColor: AppTokens.accentSecondary.withOpacity(0.5),
                    child: ListView(
                      padding: const EdgeInsets.symmetric(vertical: 4, horizontal: 10),
                      physics: const AlwaysScrollableScrollPhysics(parent: BouncingScrollPhysics()),
                      children: [
                        // Active Session Card (if any active)
                        if (_currentConversationId.isNotEmpty) ...[
                          _buildActiveConversationCard(activeConv, isDark),
                          const SizedBox(height: 8),
                        ],

                        // Categorized Groups
                        for (final category in ['Pinned', 'Today', 'Yesterday', 'Previous 7 Days', 'Older'])
                          if ((categorized[category] ?? []).isNotEmpty) ...[
                            _buildCategoryHeader(category, categorized[category]!.length, isDark),
                            for (final conv in categorized[category]!)
                              _buildConversationTile(conv, isDark),
                            const SizedBox(height: 6),
                          ],
                      ],
                    ),
                  ),
            ),

            // 5. Docked Bottom Auxiliary Section (Divider, Utilities & Session Status)
            Padding(
              padding: const EdgeInsets.symmetric(horizontal: 16),
              child: Divider(color: AppTokens.border(isDark), height: 1),
            ),
            ConstrainedBox(
              constraints: const BoxConstraints(maxHeight: 280),
              child: SingleChildScrollView(
                child: Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _buildDrawerItem(Icons.dashboard_customize_rounded, 'Artifacts', () async {
                      if (!await _ensureUnlocked()) return;
                      _closeDrawerSafely();
                      if (mounted) Navigator.push(context, MaterialPageRoute(builder: (context) => const ArtifactsPage()));
                    }),
                    _buildDrawerItem(Icons.shield_rounded, 'Security Alerts', () {
                      _closeDrawerSafely();
                      _showSecurityAlerts();
                    }),
                    _buildDrawerItem(Icons.camera_outdoor_rounded, 'Surveillance', () async {
                      if (!await _ensureUnlocked()) return;
                      _closeDrawerSafely();
                      if (mounted) showModalBottomSheet(
                        context: context,
                        isScrollControlled: true,
                        backgroundColor: Colors.transparent,
                        builder: (context) => SurveillanceSheet(
                          backendUrl: backendUrl,
                          deviceId: _activeDevice,
                        ),
                      );
                    }),
                    _buildDrawerItem(Icons.devices_rounded, 'Saved Devices', () {
                      _closeDrawerSafely();
                      _showSavedDevices();
                    }),
                    _buildDrawerItem(Icons.tune_rounded, 'Settings', () {
                      _closeDrawerSafely();
                      _showSettingsSheet(context);
                    }),
                    _buildDrawerItem(Icons.image_not_supported_rounded, 'Clear Screenshots', () {
                      if (mounted) setState(() {
                        _messages.removeWhere((m) => (m['content'] as String? ?? '').startsWith('__IMAGE__:'));
                      });
                      _closeDrawerSafely();
                    }),
                    _buildDrawerItem(Icons.delete_sweep_rounded, 'Clear All Chats', () {
                      _confirmClearAllConversations();
                    }),

                    // Session Status Card
                    Padding(
                      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
                      child: Container(
                        padding: const EdgeInsets.all(10),
                        decoration: BoxDecoration(
                          color: _isSessionValid() 
                            ? (_isSessionExpiringSoon() ? Colors.orange.withOpacity(0.1) : Colors.green.withOpacity(0.1))
                            : Colors.red.withOpacity(0.1),
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                            color: _isSessionValid() 
                              ? (_isSessionExpiringSoon() ? Colors.orange.withOpacity(0.5) : Colors.green.withOpacity(0.5))
                              : Colors.red.withOpacity(0.5),
                          ),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              _isSessionValid() ? Icons.lock_open_rounded : Icons.lock_rounded,
                              size: 16,
                              color: _isSessionValid() 
                                ? (_isSessionExpiringSoon() ? Colors.orange : Colors.green)
                                : Colors.red,
                            ),
                            const SizedBox(width: 10),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text('Session Status', style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark), fontSize: 11)),
                                  const SizedBox(height: 1),
                                  Text(
                                    _getSessionStatusText(),
                                    style: GoogleFonts.inter(
                                      color: _isSessionValid() 
                                        ? (_isSessionExpiringSoon() ? Colors.orange : Colors.green)
                                        : Colors.red,
                                      fontWeight: FontWeight.bold,
                                      fontSize: 13,
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildActiveConversationCard(Map<String, String> conv, bool isDark) {
    final title = (conv['title'] != null && conv['title']!.isNotEmpty)
        ? conv['title']!
        : (_messagesAgent.isNotEmpty && _messagesAgent.any((m) => m['type'] == 'user')
            ? _messagesAgent.firstWhere((m) => m['type'] == 'user')['content'].toString()
            : 'Active Conversation');
    final snippet = conv['last_snippet'] ?? '';

    return Container(
      decoration: BoxDecoration(
        color: AppTokens.accentSecondary.withOpacity(0.12),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(color: AppTokens.accentSecondary, width: 1.5),
        boxShadow: [
          BoxShadow(
            color: AppTokens.accentSecondary.withOpacity(0.15),
            blurRadius: 8,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: ListTile(
        dense: true,
        contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 2),
        leading: Stack(
          alignment: Alignment.center,
          children: [
            Container(
              width: 28,
              height: 28,
              decoration: BoxDecoration(
                color: AppTokens.accentSecondary.withOpacity(0.2),
                shape: BoxShape.circle,
              ),
              child: const Icon(Icons.bolt_rounded, size: 18, color: AppTokens.accentSecondary),
            ),
          ],
        ),
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1),
              decoration: BoxDecoration(
                color: const Color(0xFF10B981).withOpacity(0.2),
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: const Color(0xFF10B981), width: 0.8),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Container(
                    width: 5,
                    height: 5,
                    decoration: const BoxDecoration(
                      color: Color(0xFF10B981),
                      shape: BoxShape.circle,
                    ),
                  ),
                  const SizedBox(width: 4),
                  Text(
                    'ACTIVE NOW',
                    style: GoogleFonts.inter(
                      color: const Color(0xFF10B981),
                      fontSize: 9,
                      fontWeight: FontWeight.w800,
                      letterSpacing: 0.5,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        subtitle: Padding(
          padding: const EdgeInsets.only(top: 4),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                title,
                style: GoogleFonts.inter(
                  color: AppTokens.textPrimary(isDark),
                  fontWeight: FontWeight.w700,
                  fontSize: 13,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
              if (snippet.isNotEmpty)
                Padding(
                  padding: const EdgeInsets.only(top: 2),
                  child: Text(
                    snippet,
                    style: GoogleFonts.inter(
                      color: AppTokens.textSecondary(isDark),
                      fontSize: 11,
                    ),
                    maxLines: 1,
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
            ],
          ),
        ),
        onTap: () {
          _closeDrawerSafely();
        },
      ),
    );
  }

  Widget _buildCategoryHeader(String title, int count, bool isDark) {
    return Padding(
      padding: const EdgeInsets.only(left: 6, top: 10, bottom: 4, right: 6),
      child: Row(
        children: [
          Text(
            title.toUpperCase(),
            style: GoogleFonts.spaceGrotesk(
              color: AppTokens.textSecondary(isDark).withOpacity(0.8),
              fontSize: 10.5,
              fontWeight: FontWeight.w800,
              letterSpacing: 1.0,
            ),
          ),
          const SizedBox(width: 6),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
            decoration: BoxDecoration(
              color: AppTokens.border(isDark).withOpacity(0.5),
              borderRadius: BorderRadius.circular(8),
            ),
            child: Text(
              '$count',
              style: GoogleFonts.inter(
                color: AppTokens.textSecondary(isDark),
                fontSize: 9,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }

  void _togglePinConversation(String convId, bool isPinned) {
    if (convId.isEmpty) return;
    setState(() {
      final idx = _conversations.indexWhere((c) => c['id'] == convId);
      if (idx >= 0) {
        final item = Map<String, String>.from(_conversations[idx]);
        item['is_pinned'] = isPinned ? 'true' : 'false';
        _conversations[idx] = item;
        _sortConversations();
        _saveConversationsToDiskCache(_conversations);
      }
    });

    if (_channel != null) {
      _channel!.sink.add(jsonEncode({
        'action': 'pin_conversation',
        'conversation_id': convId,
        'is_pinned': isPinned,
      }));
    }
  }

  void _showForkConversationDialog(String parentId, String parentTitle) {
    String selectedModel = 'GROQ';
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (ctx) {
        final isDark = appThemeMode.value == ThemeMode.dark;
        return StatefulBuilder(
          builder: (context, setModalState) {
            return Container(
              padding: EdgeInsets.only(
                left: 20,
                right: 20,
                top: 20,
                bottom: MediaQuery.of(context).viewInsets.bottom + 24,
              ),
              decoration: BoxDecoration(
                color: AppTokens.card(isDark),
                borderRadius: const BorderRadius.vertical(top: Radius.circular(20)),
                border: Border.all(color: AppTokens.border(isDark)),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.fork_right_rounded, color: AppTokens.accentSecondary, size: 22),
                      const SizedBox(width: 8),
                      Text(
                        'Fork Session',
                        style: GoogleFonts.inter(
                          color: AppTokens.textPrimary(isDark),
                          fontSize: 16,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Text(
                    'Branch "$parentTitle" to another AI model provider so they can cross-analyze each other\'s work and task history.',
                    style: GoogleFonts.inter(
                      color: AppTokens.textSecondary(isDark),
                      fontSize: 12,
                    ),
                  ),
                  const SizedBox(height: 16),
                  Text(
                    'SELECT TARGET MODEL PROVIDER',
                    style: GoogleFonts.inter(
                      color: AppTokens.textSecondary(isDark),
                      fontSize: 10,
                      fontWeight: FontWeight.w700,
                      letterSpacing: 0.8,
                    ),
                  ),
                  const SizedBox(height: 8),
                  for (final provider in [
                    {'id': 'GROQ', 'name': 'Groq Cloud (Ultra Fast)', 'icon': Icons.bolt_rounded},
                    {'id': 'OLLAMA', 'name': 'Ollama Local (Offline / Private)', 'icon': Icons.memory_rounded},
                    {'id': 'LOCAL', 'name': 'Local Default Agent', 'icon': Icons.terminal_rounded},
                  ])
                    Container(
                      margin: const EdgeInsets.symmetric(vertical: 4),
                      decoration: BoxDecoration(
                        color: selectedModel == provider['id']
                            ? AppTokens.accentSecondary.withOpacity(0.12)
                            : Colors.transparent,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(
                          color: selectedModel == provider['id']
                              ? AppTokens.accentSecondary
                              : AppTokens.border(isDark),
                        ),
                      ),
                      child: ListTile(
                        dense: true,
                        leading: Icon(
                          provider['icon'] as IconData,
                          color: selectedModel == provider['id']
                              ? AppTokens.accentSecondary
                              : AppTokens.textSecondary(isDark),
                          size: 18,
                        ),
                        title: Text(
                          provider['name'] as String,
                          style: GoogleFonts.inter(
                            color: AppTokens.textPrimary(isDark),
                            fontSize: 12.5,
                            fontWeight: selectedModel == provider['id'] ? FontWeight.w600 : FontWeight.w400,
                          ),
                        ),
                        trailing: selectedModel == provider['id']
                            ? const Icon(Icons.check_circle_rounded, color: AppTokens.accentSecondary, size: 18)
                            : null,
                        onTap: () {
                          setModalState(() {
                            selectedModel = provider['id'] as String;
                          });
                        },
                      ),
                    ),
                  const SizedBox(height: 16),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: () => Navigator.pop(ctx),
                          style: OutlinedButton.styleFrom(
                            side: BorderSide(color: AppTokens.border(isDark)),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                          ),
                          child: Text(
                            'Cancel',
                            style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark)),
                          ),
                        ),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: ElevatedButton(
                          onPressed: () {
                            Navigator.pop(ctx);
                            final newForkId = 'conv_fork_' + const Uuid().v4().substring(0, 8);
                            if (_channel != null) {
                              _channel!.sink.add(jsonEncode({
                                'action': 'fork_conversation',
                                'conversation_id': parentId,
                                'new_id': newForkId,
                                'model': selectedModel,
                              }));
                            }
                            _resumeConversation(newForkId, '[Fork] $parentTitle');
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text('Forked session to $selectedModel'),
                                duration: const Duration(seconds: 2),
                              ),
                            );
                          },
                          style: ElevatedButton.styleFrom(
                            backgroundColor: AppTokens.accentSecondary,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                          ),
                          child: Text(
                            'Fork Chat',
                            style: GoogleFonts.inter(color: Colors.black, fontWeight: FontWeight.w700),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            );
          },
        );
      },
    );
  }

  Widget _buildConversationTile(Map<String, String> conv, bool isDark) {
    final isSelected = _currentConversationId == conv['id'];
    final convId = conv['id'] ?? '';
    final title = conv['title'] ?? 'Conversation';
    final snippet = conv['last_snippet'] ?? '';
    final isPinned = conv['is_pinned'] == 'true';
    final isTaskRunning = _thinkingSessions.contains(convId) ||
        _bgTasks.any((t) => (t['conversation_id']?.toString() == convId || t['conv_id']?.toString() == convId) && t['status'] == 'running');

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 2),
      decoration: BoxDecoration(
        color: isSelected ? AppTokens.accentSecondary.withOpacity(0.14) : Colors.transparent,
        borderRadius: BorderRadius.circular(10),
        border: isSelected ? Border.all(color: AppTokens.accentSecondary.withOpacity(0.5), width: 1.2) : null,
      ),
      child: ListTile(
        dense: true,
        contentPadding: const EdgeInsets.only(left: 8, right: 4),
        leading: Stack(
          clipBehavior: Clip.none,
          children: [
            Icon(
              isSelected ? Icons.auto_awesome : Icons.chat_bubble_outline_rounded,
              size: 16,
              color: isTaskRunning
                  ? const Color(0xFF10B981)
                  : (isSelected ? AppTokens.accentSecondary : AppTokens.textSecondary(isDark).withOpacity(0.7)),
            ),
            if (isTaskRunning)
              Positioned(
                right: -4,
                top: -4,
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 2.5, vertical: 0.5),
                  decoration: BoxDecoration(
                    color: const Color(0xFF10B981),
                    borderRadius: BorderRadius.circular(3),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF10B981).withOpacity(0.6),
                        blurRadius: 4,
                        spreadRadius: 1,
                      ),
                    ],
                  ),
                  child: const Text(
                    'A',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 7.5,
                      fontWeight: FontWeight.w900,
                      height: 1.0,
                    ),
                  ),
                ),
              ),
          ],
        ),
        title: Row(
          children: [
            if (isPinned) ...[
              const Icon(Icons.push_pin_rounded, size: 12, color: Color(0xFFF59E0B)),
              const SizedBox(width: 4),
            ],
            Expanded(
              child: Text(
                title,
                style: GoogleFonts.inter(
                  color: isSelected ? AppTokens.textPrimary(isDark) : AppTokens.textSecondary(isDark),
                  fontWeight: isSelected ? FontWeight.w700 : FontWeight.w500,
                  fontSize: 12.5,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              ),
            ),
            if (isTaskRunning) ...[
              const SizedBox(width: 4),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1.5),
                decoration: BoxDecoration(
                  color: const Color(0xFF10B981).withOpacity(0.18),
                  borderRadius: BorderRadius.circular(4),
                  border: Border.all(color: const Color(0xFF10B981), width: 1),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 5,
                      height: 5,
                      decoration: const BoxDecoration(
                        color: Color(0xFF10B981),
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 3),
                    const Text(
                      'A',
                      style: TextStyle(
                        color: Color(0xFF10B981),
                        fontSize: 9,
                        fontWeight: FontWeight.w900,
                        height: 1.0,
                      ),
                    ),
                  ],
                ),
              ),
            ],
          ],
        ),
        subtitle: snippet.isNotEmpty
            ? Text(
                snippet,
                style: GoogleFonts.inter(
                  color: AppTokens.textSecondary(isDark).withOpacity(0.6),
                  fontSize: 10.5,
                ),
                maxLines: 1,
                overflow: TextOverflow.ellipsis,
              )
            : null,
        trailing: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            IconButton(
              icon: Icon(
                isPinned ? Icons.push_pin_rounded : Icons.push_pin_outlined,
                size: 14,
                color: isPinned ? const Color(0xFFF59E0B) : AppTokens.textSecondary(isDark).withOpacity(0.4),
              ),
              tooltip: isPinned ? 'Unpin Chat' : 'Pin Chat',
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
              onPressed: () => _togglePinConversation(convId, !isPinned),
            ),
            IconButton(
              icon: Icon(
                Icons.fork_right_rounded,
                size: 14,
                color: AppTokens.textSecondary(isDark).withOpacity(0.5),
              ),
              tooltip: 'Fork Chat',
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
              onPressed: () => _showForkConversationDialog(convId, title),
            ),
            IconButton(
              icon: Icon(
                Icons.delete_outline_rounded,
                size: 14,
                color: AppTokens.textSecondary(isDark).withOpacity(0.4),
              ),
              tooltip: 'Delete Chat',
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(minWidth: 24, minHeight: 24),
              onPressed: () => _confirmDeleteConversation(convId, title),
            ),
          ],
        ),
        onTap: () {
          _resumeConversation(convId, title);
        },
      ),
    );
  }

  Widget _buildDrawerItem(IconData icon, String title, VoidCallback onTap) {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    return ListTile(
      leading: Icon(icon, color: AppTokens.accent),
      title: Text(title, style: GoogleFonts.inter(color: AppTokens.textPrimary(isDark), fontSize: 15, fontWeight: FontWeight.w500)),
      onTap: onTap,
    );
  }

  // Helper method to merge HTTP tasks with real-time WebSocket data
  List<dynamic> _getMergedTasks() {
    List<dynamic> allTasks = List.from(_bgTasks);
    if (_activeJobId != null && _activeJobId!.isNotEmpty) {
      int existingIndex = allTasks.indexWhere((t) => t['id'] == _activeJobId);
      if (existingIndex != -1) {
        final Map<String, dynamic> existing = Map<String, dynamic>.from(allTasks[existingIndex] as Map);
        String polledStatus = existing['status']?.toString().toLowerCase() ?? '';
        
        // If the backend has marked it as done/failed, don't let local stuck state override it
        if (polledStatus == 'completed' || polledStatus == 'done' || polledStatus == 'failed' || polledStatus == 'error') {
          if (_activeJobStatus == 'running' || _activeJobStatus == 'queued' || _activeJobStatus == 'cancelling') {
             // Clear the stuck local state
             WidgetsBinding.instance.addPostFrameCallback((_) {
               if (mounted) {
                 setState(() {
                   _activeJobId = null;
                   _activeJobStatus = '';
                 });
               }
             });
          }
        } else {
          existing['status'] = _activeJobStatus;
        }
        
        if (_activeJobSummary.isNotEmpty) existing['action'] = _activeJobSummary;
        allTasks[existingIndex] = existing;
      } else {
        allTasks.add({
          'id': _activeJobId,
          'status': _activeJobStatus,
          'action': _activeJobSummary,
        });
      }
    }
    return allTasks;
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    
    return PopScope(
      canPop: false,
      onPopInvokedWithResult: (didPop, result) {
        if (didPop) return;
        if (_scaffoldKey.currentState?.isDrawerOpen ?? false) {
          _scaffoldKey.currentState?.closeDrawer();
        } else if (_scaffoldKey.currentState?.isEndDrawerOpen ?? false) {
          _scaffoldKey.currentState?.closeEndDrawer();
        }
      },
      child: Scaffold(
        key: _scaffoldKey,
        onDrawerChanged: (isOpen) {
          if (isOpen) {
            _fetchConversations();
          }
        },
        drawer: _isAssistant ? null : _buildDrawer(),
        endDrawer: _isAssistant ? null : _buildBgTasksSidebar(),
        backgroundColor: _isAssistant ? Colors.transparent : AppTokens.bg(appThemeMode.value == ThemeMode.dark),
        body: _isAssistant
          ? Stack(
              children: [
                // Backdrop touch dismisser
                Positioned.fill(
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () {
                      try {
                        platform.invokeMethod('closeOverlay');
                      } catch (_) {}
                      SystemNavigator.pop();
                    },
                    child: Container(color: Colors.transparent),
                  ),
                ),
                // Anchored floating assistant bottom sheet
                Positioned(
                  bottom: 0,
                  left: 0,
                  right: 0,
                  child: SafeArea(
                    top: false,
                    child: _buildRedesignedAssistantOverlay(colorScheme),
                  ),
                ),
              ],
            )
          : SafeArea(
              child: Container(
                width: double.infinity,
                height: double.infinity,
                color: Colors.transparent,
                child: _buildMainContent(colorScheme),
              ),
            ),
      ),
    );
  }

  Widget _buildSubtitleOverlay(ColorScheme colorScheme, bool isOverlayMode) {
    if (!_showSubtitles || _currentAiSubtitle.isEmpty) return const SizedBox.shrink();
    
    bool isDark = appThemeMode.value == ThemeMode.dark;

    if (isOverlayMode) {
      // System overlay: Transparent background, text shadow for legibility over random apps
      return Container(
        margin: const EdgeInsets.only(left: 16, right: 16, top: 10, bottom: 20),
        padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 20),
        width: double.infinity,
        constraints: const BoxConstraints(maxHeight: 250),
        decoration: const BoxDecoration(
          color: Colors.transparent, // Fully transparent as requested
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Flexible(
              child: SingleChildScrollView(
                physics: const BouncingScrollPhysics(),
                child: Text(
                  _currentAiSubtitle,
                  style: GoogleFonts.outfit(
                    fontSize: 20,
                    height: 1.4,
                    fontWeight: FontWeight.w700,
                    color: AppTokens.textPrimary(isDark),
                    shadows: [
                      Shadow(color: isDark ? Colors.black : Colors.white, blurRadius: 12),
                      Shadow(color: isDark ? Colors.black87 : Colors.white70, blurRadius: 4),
                    ],
                  ),
                  textAlign: TextAlign.center,
                ),
              ),
            ),
            if (!_isAiSpeaking)
              Padding(
                padding: const EdgeInsets.only(top: 16.0),
                child: InkWell(
                  onTap: () => _speak(_currentAiSubtitle),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    decoration: BoxDecoration(
                      color: AppTokens.accentSecondary.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(100),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.replay_circle_filled_rounded, size: 18, color: AppTokens.accentSecondary),
                        const SizedBox(width: 6),
                        Text("REPEAT AUDIO", style: GoogleFonts.spaceGrotesk(color: AppTokens.accentSecondary, fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 1.0)),
                      ],
                    ),
                  ),
                ),
              ),
          ],
        ),
      );
    } else {
      // Full screen mode: raw beautiful typography, no card bounds
      return Container(
        margin: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
        width: double.infinity,
        constraints: BoxConstraints(maxHeight: MediaQuery.of(context).size.height * 0.4),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.center,
              children: [
                Container(
                  width: 10,
                  height: 10,
                  decoration: const BoxDecoration(
                    color: AppTokens.accentSecondary,
                    shape: BoxShape.circle,
                  ),
                ),
                const SizedBox(width: 12),
                Text(
                  'AI SUBTITLE',
                  style: GoogleFonts.spaceGrotesk(
                    color: AppTokens.accentSecondary,
                    fontSize: 12,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 2.0,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 16),
            Flexible(
              child: SingleChildScrollView(
                physics: const BouncingScrollPhysics(),
                child: Text(
                  _currentAiSubtitle,
                  style: GoogleFonts.outfit(
                    fontSize: 28,
                    height: 1.4,
                    letterSpacing: 0.2,
                    fontWeight: FontWeight.w600,
                    color: AppTokens.textPrimary(isDark),
                  ),
                  textAlign: TextAlign.left,
                ),
              ),
            ),
            if (!_isAiSpeaking)
              Padding(
                padding: const EdgeInsets.only(top: 24.0),
                child: Align(
                  alignment: Alignment.centerRight,
                  child: InkWell(
                    onTap: () => _speak(_currentAiSubtitle),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                      decoration: BoxDecoration(
                        color: AppTokens.accentSecondary.withOpacity(0.1),
                        borderRadius: BorderRadius.circular(100),
                        border: Border.all(color: AppTokens.accentSecondary.withOpacity(0.3)),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          const Icon(Icons.replay_circle_filled_rounded, size: 20, color: AppTokens.accentSecondary),
                          const SizedBox(width: 8),
                          Text("REPEAT AUDIO", style: GoogleFonts.spaceGrotesk(color: AppTokens.accentSecondary, fontSize: 13, fontWeight: FontWeight.bold, letterSpacing: 1.0)),
                        ],
                      ),
                    ),
                  ),
                ),
              ),
          ],
        ),
      );
    }
  }

  Widget _buildOverlayActionChip({
    required IconData icon,
    required String label,
    required VoidCallback onTap,
    required bool isDark,
    bool isDanger = false,
  }) {
    final Color chipColor = isDanger
        ? const Color(0xFFEF4444).withOpacity(0.15)
        : (isDark ? const Color(0xFF1E222D) : const Color(0xFFF1F3F5));
    final Color textColor = isDanger
        ? const Color(0xFFEF4444)
        : AppTokens.textPrimary(isDark);
    final Color borderColor = isDanger
        ? const Color(0xFFEF4444).withOpacity(0.35)
        : (isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.08));

    return GestureDetector(
      behavior: HitTestBehavior.opaque,
      onTap: onTap,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
        decoration: BoxDecoration(
          color: chipColor,
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: borderColor),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 14, color: textColor),
            const SizedBox(width: 5),
            Text(
              label,
              style: GoogleFonts.inter(
                fontSize: 12,
                fontWeight: FontWeight.w600,
                color: textColor,
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildRedesignedAssistantOverlay(ColorScheme colorScheme) {
    final bool isDark = appThemeMode.value == ThemeMode.dark;
    final String activeDeviceName = _activeDevice.isNotEmpty ? (_devices[_activeDevice]?['name'] ?? 'Desktop') : 'Desktop Agent';

    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(32),
        gradient: LinearGradient(
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
          colors: isDark
              ? [
                  Colors.white.withOpacity(0.18),
                  const Color(0xFF131722).withOpacity(0.72),
                  const Color(0xFF0B0D14).withOpacity(0.88),
                ]
              : [
                  Colors.white.withOpacity(0.85),
                  const Color(0xFFF8FAFC).withOpacity(0.75),
                  const Color(0xFFE2E8F0).withOpacity(0.85),
                ],
          stops: const [0.0, 0.40, 1.0],
        ),
        border: Border.all(
          color: isDark ? Colors.white.withOpacity(0.20) : Colors.white.withOpacity(0.85),
          width: 1.4,
        ),
        boxShadow: [
          BoxShadow(
            color: isDark ? Colors.black.withOpacity(0.55) : const Color(0xFF64748B).withOpacity(0.25),
            blurRadius: 36,
            offset: const Offset(0, 14),
            spreadRadius: 2,
          ),
          BoxShadow(
            color: (isDark ? const Color(0xFF6366F1) : const Color(0xFF00E5FF)).withOpacity(0.10),
            blurRadius: 40,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(32),
        child: BackdropFilter(
          filter: ImageFilter.blur(sigmaX: 24, sigmaY: 24),
          child: FluidWaterOverlayContainer(
            isDark: isDark,
            isListening: _isListening,
            isSpeaking: _isAiSpeaking,
            isThinking: _isThinking,
            child: Padding(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  // 1. Top drag handle pill (floating)
                  FloatingWaterElement(
                    distanceFactor: -1.0,
                    child: Center(
                      child: Container(
                        width: 36,
                        height: 4,
                        decoration: BoxDecoration(
                          color: isDark ? Colors.white24 : Colors.black26,
                          borderRadius: BorderRadius.circular(2),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(height: 10),

                  // 2. Device status capsule + theme toggle + dismiss button (floating)
                  FloatingWaterElement(
                    distanceFactor: -0.75,
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4.5),
                          decoration: BoxDecoration(
                            color: isDark ? const Color(0xFF1E222D).withOpacity(0.85) : const Color(0xFFF1F3F5).withOpacity(0.85),
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(
                              color: isDark ? Colors.white12 : Colors.black12,
                            ),
                          ),
                          child: Row(
                            mainAxisSize: MainAxisSize.min,
                            children: [
                              Container(
                                width: 7,
                                height: 7,
                                decoration: BoxDecoration(
                                  color: _isConnected ? const Color(0xFF10B981) : const Color(0xFFEF4444),
                                  shape: BoxShape.circle,
                                  boxShadow: [
                                    if (_isConnected)
                                      BoxShadow(
                                        color: const Color(0xFF10B981).withOpacity(0.5),
                                        blurRadius: 6,
                                        spreadRadius: 1,
                                      ),
                                  ],
                                ),
                              ),
                              const SizedBox(width: 6),
                              Text(
                                activeDeviceName,
                                style: GoogleFonts.inter(fontSize: 11, fontWeight: FontWeight.w600, color: AppTokens.textPrimary(isDark)),
                              ),
                              const SizedBox(width: 4),
                              Text(
                                '• AGENT',
                                style: GoogleFonts.inter(fontSize: 10, fontWeight: FontWeight.w700, color: const Color(0xFF6366F1)),
                              ),
                            ],
                          ),
                        ),
                        Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            GestureDetector(
                              behavior: HitTestBehavior.opaque,
                              onTap: () {
                                saveThemeMode(isDark ? ThemeMode.light : ThemeMode.dark);
                              },
                              child: Container(
                                padding: const EdgeInsets.all(5),
                                margin: const EdgeInsets.only(right: 6),
                                decoration: BoxDecoration(
                                  color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                                  shape: BoxShape.circle,
                                  border: Border.all(color: isDark ? Colors.white10 : Colors.black12),
                                ),
                                child: Icon(
                                  isDark ? Icons.light_mode_rounded : Icons.dark_mode_rounded,
                                  size: 15,
                                  color: isDark ? Colors.amberAccent : AppTokens.textPrimary(isDark),
                                ),
                              ),
                            ),
                            GestureDetector(
                              behavior: HitTestBehavior.opaque,
                              onTap: () {
                                try { platform.invokeMethod('closeOverlay'); } catch (_) {}
                                SystemNavigator.pop();
                              },
                              child: Container(
                                padding: const EdgeInsets.all(5),
                                decoration: BoxDecoration(
                                  color: isDark ? Colors.white.withOpacity(0.08) : Colors.black.withOpacity(0.06),
                                  shape: BoxShape.circle,
                                  border: Border.all(color: isDark ? Colors.white10 : Colors.black12),
                                ),
                                child: Icon(Icons.close_rounded, size: 15, color: AppTokens.textSecondary(isDark)),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),

                  // 3. Screenshot Preview (if captured) (floating)
                  if (_temporaryAssistantImage != null) ...[
                    const SizedBox(height: 10),
                    FloatingWaterElement(
                      distanceFactor: -0.45,
                      child: GestureDetector(
                        behavior: HitTestBehavior.opaque,
                        onTap: () {
                          showDialog(
                            context: context,
                            builder: (context) => Dialog(
                              backgroundColor: Colors.transparent,
                              insetPadding: EdgeInsets.zero,
                              child: Stack(
                                alignment: Alignment.center,
                                children: [
                                  InteractiveViewer(
                                    panEnabled: true,
                                    boundaryMargin: const EdgeInsets.all(20),
                                    minScale: 0.5,
                                    maxScale: 4,
                                    child: Image.memory(
                                      (() { try { return base64Decode(_temporaryAssistantImage!); } catch (_) { return Uint8List(0); } })(),
                                      fit: BoxFit.contain,
                                    ),
                                  ),
                                  Positioned(
                                    top: 40,
                                    right: 20,
                                    child: IconButton(
                                      icon: const Icon(Icons.close, color: Colors.white, size: 30),
                                      onPressed: () => Navigator.pop(context),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                        child: Container(
                          constraints: const BoxConstraints(maxHeight: 160),
                          decoration: BoxDecoration(
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: Colors.white.withOpacity(0.1)),
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(16),
                            child: Image.memory(
                              (() { try { return base64Decode(_temporaryAssistantImage!); } catch (_) { return Uint8List(0); } })(),
                              fit: BoxFit.contain,
                              errorBuilder: (c, e, s) => const SizedBox.shrink(),
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],

                  const SizedBox(height: 12),

                  // 4. Live Transcription / Status subtitle (floating)
                  FloatingWaterElement(
                    distanceFactor: -0.25,
                    child: Container(
                      constraints: const BoxConstraints(maxHeight: 70),
                      padding: const EdgeInsets.symmetric(horizontal: 8),
                      child: SingleChildScrollView(
                        physics: const BouncingScrollPhysics(),
                        child: Text(
                          _currentAiSubtitle.isNotEmpty
                              ? _currentAiSubtitle
                              : (_isListening
                                  ? 'Listening...'
                                  : (_isThinking
                                      ? 'Thinking...'
                                      : (_isAiSpeaking ? 'AI speaking...' : 'Ready for voice or text prompt'))),
                          style: GoogleFonts.outfit(
                            fontSize: 16,
                            height: 1.35,
                            fontWeight: FontWeight.w600,
                            color: _currentAiSubtitle.isNotEmpty ? AppTokens.textPrimary(isDark) : AppTokens.textSecondary(isDark),
                            shadows: [
                              Shadow(color: isDark ? Colors.black87 : Colors.white70, blurRadius: 6),
                            ],
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    ),
                  ),

                  const SizedBox(height: 10),

                  // 5. Center 3D Mic Button with underwater ripples & tactile volumetric depth
                  Center(
                    child: Volumetric3DMicButton(
                      isListening: _isListening,
                      isSpeaking: _isAiSpeaking,
                      isThinking: _isThinking,
                      isDark: isDark,
                      onTap: () {
                        if (_isListening) {
                          _stopListening();
                        } else if (_isThinking) {
                          _cancelBackendTask();
                        } else {
                          setState(() { _isLiveSession = true; });
                          _startListening();
                        }
                      },
                    ),
                  ),

                  // 5.5 Proactive Watchdog Card (when background task is active or failed)
                  (() {
                    Map<String, dynamic>? activeWatchdogTask;
                    for (final t in _bgTasks) {
                      if (t is Map) {
                        final tid = t['id']?.toString();
                        if (tid == _dismissedWatchdogTaskId) continue;
                        final status = t['status']?.toString();
                        if (status == 'running' || status == 'failed') {
                          activeWatchdogTask = Map<String, dynamic>.from(t);
                          break;
                        }
                      }
                    }
                    if (activeWatchdogTask != null) {
                      return Padding(
                        padding: const EdgeInsets.only(top: 10),
                        child: FloatingWaterElement(
                          distanceFactor: 0.15,
                          child: _buildProactiveWatchdogCard(activeWatchdogTask, isDark),
                        ),
                      );
                    }
                    return const SizedBox.shrink();
                  })(),

                  // 5.6 Ambient Smart Clipboard Card
                  if (_activeClipboardSuggestion != null) ...[
                    const SizedBox(height: 10),
                    FloatingWaterElement(
                      distanceFactor: 0.22,
                      child: _buildAmbientClipboardCard(_activeClipboardSuggestion!, isDark),
                    ),
                  ],

                  // 5.7 Contextual Workday Briefing Card
                  if (_activeWorkdayBriefing != null) ...[
                    const SizedBox(height: 10),
                    FloatingWaterElement(
                      distanceFactor: 0.28,
                      child: _buildWorkdayBriefingCard(_activeWorkdayBriefing!, isDark),
                    ),
                  ],

                  // 5.8 Autonomous Nightly Guardian Card
                  if (_activeNightlyAuditReport != null) ...[
                    const SizedBox(height: 10),
                    FloatingWaterElement(
                      distanceFactor: 0.30,
                      child: _buildNightlyGuardianCard(_activeNightlyAuditReport!, isDark),
                    ),
                  ],

                  const SizedBox(height: 12),

                  // 6. Quick Action Context Chips (floating)
                  FloatingWaterElement(
                    distanceFactor: 0.35,
                    child: SingleChildScrollView(
                      scrollDirection: Axis.horizontal,
                      physics: const BouncingScrollPhysics(),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          _buildOverlayActionChip(
                            icon: Icons.camera_alt_outlined,
                            label: 'Screenshot',
                            onTap: () {
                              _controller.text = "__SCREENSHOT__";
                              _sendMessage();
                            },
                            isDark: isDark,
                          ),
                          const SizedBox(width: 8),
                          _buildOverlayActionChip(
                            icon: Icons.wb_sunny_outlined,
                            label: 'Briefing',
                            onTap: () {
                              if (_isConnected && _activeDevice.isNotEmpty && _activeDevice.startsWith('desktop-')) {
                                final message = {
                                  'type': 'command',
                                  'device_id': _activeDevice,
                                  'command': '__GET_WORKDAY_BRIEFING__',
                                  'session_token': _sessionToken,
                                };
                                _channel?.sink.add(jsonEncode(message));
                              } else {
                                _controller.text = "Give me a workday briefing";
                                _sendMessage();
                              }
                            },
                            isDark: isDark,
                          ),
                          if (_isThinking || _isListening) ...[
                            const SizedBox(width: 8),
                            _buildOverlayActionChip(
                              icon: Icons.stop_rounded,
                              label: 'Stop',
                              isDanger: true,
                              onTap: () {
                                _cancelBackendTask();
                                _stopListening();
                              },
                              isDark: isDark,
                            ),
                          ],
                        ],
                      ),
                    ),
                  ),

                  const SizedBox(height: 14),

                  // 7. Floating capsule input bar (floating)
                  FloatingWaterElement(
                    distanceFactor: 0.75,
                    child: _buildInputArea(colorScheme),
                  ),
                ],
              ),
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildMainContent(ColorScheme colorScheme) {
    if (_isAssistant) {
      return _buildRedesignedAssistantOverlay(colorScheme);
    }

    // Full layout for normal App Mode
    return Column(
      children: [
        // Custom Modal Header
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
          decoration: BoxDecoration(
            border: Border(bottom: BorderSide(color: AppTokens.border(appThemeMode.value == ThemeMode.dark))),
          ),
          child: Row(
            children: [
              IconButton(
                icon: Icon(Icons.menu_rounded, size: 22, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
                onPressed: () => _scaffoldKey.currentState?.openDrawer(),
              ),
              Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Text(
                    'VOILA VOICE',
                    style: GoogleFonts.spaceGrotesk(fontSize: 20, fontWeight: FontWeight.w800, letterSpacing: -1.0, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
                  ),
                  if (_currentConversationId.isNotEmpty)
                    GestureDetector(
                      onTap: () => _scaffoldKey.currentState?.openDrawer(),
                      child: Container(
                        margin: const EdgeInsets.only(top: 2),
                        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 1.5),
                        decoration: BoxDecoration(
                          color: AppTokens.accentSecondary.withOpacity(0.12),
                          borderRadius: BorderRadius.circular(6),
                          border: Border.all(color: AppTokens.accentSecondary.withOpacity(0.3)),
                        ),
                        child: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            Container(
                              width: 5,
                              height: 5,
                              decoration: const BoxDecoration(
                                color: Color(0xFF10B981),
                                shape: BoxShape.circle,
                              ),
                            ),
                            const SizedBox(width: 4),
                            ConstrainedBox(
                              constraints: const BoxConstraints(maxWidth: 110),
                              child: Text(
                                _getActiveConversationTitle(),
                                style: GoogleFonts.inter(
                                  fontSize: 10,
                                  fontWeight: FontWeight.w600,
                                  color: AppTokens.accentSecondary,
                                ),
                                overflow: TextOverflow.ellipsis,
                                maxLines: 1,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                ],
              ),
              const Spacer(),
              if (_currentMode.toUpperCase() == 'AGENT')
                IconButton(
                  icon: Icon(Icons.auto_awesome, size: 22, color: _selectedModel.isNotEmpty ? AppTokens.accent : AppTokens.textSecondary(appThemeMode.value == ThemeMode.dark)),
                  onPressed: _showModelSelector,
                ),
              IconButton(
                icon: Icon(appThemeMode.value == ThemeMode.dark ? Icons.light_mode_rounded : Icons.dark_mode_rounded, size: 22, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
                onPressed: () {
                  saveThemeMode(appThemeMode.value == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark);
                },
              ),
              const SizedBox(width: 4),
              Flexible(
                child: GestureDetector(
                  onTap: () => _showDeviceSelector(context),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                    decoration: BoxDecoration(
                      color: AppTokens.cardAlt(appThemeMode.value == ThemeMode.dark),
                      borderRadius: BorderRadius.circular(20),
                      border: Border.all(color: AppTokens.border(appThemeMode.value == ThemeMode.dark)),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.computer_rounded, size: 14, color: AppTokens.accent),
                        const SizedBox(width: 6),
                        Flexible(
                          child: Text(
                            _activeDevice.isEmpty ? 'Select Device' : (_devices[_activeDevice]?['name'] ?? 'Desktop'),
                            style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w500, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
                            overflow: TextOverflow.ellipsis,
                            maxLines: 1,
                          ),
                        ),
                        const SizedBox(width: 4),
                        Icon(Icons.keyboard_arrow_down_rounded, size: 14, color: AppTokens.textSecondary(appThemeMode.value == ThemeMode.dark)),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
        Expanded(
          child: Column(
            children: [
              GestureDetector(
                onTap: () { if (mounted) setState(() => _showFlowchart = !_showFlowchart); },
                child: Container(
                  padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 16),
                  color: Colors.transparent,
                  child: Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(_showFlowchart ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down, size: 16, color: Colors.white54),
                      const SizedBox(width: 4),
                      Text(_showFlowchart ? 'Hide Connection Info' : 'Show Connection Info', style: const TextStyle(fontSize: 12, color: Colors.white54)),
                    ],
                  ),
                ),
              ),
              AnimatedCrossFade(
                firstChild: const SizedBox(width: double.infinity, height: 0),
                secondChild: ConnectionFlowchart(
                  isBackendConnected: _isHealthy,
                  isLocalAgentConnected: _localAgentConnected,
                  isWebSocketConnected: _isConnected,
                  isDataDeparting: _isDataDeparting,
                  isDataArriving: _isDataArriving,
                  activeDeviceName: _activeDevice.isNotEmpty ? (_devices[_activeDevice]?['name'] ?? 'Desktop') : null,
                ),
                crossFadeState: _showFlowchart ? CrossFadeState.showSecond : CrossFadeState.showFirst,
                duration: const Duration(milliseconds: 250),
              ),
              const SizedBox(height: 12),
              Padding(
                padding: const EdgeInsets.symmetric(horizontal: 16),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    _buildModeToggle(colorScheme),
                    Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        AnimatedSize(
                          duration: const Duration(milliseconds: 350),
                          curve: Curves.easeInOutCubic,
                          child: _bgTasks.isEmpty ? const SizedBox.shrink() :
                            Builder(
                              builder: (BuildContext ctx) {
                                int runningCount = _bgTasks.where((t) => t['status'] == 'running').length;
                                return GestureDetector(
                                  onTap: () async {
                                    if (!await _ensureUnlocked()) return;
                                    if (mounted) Scaffold.of(ctx).openEndDrawer();
                                  },
                                  child: AnimatedContainer(
                                    duration: const Duration(milliseconds: 300),
                                    curve: Curves.easeInOutCubic,
                                    margin: const EdgeInsets.only(left: 12),
                                    padding: EdgeInsets.symmetric(horizontal: runningCount > 0 ? 14 : 10, vertical: 10),
                                    decoration: BoxDecoration(
                                      color: runningCount > 0 ? const Color(0xFF0F766E).withOpacity(0.4) : const Color(0xFF222222).withOpacity(0.5),
                                      borderRadius: BorderRadius.circular(100),
                                      border: Border.all(color: runningCount > 0 ? const Color(0xFF14B8A6).withOpacity(0.5) : Colors.white24),
                                    ),
                                    child: Row(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        if (runningCount > 0) ...[
                                          Container(
                                            padding: const EdgeInsets.all(4),
                                            decoration: const BoxDecoration(color: Color(0xFF14B8A6), shape: BoxShape.circle),
                                            child: Text(
                                              runningCount.toString(),
                                              style: const TextStyle(color: Colors.black, fontSize: 10, fontWeight: FontWeight.w900),
                                            ),
                                          ),
                                          const SizedBox(width: 8),
                                        ],
                                        Icon(Icons.memory, size: 16, color: runningCount > 0 ? const Color(0xFF2DD4BF) : Colors.white54),
                                        if (runningCount > 0) ...[
                                          const SizedBox(width: 6),
                                          const Text('RUNNING', style: TextStyle(color: Color(0xFF5EEAD4), fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 0.5)),
                                        ]
                                      ],
                                    ),
                                  ),
                                );
                              }
                            ),
                        ),
                        if (_currentMode.toUpperCase() == 'AGENT')
                          GestureDetector(
                            behavior: HitTestBehavior.opaque,
                            onTap: _openLiveModeSheet,
                            child: Container(
                              padding: const EdgeInsets.all(8),
                              margin: const EdgeInsets.only(left: 8),
                              decoration: BoxDecoration(
                                gradient: const LinearGradient(
                                  colors: [Color(0xFF6366F1), Color(0xFF8B5CF6), Color(0xFFEC4899)],
                                ),
                                shape: BoxShape.circle,
                                boxShadow: [
                                  BoxShadow(
                                    color: const Color(0xFF8B5CF6).withOpacity(0.35),
                                    blurRadius: 6,
                                    offset: const Offset(0, 2),
                                  ),
                                ],
                              ),
                              child: const Icon(Icons.sensors_rounded, size: 16, color: Colors.white),
                            ),
                          ),
                      ],
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Expanded(child: _buildMessagesList(colorScheme)),
              
              _buildSubtitleOverlay(colorScheme, true),
              _buildTaskWorkflow(colorScheme),
              _buildInputArea(colorScheme),
            ],
          ),
        ),
      ],
    );
  }

  String _normalizeForSpeech(String text) {
    return SpeechNormalizer.normalize(text);
  }

  Future<void> _speak(String text) async {
    if (_isAiSpeaking) return; // Prevent overlapping TTS
    if (!_willTalk || text.isEmpty) return;
    
    if (mounted) {
      setState(() {
        _currentAiSubtitle = text;
        _isAiSpeaking = true;
      });
    }

    String cleanText = _normalizeForSpeech(text);
    
    // T1.4 Prioritize network (Edge) TTS first
    bool edgeSuccess = await _playEdgeTts(cleanText);
    
    if (!edgeSuccess) {
      // Fallback to native built-in TTS
      try {
        final Iterable<Match> matches = SpeechNormalizer.chunkRegex.allMatches(cleanText);
        
        for (final Match match in matches) {
          String chunk = match.group(0)?.trim() ?? "";
          if (chunk.isEmpty) continue;
          
          double pitch = 0.85;
          double rate = 0.55; 
          
          if (chunk.contains('?')) {
            pitch = 1.15; rate = 0.5;
          } else if (chunk.contains('!')) {
            pitch = 1.1; rate = 0.6;
          } else if (chunk.contains('...')) {
            pitch = 0.75; rate = 0.4;
          } else if (chunk.toLowerCase().contains("boss")) {
            pitch = 0.80;
          } else if (chunk.toLowerCase().contains("error") || chunk.toLowerCase().contains("fail")) {
            pitch = 0.9; rate = 0.45;
          }
          
          await flutterTts.setPitch(pitch);
          await flutterTts.setSpeechRate(rate);
          
          await flutterTts.speak(chunk);
          if (chunk.contains(',') || chunk.contains(';') || chunk.contains(':')) {
            await Future.delayed(const Duration(milliseconds: 220));
          } else {
            await Future.delayed(const Duration(milliseconds: 350));
          }
        }
      } catch (e) {
        debugPrint("TTS Speak Error: $e");
        await flutterTts.setPitch(1.0);
        await flutterTts.speak(cleanText);
      }
    }
    
    if (mounted) {
      setState(() {
        _isAiSpeaking = false;
      });
      // Auto-restart listening if in a live session
      if (_isLiveSession) {
        _startListening();
      }
    }
  }

  String _formatSsmlProsody(String text) {
    // 1. XML character escaping
    String clean = text
        .replaceAll('&', '&amp;')
        .replaceAll('<', '&lt;')
        .replaceAll('>', '&gt;')
        .replaceAll('"', '&quot;')
        .replaceAll("'", '&apos;');

    // 2. Syntactic human prosody pausing (English grammar)
    // Commas: short syntactic breath pause (~220ms)
    clean = clean.replaceAllMapped(RegExp(r',(?:\s+|$)'), (m) => ', <break time="220ms"/> ');
    // Semicolons and Colons: clause punctuation pause (~320ms)
    clean = clean.replaceAllMapped(RegExp(r';(?:\s+|$)'), (m) => '; <break time="320ms"/> ');
    clean = clean.replaceAllMapped(RegExp(r':(?:\s+|$)'), (m) => ': <break time="300ms"/> ');
    // Em dash / parenthetical dashes: (~260ms)
    clean = clean.replaceAllMapped(RegExp(r'\s+[-–—]\s+'), (m) => ' <break time="260ms"/> ');
    // Sentence terminals (periods, question marks, exclamations): (~450ms)
    clean = clean.replaceAllMapped(RegExp(r'\.(?:\s+|$)'), (m) => '. <break time="450ms"/> ');
    clean = clean.replaceAllMapped(RegExp(r'\?(?:\s+|$)'), (m) => '? <break time="450ms"/> ');
    clean = clean.replaceAllMapped(RegExp(r'!(?:\s+|$)'), (m) => '! <break time="450ms"/> ');
    // Paragraph breaks: (~550ms)
    clean = clean.replaceAll(RegExp(r'\n{2,}'), ' <break time="550ms"/> ');
    clean = clean.replaceAll('\n', ' <break time="300ms"/> ');

    return clean;
  }

  Future<bool> _playEdgeTts(String text) async {
    try {
      final String endpoint = "wss://speech.platform.bing.com/consumer/speech/synthesize/readaloud/edge/v1?TrustedClientToken=6A5AA1D4EAFF4E9FB37E23D68491D6F4";
      final channel = WebSocketChannel.connect(Uri.parse(endpoint));
      
      final String uuid = const Uuid().v4().replaceAll('-', '');
      final String dt = DateTime.now().toUtc().toIso8601String();
      
      final String configMsg = "X-Timestamp:$dt\r\n"
          "Content-Type:application/json; charset=utf-8\r\n"
          "Path:speech.config\r\n\r\n"
          '{"context":{"synthesis":{"audio":{"metadataoptions":{"sentenceBoundaryEnabled":"false","wordBoundaryEnabled":"false"},"outputFormat":"audio-24khz-48kbitrate-mono-mp3"}}}}';
      
      channel.sink.add(configMsg);

      final String formattedText = _formatSsmlProsody(text);
      final String ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-IN'><voice name='en-IN-NeerjaNeural'><prosody pitch='+0Hz' rate='-10%'>$formattedText</prosody></voice></speak>";

      final String reqMsg = "X-RequestId:$uuid\r\n"
          "Content-Type:application/ssml+xml\r\n"
          "X-Timestamp:$dt\r\n"
          "Path:ssml\r\n\r\n"
          "$ssml";
          
      channel.sink.add(reqMsg);

      List<int> audioData = [];
      bool success = false;
      
      await for (var message in channel.stream) {
        if (message is String) {
          if (message.contains("Path:turn.end")) {
            success = true;
            channel.sink.close();
            break;
          }
        } else if (message is Uint8List) {
          String headerStr = String.fromCharCodes(message.take(256));
          int headerEnd = headerStr.indexOf("\r\n\r\n");
          if (headerEnd != -1) {
            audioData.addAll(message.skip(headerEnd + 4));
          }
        }
      }

      if (success && audioData.isNotEmpty) {
        final dir = await getTemporaryDirectory();
        final file = File('${dir.path}/summary.mp3');
        await file.writeAsBytes(audioData);
        
        final player = AudioPlayer();
        try {
          await player.play(DeviceFileSource(file.path));
          await player.onPlayerComplete.first;
          return true;
        } finally {
          await player.dispose();
        }
      }
      return false;
    } catch (e) {
      debugPrint("Edge TTS error: $e");
      return false;
    }
  }

  // T1.3 Natural summary TTS using lightweight high-quality fallback
  Future<void> _speakSummary(String text, {bool isCritical = false}) async {
    if (_isAiSpeaking) return; // Prevent overlapping TTS
    if (!isCritical && _isQuietHoursActive()) { debugPrint('Quiet hours active, suppressing summary.'); return; }
    if (!_willTalk || text.isEmpty) return;
    
    String cleanText = _normalizeForSpeech(text);
    if (cleanText.length > 300) {
      cleanText = cleanText.substring(0, 300) + "..."; 
    }
    
    if (mounted) {
      setState(() {
        _currentAiSubtitle = "Summary: " + cleanText;
        _isAiSpeaking = true;
      });
    }

    bool edgeSuccess = await _playEdgeTts(cleanText);

    if (!edgeSuccess) {
      try {
        // Try to use a high-quality "network" voice natively
        List<dynamic> voices = await flutterTts.getVoices;
        for (var voice in voices) {
          if (voice["name"] != null && voice["name"].toString().toLowerCase().contains("network")) {
            await flutterTts.setVoice({"name": voice["name"], "locale": voice["locale"]});
            break;
          }
        }
        
        await flutterTts.setPitch(1.0);
        await flutterTts.setSpeechRate(0.5);
        await flutterTts.speak(cleanText);
      } catch (e) {
        debugPrint("HQ TTS failed: $e");
        await flutterTts.speak(cleanText);
      }
    }
    
    if (mounted) {
      setState(() {
        _isAiSpeaking = false;
      });
    }
  }


  void _showSettingsSheet(BuildContext context) {
    FocusScope.of(context).unfocus();
    bool isDark = appThemeMode.value == ThemeMode.dark;
    
    showModalBottomSheet(
      context: context,
      backgroundColor: AppTokens.bg(isDark),
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(32))),
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Center(
                  child: Container(
                    width: 40,
                    height: 4,
                    margin: const EdgeInsets.only(bottom: 24),
                    decoration: BoxDecoration(color: AppTokens.border(isDark), borderRadius: BorderRadius.circular(10)),
                  ),
                ),
                Text('SETTINGS', style: GoogleFonts.spaceGrotesk(fontSize: 14, fontWeight: FontWeight.w800, color: AppTokens.textSecondary(isDark), letterSpacing: 1.5)),
                const SizedBox(height: 24),
                Container(
                  decoration: BoxDecoration(
                    color: AppTokens.card(isDark),
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(color: AppTokens.border(isDark)),
                  ),
                  child: Column(
                    children: [
                      SwitchListTile(
                        title: Text('Smart Subtitles', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: AppTokens.textPrimary(isDark))),
                        subtitle: Text('Show scrolling text when AI speaks', style: GoogleFonts.inter(fontSize: 13, color: AppTokens.textSecondary(isDark))),
                        value: _showSubtitles,
                        onChanged: (val) {
                          if (mounted) setState(() => _showSubtitles = val);
                          _storage.write(key: 'show_subtitles', value: val.toString());
                          Navigator.pop(context);
                        },
                        activeColor: AppTokens.accentSecondary,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                      ),
                      Divider(color: AppTokens.border(isDark), height: 1),
                      SwitchListTile(
                        title: Text('Auto-read Responses', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: AppTokens.textPrimary(isDark))),
                        value: _willTalk,
                        activeColor: AppTokens.accentSecondary,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                        onChanged: (bool value) {
                          if (mounted) setState(() => _willTalk = value);
                          _storage.write(key: 'will_talk', value: value.toString());
                          Navigator.pop(context);
                        },
                      ),
                      Divider(color: AppTokens.border(isDark), height: 1),
                      SwitchListTile(
                        title: Text('Graphify Multi-Model', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: AppTokens.textPrimary(isDark))),
                        subtitle: Text('Chain models to boost reasoning', style: GoogleFonts.inter(fontSize: 13, color: AppTokens.textSecondary(isDark))),
                        value: _graphifyEnabled,
                        activeColor: AppTokens.accentSecondary,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                        onChanged: (bool value) {
                          if (mounted) setState(() => _graphifyEnabled = value);
                          _storage.write(key: 'graphify_enabled', value: value.toString());
                          Navigator.pop(context);
                        },
                      ),
                      Divider(color: AppTokens.border(isDark), height: 1),
                      SwitchListTile(
                        title: Text('Quiet Hours', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: AppTokens.textPrimary(isDark))),
                        subtitle: Text('Suppress voice summaries (10 PM - 7 AM)', style: GoogleFonts.inter(fontSize: 13, color: AppTokens.textSecondary(isDark))),
                        value: _quietHoursEnabled,
                        activeColor: AppTokens.accentSecondary,
                        contentPadding: const EdgeInsets.symmetric(horizontal: 20, vertical: 8),
                        onChanged: (bool value) {
                          if (mounted) setState(() => _quietHoursEnabled = value);
                          _storage.write(key: 'quiet_hours_enabled', value: value.toString());
                          Navigator.pop(context);
                        },
                      ),
                      Divider(color: AppTokens.border(isDark), height: 1),
                      ListTile(
                        title: Text('Lock Session', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: const Color(0xFFF59E0B))),
                        leading: const Icon(Icons.lock_rounded, color: Color(0xFFF59E0B), size: 20),
                        onTap: () async {
                          Navigator.pop(context);
                          await _storage.delete(key: 'session_token');
                          if (mounted) {
                            setState(() {
                              _sessionToken = '';
                            });
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Session locked. Token destroyed.')),
                            );
                          }
                        },
                      ),
                      Divider(color: AppTokens.border(isDark), height: 1),
                      ListTile(
                        title: Text('Clear Local Data', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: const Color(0xFFEF4444))),
                        leading: const Icon(Icons.delete_rounded, color: Color(0xFFEF4444), size: 20),
                        onTap: () {
                          Navigator.pop(context);
                          _clearLocalData();
                        },
                      ),
                      Divider(color: AppTokens.border(isDark), height: 1),
                      ListTile(
                        title: Text('Clear Backend Devices', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: const Color(0xFFEF4444))),
                        leading: const Icon(Icons.delete_sweep_rounded, color: Color(0xFFEF4444), size: 20),
                        onTap: () {
                          Navigator.pop(context);
                          _clearBackendData();
                        },
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),
                _TokenUsageRow(tokenData: _lastTokenUsage),
              ],
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildStatusDot(bool isOnline, Color color) {
    return Container(
      width: 10,
      height: 10,
      decoration: BoxDecoration(
        color: isOnline ? color : Colors.grey.withOpacity(0.5),
        shape: BoxShape.circle,
        boxShadow: isOnline ? [
          BoxShadow(
            color: color.withOpacity(0.4),
            blurRadius: 4,
            spreadRadius: 1,
          )
        ] : null,
      ),
    );
  }

  void _showDeviceSelector(BuildContext context) {
    FocusScope.of(context).unfocus();
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1A1A1F),
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  const Text('Active Devices', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
                  IconButton(
                    icon: const Icon(Icons.refresh, size: 20),
                    onPressed: () {
                      _getDevices();
                      Navigator.pop(context);
                    },
                  ),
                ],
              ),
              const SizedBox(height: 12),
              if (_devices.isEmpty)
                const Padding(
                  padding: EdgeInsets.symmetric(vertical: 20),
                  child: Center(child: Text('No devices online', style: TextStyle(color: Colors.white54))),
                )
              else
                ..._devices.entries.map((entry) {
                  final isSelected = entry.key == _activeDevice;
                  return ListTile(
                    contentPadding: EdgeInsets.zero,
                    leading: _buildStatusDot(true, const Color(0xFF3DDC97)),
                    title: Text(entry.value['name'] ?? entry.key, style: TextStyle(fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal)),
                    trailing: isSelected ? const Icon(Icons.check, color: Color(0xFF7C6CFF), size: 20) : null,
                    onTap: () {
                      _switchDevice(entry.key);
                      Navigator.pop(context);
                    },
                  );
                }),
            ],
          ),
          ),
        ),
      ),
    );
  }

  Widget _buildModeToggle(ColorScheme colorScheme) {
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
                style: GoogleFonts.spaceGrotesk(
                  color: isAgent ? Colors.white : AppTokens.textSecondary(isDark),
                  fontWeight: FontWeight.w800,
                  fontSize: 14,
                  letterSpacing: 1.5,
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
                style: GoogleFonts.spaceGrotesk(
                  color: !isAgent ? AppTokens.textPrimary(isDark) : AppTokens.textSecondary(isDark),
                  fontWeight: FontWeight.w800,
                  fontSize: 14,
                  letterSpacing: 1.5,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMessagesList(ColorScheme colorScheme) {
    return ListView.builder(
      controller: _scrollController,
      cacheExtent: 150.0,
      addRepaintBoundaries: true,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      itemCount: _messages.length + (_isThinking ? 1 : 0),
      itemBuilder: (context, index) {
        if (index == _messages.length && _isThinking) {
          return _buildSkeletonLoader();
        }
        return _buildMessageCard(_messages[index], colorScheme);
      },
    );
  }

  Widget _buildSkeletonLoader() {
    return Container(
      margin: const EdgeInsets.only(bottom: 16, right: 40),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1F),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.04)),
      ),
      child: Row(
        children: [
          const SizedBox(
            width: 14, height: 14,
            child: CircularProgressIndicator(strokeWidth: 2, color: Color(0xFF7C6CFF)),
          ),
          const SizedBox(width: 12),
          Text(_currentStatus, style: TextStyle(fontSize: 13, color: Colors.white.withOpacity(0.6))),
        ],
      ),
    );
  }

  Widget _buildMessageCard(Map<String, dynamic> message, ColorScheme colorScheme) {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    bool isAgent = _currentMode.toUpperCase() == 'AGENT';
    final type = message['type'] as String? ?? 'unknown';
    final content = message['content'] as String? ?? '';
    final isUser = type == 'user';
    final isError = type == 'error';
    final isSystem = type == 'system';
    
    bool isImage = false;
    String displayContent = content;
    Uint8List? imageBytes;
    if (content.startsWith('__IMAGE__:')) {
      isImage = true;
      if (message['_cachedBytes'] is Uint8List) {
        imageBytes = message['_cachedBytes'] as Uint8List;
      } else {
        try {
          final cleanBase64 = content.substring(10).replaceAll(RegExp(r'\s+'), '');
          imageBytes = base64Decode(cleanBase64);
          message['_cachedBytes'] = imageBytes;
        } catch (_) {}
      }
    }

    // Guard against hollow empty bubbles
    if (content.trim().isEmpty && !isImage) {
      return const SizedBox.shrink();
    }

    final screenWidth = MediaQuery.of(context).size.width;

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      child: isUser
          // User messages: Dynamic WhatsApp-style bubble (hugs text width, max width 82% of screen)
          ? Align(
              alignment: Alignment.centerRight,
              child: ConstrainedBox(
                constraints: BoxConstraints(
                  maxWidth: screenWidth * 0.82,
                  minWidth: 48,
                ),
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
                  decoration: BoxDecoration(
                    color: AppTokens.accent,
                    borderRadius: const BorderRadius.only(
                      topLeft: Radius.circular(18),
                      topRight: Radius.circular(18),
                      bottomLeft: Radius.circular(18),
                      bottomRight: Radius.circular(4),
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: AppTokens.accent.withOpacity(0.3),
                        blurRadius: 10,
                        offset: const Offset(0, 4),
                      )
                    ],
                  ),
                  child: isImage
                      ? ClipRRect(
                          borderRadius: BorderRadius.circular(12),
                          child: (imageBytes != null)
                              ? Image.memory(
                                  imageBytes,
                                  fit: BoxFit.cover,
                                  cacheWidth: 800,
                                  gaplessPlayback: true,
                                )
                              : const SizedBox.shrink(),
                        )
                      : Text(
                          content,
                          style: GoogleFonts.inter(
                            color: Colors.white,
                            fontSize: 15,
                            fontWeight: FontWeight.w600,
                          ),
                        ),
                ),
              ),
            )
          // System/AI/Shell responses: Dynamic bubble aligned left (hugs content, max width 88% / 94% of screen)
          : Align(
              alignment: Alignment.centerLeft,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                mainAxisSize: MainAxisSize.min,
                children: [
                  Row(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.center,
                    children: [
                      Container(
                        width: 8,
                        height: 8,
                        decoration: BoxDecoration(
                          color: isError ? const Color(0xFFEF4444) : (isAgent ? AppTokens.accentSecondary : AppTokens.textSecondary(isDark)),
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 8),
                      Text(
                        isError ? 'SYSTEM ERROR' : (isSystem ? 'SYSTEM' : (isAgent ? 'AI ASSISTANT' : 'SHELL OUTPUT')),
                        style: GoogleFonts.spaceGrotesk(
                          color: isError ? const Color(0xFFEF4444) : (isAgent ? AppTokens.accentSecondary : AppTokens.textSecondary(isDark)),
                          fontSize: 11,
                          fontWeight: FontWeight.w800,
                          letterSpacing: 2.0,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  isImage
                      ? ConstrainedBox(
                          constraints: BoxConstraints(maxWidth: screenWidth * 0.88),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(18),
                            child: (imageBytes != null)
                                ? Image.memory(
                                    imageBytes,
                                    fit: BoxFit.cover,
                                    cacheWidth: 800,
                                    gaplessPlayback: true,
                                  )
                                : const SizedBox.shrink(),
                          ),
                        )
                      : (isAgent 
                          // Dynamic Bento Box rich styling for AI Assistant (WhatsApp-style maxWidth 88%, wraps content)
                          ? ConstrainedBox(
                              constraints: BoxConstraints(
                                maxWidth: screenWidth * 0.88,
                                minWidth: 60,
                              ),
                              child: Container(
                                decoration: BoxDecoration(
                                  color: AppTokens.card(isDark),
                                  borderRadius: const BorderRadius.only(
                                    topLeft: Radius.circular(4),
                                    topRight: Radius.circular(18),
                                    bottomLeft: Radius.circular(18),
                                    bottomRight: Radius.circular(18),
                                  ),
                                  border: Border.all(color: AppTokens.border(isDark), width: 1.5),
                                  boxShadow: AppTokens.shadow(isDark),
                                ),
                                child: Container(
                                  decoration: BoxDecoration(
                                    border: Border(
                                      left: BorderSide(color: AppTokens.accentSecondary, width: 4),
                                    ),
                                    borderRadius: const BorderRadius.only(
                                      topLeft: Radius.circular(4),
                                      topRight: Radius.circular(16),
                                      bottomLeft: Radius.circular(16),
                                      bottomRight: Radius.circular(16),
                                    ),
                                  ),
                                  child: Padding(
                                    padding: const EdgeInsets.all(16),
                                    child: VoilaRichSummaryView(
                                      text: displayContent,
                                      isDark: isDark,
                                      primaryTextColor: isError ? const Color(0xFFEF4444) : AppTokens.textPrimary(isDark),
                                    ),
                                  ),
                                ),
                              ),
                            )
                          // Dedicated Authentic Terminal Card for SHELL commands
                          : ConstrainedBox(
                              constraints: BoxConstraints(
                                maxWidth: screenWidth * 0.94,
                              ),
                              child: ShellOutputCard(
                                message: message,
                                isDark: isDark,
                              ),
                            )),
                ],
              ),
            ),
    );
  }

  Widget _buildBgTasksSidebar() {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    // The backend already sorts newest-first. Do not reverse it.
    final displayTasks = _getMergedTasks().take(50).toList();
    
    return Drawer(
      backgroundColor: AppTokens.bg(isDark),
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: AppTokens.border(isDark))),
              ),
              child: Row(
                children: [
                  const Icon(Icons.memory_rounded, color: AppTokens.accentSecondary),
                  const SizedBox(width: 12),
                  Text('BACKGROUND TASKS', style: GoogleFonts.spaceGrotesk(color: AppTokens.textPrimary(isDark), fontSize: 16, fontWeight: FontWeight.w800, letterSpacing: -0.5)),
                  const Spacer(),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: AppTokens.accentSecondary.withOpacity(0.15),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Text(
                      ' Active',
                      style: GoogleFonts.inter(color: AppTokens.accentSecondary, fontSize: 12, fontWeight: FontWeight.bold),
                    ),
                  ),
                ],
              ),
            ),
            Expanded(
              child: displayTasks.isEmpty
                  ? Center(
                      child: Text(
                        'No background tasks',
                        style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark)),
                      ),
                    )
                  : ListView.separated(
                      padding: const EdgeInsets.all(16),
                      itemCount: displayTasks.length,
                      separatorBuilder: (context, index) => const SizedBox(height: 12),
                      itemBuilder: (context, index) {
                        final task = displayTasks[index];
                        final isRunning = task['status'] == 'running';
                        
                        return InkWell(
                          borderRadius: BorderRadius.circular(16),
                          onTap: () => _showTaskDetailsDialog(Map<String, dynamic>.from(task as Map)),
                          child: Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: AppTokens.cardAlt(isDark),
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(color: isRunning ? AppTokens.accentSecondary.withOpacity(0.5) : AppTokens.border(isDark)),
                            ),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                children: [
                                  Icon(
                                    isRunning ? Icons.play_circle_fill_rounded : Icons.check_circle_rounded,
                                    size: 16,
                                    color: isRunning ? AppTokens.accentSecondary : AppTokens.textSecondary(isDark),
                                  ),
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Text(
                                      task['id'] ?? 'Unknown Task',
                                      style: GoogleFonts.inter(
                                        color: AppTokens.textPrimary(isDark),
                                        fontWeight: FontWeight.bold,
                                        fontSize: 13,
                                      ),
                                    ),
                                  ),
                                  if (isRunning) ...[
                                    GestureDetector(
                                      behavior: HitTestBehavior.opaque,
                                      onTap: () => _killSpecificBgTask(task['id']?.toString() ?? ''),
                                      child: Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                        decoration: BoxDecoration(
                                          color: const Color(0xFFEF4444).withOpacity(0.15),
                                          borderRadius: BorderRadius.circular(8),
                                          border: Border.all(color: const Color(0xFFEF4444)),
                                        ),
                                        child: Row(
                                          mainAxisSize: MainAxisSize.min,
                                          children: [
                                            const Icon(Icons.stop_rounded, size: 12, color: Color(0xFFEF4444)),
                                            const SizedBox(width: 2),
                                            Text(
                                              'KILL',
                                              style: GoogleFonts.spaceGrotesk(
                                                color: const Color(0xFFEF4444),
                                                fontSize: 10,
                                                fontWeight: FontWeight.w800,
                                              ),
                                            ),
                                          ],
                                        ),
                                      ),
                                    ),
                                  ],
                                ],
                              ),
                              if (task['action'] != null) ...[
                                const SizedBox(height: 8),
                                Text(
                                  task['action'],
                                  style: GoogleFonts.inter(
                                    color: AppTokens.textSecondary(isDark),
                                    fontSize: 12,
                                  ),
                                ),
                              ],
                            ],
                          ),
                        ),
                      );
                      },
                    ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInputArea(ColorScheme colorScheme) {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    bool isAgent = _currentMode == 'agent' || _isAssistant;

    if (isAgent) {
      if (_isLiveSession && !_showTextInput) {
        // Voice-only AI Assistant layout (Guardian Robotics style)
        return Container(
          width: double.infinity,
          padding: const EdgeInsets.only(bottom: 40, top: 20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Text(
                _isAiSpeaking ? 'AI is speaking...' : (_isListening ? 'Listening...' : _currentStatus),
                style: GoogleFonts.spaceGrotesk(color: AppTokens.textPrimary(isDark), fontSize: 24, fontWeight: FontWeight.w800, letterSpacing: -0.5),
                textAlign: TextAlign.center,
              ),
              const SizedBox(height: 40),
              // Massive pulsing mic button
            PulseWaveVisualizer(
              isListening: _isListening,
              isSpeaking: _isAiSpeaking,
              onTap: () {
                _stopListening();
                flutterTts.stop();
                if (mounted) setState(() { _isAiSpeaking = false; _isLiveSession = false; _showTextInput = true; });
              },
              ),
            ],
            ),
        );
      }

      // Minimal floating pill input
      return Container(
        margin: EdgeInsets.only(left: _isAssistant ? 0 : 14, right: _isAssistant ? 0 : 14, bottom: _isAssistant ? 2 : 26, top: _isAssistant ? 2 : 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            // Screenshot Camera Button (compact) - only in main app, overlay uses quick chip
            if (!_isAssistant)
              GestureDetector(
                behavior: HitTestBehavior.opaque,
                onTap: () {
                  _controller.text = "__SCREENSHOT__";
                  _sendMessage();
                },
                child: Container(
                  margin: const EdgeInsets.only(bottom: 2, right: 6),
                  padding: const EdgeInsets.all(9),
                  decoration: BoxDecoration(
                    color: AppTokens.cardAlt(isDark),
                    shape: BoxShape.circle,
                    border: Border.all(color: AppTokens.border(isDark)),
                  ),
                  child: Icon(Icons.camera_alt_rounded, color: AppTokens.textSecondary(isDark), size: 18),
                ),
              ),
            
            // Text Input Field (spans full available width)
            Expanded(
              child: Container(
                margin: const EdgeInsets.only(bottom: 2),
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
                decoration: BoxDecoration(
                  color: _isAssistant
                      ? (isDark ? Colors.white.withOpacity(0.06) : Colors.black.withOpacity(0.04))
                      : AppTokens.cardAlt(isDark),
                  borderRadius: BorderRadius.circular(100),
                  border: Border.all(color: isDark ? Colors.white12 : Colors.black12),
                ),
                child: TextField(
                  controller: _controller,
                  minLines: 1,
                  maxLines: 4,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _sendMessage(),
                  onChanged: (_) => setState(() {}),
                  style: GoogleFonts.inter(fontSize: 14, color: AppTokens.textPrimary(isDark), fontWeight: FontWeight.w500),
                  decoration: InputDecoration(
                    hintText: 'Ask me anything...',
                    hintStyle: GoogleFonts.inter(color: AppTokens.textSecondary(isDark), fontSize: 14),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 2, vertical: 10),
                    border: InputBorder.none,
                    isDense: true,
                  ),
                ),
              ),
            ),

            // Send / Mic Button with dynamic listener (compact)
            ValueListenableBuilder<TextEditingValue>(
              valueListenable: _controller,
              builder: (context, val, _) {
                final hasText = val.text.trim().isNotEmpty;
                // In assistant overlay: remove duplicate mic button; only display button if text is entered (Send) or thinking (Stop)
                if (_isAssistant && !hasText && !_isThinking) {
                  return const SizedBox.shrink();
                }

                return Padding(
                  padding: const EdgeInsets.only(left: 6),
                  child: GestureDetector(
                    behavior: HitTestBehavior.opaque,
                    onTap: () {
                      if (_isThinking) {
                        _cancelBackendTask();
                      } else if (hasText) {
                        _sendMessage();
                      } else {
                        setState(() { _isLiveSession = true; _showTextInput = false; });
                        _startListening();
                      }
                    },
                    child: Container(
                      margin: const EdgeInsets.only(bottom: 2),
                      padding: const EdgeInsets.all(9),
                      decoration: BoxDecoration(
                        color: _isThinking
                            ? const Color(0xFFEF4444)
                            : (hasText
                                ? AppTokens.accentSecondary
                                : AppTokens.accent),
                        shape: BoxShape.circle,
                        boxShadow: [
                          BoxShadow(
                            color: (_isThinking ? const Color(0xFFEF4444) : (hasText ? AppTokens.accentSecondary : AppTokens.accent)).withOpacity(0.4),
                            blurRadius: 10,
                            offset: const Offset(0, 3),
                          )
                        ],
                      ),
                      child: Icon(
                        _isThinking 
                            ? Icons.stop_rounded 
                            : (hasText 
                                ? Icons.send_rounded 
                                : Icons.mic_rounded),
                        color: hasText ? const Color(0xFF09090B) : Colors.white,
                        size: 18,
                      ),
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      );
    }
    
    // SHELL mode (keeps compact bento structure)
    return Container(
      margin: const EdgeInsets.only(left: 16, right: 16, bottom: 24, top: 8),
      decoration: AppTokens.bentoBox(isDark, radius: 24),
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Container(
                margin: const EdgeInsets.only(bottom: 2),
                decoration: BoxDecoration(
                  color: AppTokens.cardAlt(isDark),
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: AppTokens.border(isDark)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _controller,
                        minLines: 1,
                        maxLines: 4,
                        textInputAction: TextInputAction.send,
                        onSubmitted: (_) => _sendMessage(),
                        onChanged: (_) => setState(() {}),
                        style: GoogleFonts.inter(fontSize: 14, color: AppTokens.textPrimary(isDark)),
                        decoration: InputDecoration(
                          hintText: _isListening ? 'Listening...' : 'Enter shell command...',
                          hintStyle: GoogleFonts.inter(color: AppTokens.textSecondary(isDark)),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                          border: InputBorder.none,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 6),
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: () {
                _controller.text = "__SCREENSHOT__";
                _sendMessage();
              },
              child: Container(
                padding: const EdgeInsets.all(9),
                margin: const EdgeInsets.only(bottom: 2),
                decoration: BoxDecoration(
                  color: AppTokens.cardAlt(isDark),
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.camera_alt_rounded, color: AppTokens.textSecondary(isDark), size: 18),
              ),
            ),
            const SizedBox(width: 6),
            GestureDetector(
              behavior: HitTestBehavior.opaque,
              onTap: _sendMessage,
              child: Container(
                padding: const EdgeInsets.all(9),
                margin: const EdgeInsets.only(bottom: 2),
                decoration: const BoxDecoration(
                  color: AppTokens.accent,
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.send_rounded, color: Colors.white, size: 18),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTaskWorkflow(ColorScheme colorScheme) {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    bool isAgent = _currentMode.toUpperCase() == 'AGENT';
    
    // Only show in Agent mode
    if (!isAgent) return const SizedBox.shrink();

    // Use the helper to merge HTTP polling tasks with Real-time WebSocket job_status
    List<dynamic> allTasks = _getMergedTasks();
    
    // Filter out completed tasks so the flowchart disappears when idle
    final activeTasks = allTasks.where((t) {
      final status = t['status']?.toString().toLowerCase() ?? '';
      return status == 'running' || status == 'queued' || status == 'cancelling';
    }).toList();

    // Get up to 4 most recent active tasks for the workflow visualization
    final workflowTasks = activeTasks.reversed.take(4).toList().reversed.toList();
    if (workflowTasks.isEmpty) return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.only(left: 20, right: 20, bottom: 12),
      height: 65,
      child: Center(
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          shrinkWrap: true,
          itemCount: workflowTasks.length,
          itemBuilder: (context, index) {
            final task = workflowTasks[index];
            final isRunning = task['status'] == 'running';
            final isDone = task['status'] == 'completed' || task['status'] == 'done';
            final isFailed = task['status'] == 'failed' || task['status'] == 'error';
            
            Color nodeColor = AppTokens.border(isDark);
            if (isRunning) nodeColor = AppTokens.accentSecondary;
            else if (isDone) nodeColor = const Color(0xFF10B981);
            else if (isFailed) nodeColor = const Color(0xFFEF4444);

            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 24,
                      height: 24,
                      decoration: BoxDecoration(
                        color: isRunning ? nodeColor.withOpacity(0.15) : Colors.transparent,
                        shape: BoxShape.circle,
                        border: Border.all(color: isRunning || isDone || isFailed ? nodeColor : AppTokens.border(isDark), width: isRunning ? 2 : 1.5),
                      ),
                      child: Center(
                        child: isDone
                            ? Icon(Icons.check_rounded, size: 14, color: nodeColor)
                            : (isFailed
                                ? Icon(Icons.close_rounded, size: 14, color: nodeColor)
                                : (isRunning
                                    ? SizedBox(width: 10, height: 10, child: CircularProgressIndicator(color: nodeColor, strokeWidth: 2))
                                    : Icon(Icons.circle, size: 8, color: nodeColor))),
                      ),
                    ),
                    const SizedBox(height: 6),
                    SizedBox(
                      width: 70,
                      child: Text(
                        task['action'] ?? task['id'] ?? 'Task',
                        style: GoogleFonts.inter(
                          color: isRunning ? AppTokens.textPrimary(isDark) : AppTokens.textSecondary(isDark),
                          fontSize: 9,
                          fontWeight: isRunning ? FontWeight.w700 : FontWeight.w500,
                        ),
                        textAlign: TextAlign.center,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
                if (index < workflowTasks.length - 1)
                  Container(
                    width: 30,
                    height: 2,
                    margin: const EdgeInsets.only(top: 11),
                    color: (isDone || isFailed) ? nodeColor.withOpacity(0.5) : AppTokens.border(isDark),
                  ),
              ],
            );
          },
        ),
      ),
    );
  }

  Future<void> _showApprovalDialog(Map<String, dynamic> data) async {
    final jobId = data['job_id'] ?? '';
    final riskLevel = data['risk_level'] ?? 'high';
    final actionType = data['action_type'] ?? 'unknown';
    final summary = data['summary'] ?? 'Unknown action';
    final detail = data['detail'] ?? summary;
    final reason = data['reason'] ?? 'Flagged by security policy';
    final windowTitle = data['window'] ?? '';
    final controlName = data['control_name'] ?? '';

    Color riskColor = Colors.orangeAccent;
    if (riskLevel.toString().toLowerCase() == 'critical') {
      riskColor = Colors.redAccent;
    } else if (riskLevel.toString().toLowerCase() == 'medium') {
      riskColor = Colors.yellowAccent;
    }

    String targetText = windowTitle;
    if (controlName.isNotEmpty) targetText += ' > $controlName';
    if (targetText.isEmpty) targetText = 'N/A';

    bool? approved = await showDialog<bool>(
      context: context,
      barrierDismissible: false,
      builder: (BuildContext context) {
        return AlertDialog(
          backgroundColor: const Color(0xFF1E1E24),
          title: Row(
            children: const [
              Icon(Icons.security, color: Colors.white),
              SizedBox(width: 10),
              Expanded(child: Text('Security Permission', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 18))),
            ],
          ),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                RichText(text: TextSpan(children: [
                  const TextSpan(text: 'Risk Level: ', style: TextStyle(color: Colors.white70, fontWeight: FontWeight.bold)),
                  TextSpan(text: riskLevel.toString().toUpperCase(), style: TextStyle(color: riskColor, fontWeight: FontWeight.bold)),
                ])),
                const SizedBox(height: 8),
                RichText(text: TextSpan(children: [
                  const TextSpan(text: 'Action: ', style: TextStyle(color: Colors.white70, fontWeight: FontWeight.bold)),
                  TextSpan(text: actionType, style: const TextStyle(color: Colors.white)),
                ])),
                const SizedBox(height: 8),
                RichText(text: TextSpan(children: [
                  const TextSpan(text: 'Target: ', style: TextStyle(color: Colors.white70, fontWeight: FontWeight.bold)),
                  TextSpan(text: targetText, style: const TextStyle(color: Colors.white)),
                ])),
                const SizedBox(height: 12),
                const Text('Why blocked:', style: TextStyle(color: Colors.white70, fontWeight: FontWeight.bold)),
                Text(reason, style: const TextStyle(color: Colors.white)),
                const SizedBox(height: 12),
                const Text('Detail:', style: TextStyle(color: Colors.white70, fontWeight: FontWeight.bold)),
                Text(detail, style: const TextStyle(color: Colors.white54, fontSize: 12)),
              ],
            ),
          ),
          actions: <Widget>[
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('DENY', style: TextStyle(color: Colors.white70)),
            ),
            ElevatedButton(
              style: ElevatedButton.styleFrom(backgroundColor: riskColor.withOpacity(0.2)),
              onPressed: () => Navigator.of(context).pop(true),
              child: Text('ALLOW ONCE', style: TextStyle(color: riskColor, fontWeight: FontWeight.bold)),
            ),
          ],
        );
      },
    );

    if (approved != null) {
      _channel?.sink.add(jsonEncode({
        'type': 'approve_job',
        'job_id': jobId,
        'approved': approved,
        'session_token': _sessionToken,
      }));
    }
  }
}

class CollapsibleOutput extends StatefulWidget {
  final String text;
  final TextStyle style;
  final bool isCodeBlock;

  const CollapsibleOutput({super.key, required this.text, required this.style, this.isCodeBlock = false});

  @override
  State<CollapsibleOutput> createState() => _CollapsibleOutputState();
}

class _CollapsibleOutputState extends State<CollapsibleOutput> {
  bool _isExpanded = false;

  @override
  Widget build(BuildContext context) {
    final lines = widget.text.split('\n');
    final isLong = lines.length > 10;
    final displayText = (!_isExpanded && isLong) ? lines.take(10).join('\n') + '\n...' : widget.text;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        widget.isCodeBlock
            ? SizedBox(
                width: double.infinity,
                child: SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: SelectableText(
                    displayText,
                    style: widget.style,
                  ),
                ),
              )
            : SelectableText(
                displayText,
                style: widget.style,
              ),
        if (isLong)
          GestureDetector(
            onTap: () {
              if (mounted) setState(() { _isExpanded = !_isExpanded; });
            },
            child: Container(
              margin: const EdgeInsets.only(top: 8),
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.white.withOpacity(0.05),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Text(
                _isExpanded ? 'Show less' : 'Show more',
                style: const TextStyle(color: Colors.white70, fontSize: 11, fontWeight: FontWeight.w500),
              ),
            ),
          ),
      ],
    );
  }

}






