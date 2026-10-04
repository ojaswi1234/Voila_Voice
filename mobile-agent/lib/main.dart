import 'dart:async';  // unawaited(), StreamSubscription, Timer
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

import 'dart:convert';
import 'dart:io';
import 'package:flutter/foundation.dart'; // For compute()
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'dart:ui';
import 'crypto.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:speech_to_text/speech_to_text.dart';
import 'package:flutter_tts/flutter_tts.dart';
import 'package:permission_handler/permission_handler.dart';
import 'device_identity.dart';
import 'artifacts_page.dart';
import 'visualizer.dart';
import 'package:uuid/uuid.dart';

import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:flutter_background/flutter_background.dart';
import 'connection_flowchart.dart';
import 'package:audioplayers/audioplayers.dart';
import 'package:path_provider/path_provider.dart';
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

class AppTokens {
  static const Color accent = Color(0xFFFF4500); // Blazing Orange / Coral
  static const Color accentSecondary = Color(0xFF00E5FF); // Electric Cyan
  
  static Color bg(bool isDark) => isDark ? const Color(0xFF09090B) : const Color(0xFFF4F4F5);
  static Color card(bool isDark) => isDark ? const Color(0xFF18181B) : Colors.white;
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
  // BUGFIX: Guard against duplicate-app exception if the engine is shared
  // and main() is somehow re-invoked (e.g., background isolate or cold-start via AssistantActivity)
  if (Firebase.apps.isEmpty) {
    await Firebase.initializeApp();
  }
  FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);
  
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
  final _storage = const FlutterSecureStorage();
  List<String> _modelsList = [];
  String _selectedModel = '';
  bool _isFetchingModels = false;
  String _cachedSecurityPhrase = '';
  final List<Map<String, dynamic>> _messagesShell = [];
  final List<Map<String, dynamic>> _messagesAgent = [];
  List<Map<String, dynamic>> get _messages => _currentMode.toUpperCase() == 'AGENT' ? _messagesAgent : _messagesShell;
  bool _isThinking = false;
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
    if (msg['type'] == 'error') {
      HapticFeedback.heavyImpact();
    }
    if (_currentMode.toUpperCase() == 'AGENT') {
      _messagesAgent.add(msg);
      if (_messagesAgent.length > 200) _messagesAgent.removeAt(0);
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
  List<Map<String, dynamic>> _securityAlerts = [];
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

  @override

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
        ArtifactsManager.addArtifact(
          title: title,
          content: (artifactPath != null && artifactPath.isNotEmpty) ? artifactPath : summary,
          source: 'fcm_task_finished',
        );
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
        
        ArtifactsManager.addArtifact(
          title: title,
          content: (artifactPath != null && artifactPath.isNotEmpty) ? artifactPath : summary,
          source: 'fcm_task_finished',
        );

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
        ArtifactsManager.addArtifact(
          title: title,
          content: (artifactPath != null && artifactPath.isNotEmpty) ? artifactPath : summary,
          source: 'fcm_task_finished',
        );
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

  Future<void> _initBackground() async {
    if (!Platform.isAndroid) return;  // BUG-25 fix: flutter_background is Android-only
    try {
      const androidConfig = FlutterBackgroundAndroidConfig(
        notificationTitle: "Voila Live Active",
        notificationText: "Maintaining connection in the background...",
        notificationImportance: AndroidNotificationImportance.normal,
        notificationIcon: AndroidResource(name: 'ic_launcher', defType: 'mipmap'),
      );
      await FlutterBackground.initialize(androidConfig: androidConfig);
      await FlutterBackground.enableBackgroundExecution();
    } catch (e) {
      debugPrint('Background execution error: $e');
    }
  }


  void _fetchConversations() {
    if (_channel != null && _isConnected) {
      final msg = jsonEncode({
        "type": "get_conversations",
        "device_id": _activeDevice,
        "session_token": _sessionToken
      });
      _channel?.sink.add(msg);
    }
  }
  
  void _startNewConversation() {
    if (mounted) setState(() {
      _currentConversationId = '';
      _messagesAgent.clear();
      _messagesAgent.insert(0, {'text': 'Started a new conversation.', 'isUser': false});
    });
    Navigator.pop(context); // close drawer
  }
  
  void _resumeConversation(String id, String title) {
    if (mounted) setState(() {
      _currentConversationId = id;
      _messagesAgent.clear();
      _messagesAgent.insert(0, {'text': 'Resumed conversation: ', 'isUser': false});
    });
    Navigator.pop(context); // close drawer
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

  void _toggleListening() async {
    if (!_speechInitialized) {
      await _initializeSpeech();
    }
    
    if (!_speechAvailable) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Speech recognition not available on this device')),
        );
      }
      return;
    }
    
    if (_isListening) {
      await _stopListening();
    } else {
      await _startListening();
    }
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
            String finalWords = _normalizeGenZSlang(result.recognizedWords);
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
              _controller.text = _previousDictationText + _normalizeGenZSlang(result.recognizedWords);
            });
          }
        },
        onSoundLevelChange: (level) {
          if (mounted) setState(() {
            _currentSoundLevel = level;
          });
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
      };
      _channel?.sink.add(jsonEncode(message));
      
      if (mounted) setState(() {
        _isThinking = false; _triggerDataArriving();
        _addMessage({
          'type': 'system',
          'content': 'Cancellation signal sent to local agent (ESC pressed).',
          'timestamp': DateTime.now().toString(),
        });
      });
      _scrollToBottom();
    }
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
              if (payload is Map && payload['encrypted'] != null) {
                 final String phrase = _cachedSecurityPhrase;
                 String dec = CryptoUtils.decrypt(payload['encrypted'], phrase);
                 try {
                   parsedData = await compute(parseJsonListInBackground, dec);
                 } catch(e) {}
              } else if (payload is List) {
                 parsedData = payload;
              }
              if (mounted) setState(() {  // BUG-08 fix: safe cast handles non-String JSON values
                _conversations = parsedData.map((x) {
                  try {
                    return Map<String, String>.from(
                      (x as Map).map((k, v) => MapEntry(k.toString(), v?.toString() ?? '')));
                  } catch (_) { return <String, String>{}; }
                }).where((m) => m.isNotEmpty).toList();
              });
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
                  }
                });
              }
              return;
            } else if (jsonResponse is Map && jsonResponse['type'] == 'queued') {
              // Task queued! Keep loader spinning.
              return;
            } else if (jsonResponse is Map && jsonResponse.containsKey('summary')) {
              if (jsonResponse['mode'] != 'screenshot') {
                if (mounted) setState(() {
                  _isThinking = false; _triggerDataArriving();
                });
              } else {
                setState(() { _triggerDataArriving(); });
              }
              
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

              final contentStr = jsonResponse['output'] ?? message;
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
          _isConnected = false;
          _addMessage({
            'type': 'error',
            'content': 'Connection error: $error',
            'timestamp': DateTime.now().toString(),
          });
        });
      }, onDone: () {
        if (mounted) setState(() {  // BUG-11 fix
          _isConnected = false;
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
        _isConnected = false;
        _addMessage({
          'type': 'error',
          'content': 'Failed to connect: $e',
          'timestamp': DateTime.now().toString(),
        });
      });
    }
  }

  void _startBgTaskChecks() {
    _bgTaskTimer = Timer.periodic(const Duration(seconds: 3), (_) {
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
        final healthData = jsonDecode(response.body);
        
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
      // HIDDEN BUG FIX: Do NOT call _checkIntent() here unconditionally.
      // The shared engine's MethodChannel handler may still be set to
      // AssistantActivity's version (returning isAssistantIntent=true)
      // even when we are back in MainActivity context, causing the full
      // app to permanently render in overlay mode.
      //
      // Instead: the onIntentChanged push from MainActivity.onResume() (Kotlin)
      // is the authoritative signal. We only call _checkIntent() as a fallback
      // if we are currently NOT in assistant mode (initial boot validation).
      if (!_isAssistant) {
        _checkIntent();
      }
    } else if (state == AppLifecycleState.paused) {
      // When the app is paused (going to background), the overlay may be
      // taking over. Do not change _isAssistant here; wait for onIntentChanged.
    }
  }


  void _stopCommand() {
    if (_channel != null && _isConnected) {
      _channel?.sink.add(jsonEncode({"type": "stop_command"}));
      if (mounted) setState(() {
        _isThinking = false; _triggerDataArriving();
        _addMessage({
          'type': 'response',
          'content': 'Execution stopped by user.',
          'timestamp': DateTime.now().toString(),
        });
      });
    }
  }

  void _fetchModels() {
    if (_channel != null && _isConnected) {
      if (mounted) setState(() => _isFetchingModels = true);
      _channel?.sink.add(jsonEncode({
        "type": "get_models",
        "device_id": _activeDevice,
        "session_token": _sessionToken
      }));
    }
  }

  void _showModelSelector() {
    if (_modelsList.isEmpty) {
      _fetchModels();
    }
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1E1E1E),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return Container(
              padding: const EdgeInsets.symmetric(vertical: 20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('Select AI Model', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
                  const SizedBox(height: 10),
                  if (_modelsList.isEmpty) 
                    const Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator())
                  else
                    SizedBox(  // BUG-23 fix: Expanded inside mainAxisSize.min crashes - use SizedBox
                      height: 300,
                      child: ListView.builder(
                        itemCount: _modelsList.length,
                        itemBuilder: (context, index) {
                          final model = _modelsList[index];
                          return ListTile(
                            title: Text(model, style: const TextStyle(color: Colors.white70)),
                            trailing: _selectedModel == model ? const Icon(Icons.check, color: Colors.greenAccent) : null,
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
            );
          },
        );
      },
    );
  }
  void _sendMessage() async {
    if (_controller.text.isNotEmpty) {
      if (!_isConnected) {
        if (mounted) setState(() {
          _addMessage({
            'type': 'error',
            'content': 'Not connected to backend. Please wait for reconnection.',
            'timestamp': DateTime.now().toString(),
          });
        });
        _scrollToBottom();
        return;
      }
      
      if (_activeDevice.isEmpty) {
        if (mounted) setState(() {
          _addMessage({
            'type': 'error',
            'content': 'No online desktop device selected. Please wait for devices to load or refresh.',
            'timestamp': DateTime.now().toString(),
          });
        });
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('⚠️ Please connect your Desktop to use Voila AI.')),
          );
        }
        _controller.clear();
        _scrollToBottom();
        return;
      }
      
      // Validate that selected device is actually a desktop device
      if (!_activeDevice.startsWith('desktop-')) {
        if (mounted) setState(() {
          _addMessage({
            'type': 'error',
            'content': 'Invalid device selected: $_activeDevice. Expected desktop- device.',
            'timestamp': DateTime.now().toString(),
          });
        });
        _controller.clear();
        _scrollToBottom();
        return;
      }
      
      final deviceInfo = await DeviceIdentity.getDeviceInfo();
      if (!mounted) return;  // BUG-05 fix
      
      // Check session validity before sending
      if (!_isSessionValid()) {
        setState(() {
          _addMessage({
            'type': 'error',
            'content': 'Session expired - unlock to continue',
            'timestamp': DateTime.now().toString(),
          });
        });
        _controller.clear();
        _scrollToBottom();
        
        // Show unlock dialog
        if (mounted) {
          showDialog(
            context: context,
            builder: (context) => AlertDialog(
              title: const Text('Session Expired'),
              content: const Text('Your session has expired. Please unlock to continue sending commands.'),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context),
                  child: const Text('Cancel'),
                ),
                TextButton(
                  onPressed: () {
                    Navigator.pop(context);
                    _ensureUnlocked();
                  },
                  child: const Text('Unlock'),
                ),
              ],
            ),
          );
        }
        return;
      }
      
      if (!await _ensureUnlocked()) return;

      final message = {
        ...deviceInfo,
        'type': 'command',
        'device_id': _activeDevice,
        'client_device_id': _currentDeviceId,
        'client_device_name': _currentDeviceName,
        'session_id': _sessionId,
        'session_token': _sessionToken,
        'command': _controller.text,
        'mode': _currentMode,
        'graphify_enabled': _graphifyEnabled,
        'idempotency_key': const Uuid().v4(),
        'client_timestamp': DateTime.now().millisecondsSinceEpoch,
      };
      
      debugPrint('Sending command to device: $_activeDevice');
      debugPrint('Message: $message');
      
      _channel?.sink.add(jsonEncode(message));
      if (mounted) setState(() {
        if (_controller.text != '__SCREENSHOT__') {
          _isThinking = true;
          _triggerDataDeparting();
        }
        _addMessage({
          'type': 'user',
          'content': _controller.text == '__SCREENSHOT__' ? '📸 Taking screenshot...' : _controller.text,
          'timestamp': DateTime.now().toString(),
        });
      });
      _controller.clear();
      _scrollToBottom();
    }
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

  void _showSecurityAlerts() {
    FocusScope.of(context).unfocus();
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1E1E1E),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      isScrollControlled: true,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return DraggableScrollableSheet(
              expand: false,
              initialChildSize: 0.6,
              minChildSize: 0.3,
              maxChildSize: 0.9,
              builder: (_, scrollController) => Container(  // BUG-22 fix: use DraggableScrollableSheet instead of mainAxisSize.min+Expanded
              padding: const EdgeInsets.all(20),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('Security Alerts', style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, color: Colors.white)),
                      Row(
                        children: [
                          if (_securityAlerts.isNotEmpty)
                            IconButton(
                              icon: const Icon(Icons.delete_sweep, size: 18),
                              onPressed: () {
                                if (mounted) setState(() {
                                  _securityAlerts.clear();
                                });
                                setModalState(() {});
                              },
                            ),
                          IconButton(
                            icon: const Icon(Icons.refresh, size: 18),
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
                  const Divider(height: 20),
                  // Circuit breaker reset button
                  ElevatedButton.icon(
                    onPressed: _resetCircuitBreaker,
                    icon: const Icon(Icons.power_settings_new, size: 16),
                    label: const Text('Reset Circuit Breaker'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.orange.withOpacity(0.2),
                      foregroundColor: Colors.orange,
                    ),
                  ),
                  const SizedBox(height: 10),
                  if (_securityAlerts.isEmpty)
                    const Padding(
                      padding: EdgeInsets.all(20),
                      child: Text('No security alerts', style: TextStyle(color: Colors.white70)),
                    )
                  else
                    Expanded(
                      child: ListView.builder(
                        shrinkWrap: true,
                        itemCount: _securityAlerts.length,
                        itemBuilder: (context, index) {
                          final alert = _securityAlerts[index];
                          final timestamp = alert['timestamp']?.toString() ?? 'Unknown';
                          final type = alert['type']?.toString() ?? 'Unknown';
                          final severity = alert['severity']?.toString() ?? 'low';
                          final ip = alert['ip']?.toString() ?? 'Unknown';
                          final device = alert['device_id']?.toString() ?? 'Unknown';
                          final detail = alert['detail']?.toString() ?? '';
                          
                          return Card(
                            color: _getSeverityColor(severity).withOpacity(0.1),
                            margin: const EdgeInsets.only(bottom: 8),
                            child: ListTile(
                              leading: Icon(
                                _getSeverityIcon(severity),
                                color: _getSeverityColor(severity),
                                size: 20,
                              ),
                              title: Text(
                                type,
                                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w500),
                              ),
                              subtitle: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(timestamp, style: const TextStyle(color: Colors.white60, fontSize: 12)),
                                  Text('IP: $ip', style: const TextStyle(color: Colors.white60, fontSize: 12)),
                                  if (device != 'Unknown') Text('Device: $device', style: const TextStyle(color: Colors.white60, fontSize: 12)),
                                  if (detail.isNotEmpty) Text(detail, style: const TextStyle(color: Colors.white60, fontSize: 12), maxLines: 2, overflow: TextOverflow.ellipsis),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
                    ),
                ],
              ),
            ));  // BUG-22b fix: close DraggableScrollableSheet
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

  @override

  Widget _buildDrawer() {
    final colorScheme = Theme.of(context).colorScheme;
    return Drawer(
      backgroundColor: const Color(0xFF131316),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.only(top: 60, bottom: 20, left: 20, right: 20),
            color: const Color(0xFF1A1A1F),
            child: Row(
              children: [
                const Icon(Icons.mic, color: Colors.blueAccent, size: 28),
                const SizedBox(width: 12),
                const Text('Voila Voice', style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold, letterSpacing: -0.5)),
                const Spacer(),
                if (_currentMode.toUpperCase() == 'AGENT')
                  IconButton(
                    icon: const Icon(Icons.refresh, color: Colors.white54),
                    onPressed: _fetchConversations,
                  )
              ],
            ),
          ),
          
          Expanded(
            child: ListView(
              padding: const EdgeInsets.symmetric(vertical: 8),
              children: [
                if (_currentMode.toUpperCase() == 'AGENT') ...[
                  ListTile(
                    leading: const Icon(Icons.add_circle_outline, color: Colors.blueAccent),
                    title: const Text('New Conversation', style: TextStyle(color: Colors.white, fontWeight: FontWeight.w600)),
                    onTap: () {
                      Navigator.pop(context);
                      _startNewConversation();
                    },
                  ),
                  const Padding(
                    padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                    child: Divider(color: Colors.white12),
                  ),
                ],
                
                _buildDrawerItem(Icons.folder_copy_outlined, 'Artifacts', () {
                  Navigator.pop(context);
                  Navigator.push(context, MaterialPageRoute(builder: (context) => const ArtifactsPage()));
                }),
                _buildDrawerItem(Icons.security_outlined, 'Security Alerts', () {
                  Navigator.pop(context);
                  _showSecurityAlerts();
                }),
                _buildDrawerItem(Icons.settings_outlined, 'Settings', () {
                  Navigator.pop(context);
                  _showSettingsSheet(context);
                }),
                _buildDrawerItem(Icons.no_photography_outlined, 'Clear Screenshots', () {
                  if (mounted) setState(() {
                    _messages.removeWhere((m) => (m['content'] as String? ?? '').startsWith('__IMAGE__:'));
                  });
                  Navigator.pop(context);
                }),
                
                const Padding(
                  padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Divider(color: Colors.white12),
                ),
                
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                  child: Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: _isSessionValid() 
                        ? (_isSessionExpiringSoon() ? Colors.orange.withOpacity(0.1) : Colors.green.withOpacity(0.1))
                        : Colors.red.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(
                        color: _isSessionValid() 
                          ? (_isSessionExpiringSoon() ? Colors.orange.withOpacity(0.5) : Colors.green.withOpacity(0.5))
                          : Colors.red.withOpacity(0.5),
                      ),
                    ),
                    child: Row(
                      children: [
                        Icon(
                          _isSessionValid() ? Icons.lock_open : Icons.lock,
                          size: 18,
                          color: _isSessionValid() 
                            ? (_isSessionExpiringSoon() ? Colors.orange : Colors.green)
                            : Colors.red,
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              const Text('Session Status', style: TextStyle(color: Colors.white70, fontSize: 12)),
                              const SizedBox(height: 2),
                              Text(
                                _getSessionStatusText(),
                                style: TextStyle(
                                  color: _isSessionValid() 
                                    ? (_isSessionExpiringSoon() ? Colors.orange : Colors.green)
                                    : Colors.red,
                                  fontWeight: FontWeight.bold,
                                  fontSize: 14,
                                ),
                              ),
                            ],
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                
                if (_currentMode.toUpperCase() == 'AGENT' && _conversations.isNotEmpty) ...[
                  const Padding(
                    padding: EdgeInsets.only(left: 20, top: 16, bottom: 8),
                    child: Text('RECENT CHATS', style: TextStyle(color: Colors.white38, fontSize: 11, fontWeight: FontWeight.bold, letterSpacing: 1.2)),
                  ),
                  ..._conversations.map((conv) {
                    final isSelected = _currentConversationId == conv['id'];
                    return ListTile(
                      dense: true,
                      contentPadding: const EdgeInsets.symmetric(horizontal: 20),
                      tileColor: isSelected ? colorScheme.primary.withOpacity(0.15) : null,
                      leading: Icon(Icons.chat_bubble_outline, size: 18, color: isSelected ? colorScheme.primary : Colors.white54),
                      title: Text(
                        conv['title'] ?? 'Unknown', 
                        style: TextStyle(
                          color: isSelected ? Colors.white : Colors.white70,
                          fontWeight: isSelected ? FontWeight.w600 : FontWeight.normal,
                          fontSize: 14,
                        ),
                        maxLines: 1,
                        overflow: TextOverflow.ellipsis,
                      ),
                      onTap: () {
                        Navigator.pop(context);
                        _resumeConversation(conv['id']!, conv['title']!);
                      },
                    );
                  }).toList(),
                ],
              ],
            ),
          ),
        ],
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    
    return Scaffold(
      // BUG FIX A: In overlay mode the Drawer wraps the entire screen in an
      // invisible GestureDetector (to detect swipe-open gestures). This full-screen
      // touch absorber intercepts ALL taps, making every button unclickable.
      // Solution: disable the drawer completely when in assistant overlay mode.
      drawer: _isAssistant ? null : _buildDrawer(),
      endDrawer: _buildBgTasksSidebar(),
      backgroundColor: _isAssistant ? Colors.transparent : AppTokens.bg(appThemeMode.value == ThemeMode.dark),
      body: _isAssistant
        // BUG FIX B+C: The previous LayoutBuilder+SingleChildScrollView placed
        // content at the TOP of a full-screen scroll area, but rendered it visually
        // at the bottom - hit-test coordinates were completely mismatched so
        // all button taps missed their targets.
        //
        // Fix: Stack + Positioned(bottom:0) correctly anchors BOTH the visual
        // rendering AND the hit-test region to the bottom of the screen.
        // No scroll view needed - overlay content is always compact.
        ? Stack(
            children: [
              Positioned(
                bottom: 0,
                left: 0,
                right: 0,
                child: _buildMainContent(colorScheme),
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

  Widget _buildMainContent(ColorScheme colorScheme) {
    if (_isAssistant) {
      // Sleek minimal overlay for Assistant Mode
      return Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          if (_temporaryAssistantImage != null)
            GestureDetector(
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
                          child: Image.memory((() { try { return base64Decode(_temporaryAssistantImage!); } catch(_) { return Uint8List(0); } })(),
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
                margin: const EdgeInsets.only(left: 16, right: 16, top: 8),
                padding: const EdgeInsets.all(8),
                constraints: const BoxConstraints(maxHeight: 250),
                decoration: BoxDecoration(
                  color: AppTokens.card(appThemeMode.value == ThemeMode.dark).withOpacity(0.85),
                  borderRadius: BorderRadius.circular(24),
                  border: Border.all(color: Colors.white.withOpacity(0.05)),
                ),
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(16),
                  child: Image.memory((() { try { return base64Decode(_temporaryAssistantImage!); } catch(_) { return Uint8List(0); } })(),
                    fit: BoxFit.contain,
                    errorBuilder: (c, e, s) => const Text('Image Error', style: TextStyle(color: Colors.red)),
                  ),
                ),
              ),
            ),
          _buildSubtitleOverlay(colorScheme, true), // OVERLAY STYLE SUBTITLES
          // Flowchart with a subtle dark background pill for readability over random desktop walls
          Container(
            margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: AppTokens.card(appThemeMode.value == ThemeMode.dark).withOpacity(0.85),
              borderRadius: BorderRadius.circular(24),
              border: Border.all(color: Colors.white.withOpacity(0.05)),
            ),
            child: ConnectionFlowchart(
              isBackendConnected: _isHealthy,
              isLocalAgentConnected: _localAgentConnected,
              isWebSocketConnected: _isConnected,
              isDataDeparting: _isDataDeparting,
              isDataArriving: _isDataArriving,
              activeDeviceName: _activeDevice.isNotEmpty ? (_devices[_activeDevice]?['name'] ?? 'Desktop') : null,
            ),
          ),
          // We ensure _currentMode is forced to agent in Assistant view, but it should be default
          _buildInputArea(colorScheme),
        ],
      );
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
              Builder(
                builder: (BuildContext ctx) => IconButton(
                  icon: Icon(Icons.menu_rounded, size: 22, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
                  onPressed: () => Scaffold.of(ctx).openDrawer(),
                ),
              ),
              Text(
                'VOILA VOICE',
                style: GoogleFonts.spaceGrotesk(fontSize: 22, fontWeight: FontWeight.w800, letterSpacing: -1.0, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
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
                  appThemeMode.value = appThemeMode.value == ThemeMode.dark ? ThemeMode.light : ThemeMode.dark;
                },
              ),
              const SizedBox(width: 4),
              GestureDetector(
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
                      Text(
                        _activeDevice.isEmpty ? 'Select Device' : (_devices[_activeDevice]?['name'] ?? 'Desktop'),
                        style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.w500, color: AppTokens.textPrimary(appThemeMode.value == ThemeMode.dark)),
                      ),
                      const SizedBox(width: 4),
                      Icon(Icons.keyboard_arrow_down_rounded, size: 14, color: AppTokens.textSecondary(appThemeMode.value == ThemeMode.dark)),
                    ],
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
                  children: [
                    Expanded(
                      child: _buildModeToggle(colorScheme),
                    ),
                    AnimatedSize(
                      duration: const Duration(milliseconds: 350),
                      curve: Curves.easeInOutCubic,
                      child: _bgTasks.isEmpty ? const SizedBox.shrink() :
                        Builder(
                          builder: (BuildContext ctx) {
                            int runningCount = _bgTasks.where((t) => t['status'] == 'running').length;
                            return GestureDetector(
                              onTap: () => Scaffold.of(ctx).openEndDrawer(),
                              child: Container(
                                margin: const EdgeInsets.only(left: 12),
                                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                                decoration: BoxDecoration(
                                  color: runningCount > 0 ? const Color(0xFF0F766E).withOpacity(0.4) : const Color(0xFF222222).withOpacity(0.5),
                                  borderRadius: BorderRadius.circular(100),
                                  border: Border.all(color: runningCount > 0 ? const Color(0xFF14B8A6).withOpacity(0.5) : Colors.white24),
                                ),
                                child: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Icon(Icons.memory, size: 16, color: runningCount > 0 ? const Color(0xFF2DD4BF) : Colors.white54),
                                    if (runningCount > 0) ...[
                                      const SizedBox(width: 6),
                                      Text(' RUNNING', style: const TextStyle(color: Color(0xFF5EEAD4), fontSize: 11, fontWeight: FontWeight.bold)),
                                    ]
                                  ],
                                ),
                              ),
                            );
                          }
                        ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              Expanded(child: _buildMessagesList(colorScheme)),
              
              _buildSubtitleOverlay(colorScheme, true),
              _buildJobStrip(colorScheme),
              _buildInputArea(colorScheme),
            ],
          ),
        ),
      ],
    );
  }

  String _normalizeForSpeech(String text) {
    String normalized = text;
    
    // --- Smart Speech Techniques ---
    // 1. URLs - Aggressively shorten to just "the link" to prevent reading long garbled text
    normalized = normalized.replaceAll(RegExp(r'https?://[^\s)\]]+'), 'the link');
    
    // 2. Windows paths - Aggressively shorten
    normalized = normalized.replaceAll(RegExp(r'[a-zA-Z]:\\[^\s)\]]+'), 'the file path');
    
    // 3. Unix paths
    normalized = normalized.replaceAll(RegExp(r'/(?:[a-zA-Z0-9_.-]+/)+[a-zA-Z0-9_.-]+'), 'the file path');
    
    // 4. UUIDs
    normalized = normalized.replaceAll(RegExp(r'\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b'), 'an ID');
    
    // 5. Long hex hashes (12+ chars like git commits)
    normalized = normalized.replaceAll(RegExp(r'\b[0-9a-fA-F]{12,}\b'), 'a hash');
    // --------------------------------
    
    // Remove Markdown formatting
    normalized = normalized.replaceAll('**', '');
    normalized = normalized.replaceAll('*', '');
    normalized = normalized.replaceAll('__', '');
    normalized = normalized.replaceAll('_', ' ');
    normalized = normalized.replaceAll('`', '');
    normalized = normalized.replaceAll('#', '');
    
    // Replace programming operators
    normalized = normalized.replaceAll('&&', ' and ');
    normalized = normalized.replaceAll('||', ' or ');
    normalized = normalized.replaceAll('!=', ' not equal to ');
    normalized = normalized.replaceAll('==', ' equals ');
    normalized = normalized.replaceAll('>=', ' greater than or equal to ');
    normalized = normalized.replaceAll('<=', ' less than or equal to ');
    
    // Replace standalone symbols
    normalized = normalized.replaceAll(' | ', ' or ');
    normalized = normalized.replaceAll(' + ', ' plus ');
    normalized = normalized.replaceAll(' - ', ' minus ');
    normalized = normalized.replaceAll(' = ', ' equals ');
    normalized = normalized.replaceAll(' < ', ' less than ');
    normalized = normalized.replaceAll(' > ', ' greater than ');
    normalized = normalized.replaceAll('/', ' slash ');
    normalized = normalized.replaceAll('\\', ' backslash ');
    
    // Ensure proper pauses for full stops (add a space if missing to trigger natural sentence break)
    normalized = normalized.replaceAllMapped(RegExp(r'\.([A-Za-z])'), (match) => '. ${match.group(1)}');
    
    // Replace newlines with ellipses to force TTS engines to pause between lines
    normalized = normalized.replaceAll('\n', '. ');
    
    // Clean up extra spaces
    normalized = normalized.replaceAll(RegExp(r'\s+'), ' ').trim();
    
    return normalized;
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
        final RegExp chunkRegex = RegExp(r'([^.?!]+[.?!]*)');
        final Iterable<Match> matches = chunkRegex.allMatches(cleanText);
        
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

      final String ssml = "<speak version='1.0' xmlns='http://www.w3.org/2001/10/synthesis' xml:lang='en-IN'><voice name='en-IN-NeerjaNeural'><prosody pitch='+0Hz' rate='-10%'>$text</prosody></voice></speak>";

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
        await player.play(DeviceFileSource(file.path));
        await player.onPlayerComplete.first;
        return true;
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
              const Text('Settings', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
              const SizedBox(height: 20),
              SwitchListTile(
                title: const Text('Smart Subtitles (AI Speech)', style: TextStyle(fontSize: 14)),
                subtitle: const Text('Show scrolling text when AI speaks'),
                value: _showSubtitles,
                onChanged: (val) {
                  if (mounted) setState(() => _showSubtitles = val);
                  _storage.write(key: 'show_subtitles', value: val.toString());
                  Navigator.pop(context);
                },
                activeColor: const Color(0xFF3DDC97),
                contentPadding: EdgeInsets.zero,
              ),
              _TokenUsageRow(tokenData: _lastTokenUsage),
              SwitchListTile(
                title: const Text('Auto-read Voice Responses', style: TextStyle(fontSize: 14)),
                value: _willTalk,
                activeColor: const Color(0xFF7C6CFF),
                contentPadding: EdgeInsets.zero,
                onChanged: (bool value) {
                  if (mounted) setState(() => _willTalk = value);
                  _storage.write(key: 'will_talk', value: value.toString());
                  Navigator.pop(context);
                },
              ),
              SwitchListTile(
                title: const Text('Graphify Multi-Model Teams', style: TextStyle(fontSize: 14)),
                subtitle: const Text('Chain models to save tokens & boost reasoning', style: TextStyle(fontSize: 12, color: Colors.grey)),
                value: _graphifyEnabled,
                activeColor: const Color(0xFF7C6CFF),
                contentPadding: EdgeInsets.zero,
                onChanged: (bool value) {
                  if (mounted) setState(() => _graphifyEnabled = value);
                  _storage.write(key: 'graphify_enabled', value: value.toString());
                  Navigator.pop(context);
                },
              ),
              SwitchListTile(
                title: const Text('Quiet Hours', style: TextStyle(fontSize: 14)),
                subtitle: const Text('Suppress non-critical voice summaries (10 PM - 7 AM)', style: TextStyle(fontSize: 12, color: Colors.grey)),
                value: _quietHoursEnabled,
                activeColor: const Color(0xFF7C6CFF),
                contentPadding: EdgeInsets.zero,
                onChanged: (bool value) {
                  if (mounted) setState(() => _quietHoursEnabled = value);
                  _storage.write(key: 'quiet_hours_enabled', value: value.toString());
                  Navigator.pop(context);
                },
              ),
              const Divider(color: Colors.white10),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Lock Session', style: TextStyle(fontSize: 14, color: Colors.orangeAccent)),
                leading: const Icon(Icons.lock_outline, color: Colors.orangeAccent, size: 20),
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
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Clear Local Data', style: TextStyle(fontSize: 14, color: Colors.redAccent)),
                leading: const Icon(Icons.delete_outline, color: Colors.redAccent, size: 20),
                onTap: () {
                  Navigator.pop(context);
                  _clearLocalData();
                },
              ),
              ListTile(
                contentPadding: EdgeInsets.zero,
                title: const Text('Clear Backend Devices', style: TextStyle(fontSize: 14, color: Colors.redAccent)),
                leading: const Icon(Icons.delete_sweep_outlined, color: Colors.redAccent, size: 20),
                onTap: () {
                  Navigator.pop(context);
                  _clearBackendData();
                },
              ),
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

  void _retryLastCommand() {
    String? lastUserCommand;
    for (var i = _messages.length - 1; i >= 0; i--) {
      if (_messages[i]['type'] == 'user') {
        lastUserCommand = _messages[i]['content'];
        break;
      }
    }
    if (lastUserCommand != null) {
      _controller.text = lastUserCommand;
      _sendMessage();
    }
  }

  void _showErrorLog(String content) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: const Color(0xFF1A1A1F),
        title: const Text('Error Log', style: TextStyle(color: Colors.white, fontSize: 16)),
        content: SingleChildScrollView(
          child: Text(content, style: const TextStyle(color: Colors.redAccent, fontSize: 13, fontFamily: 'monospace')),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context), child: const Text('Close')),
        ],
      ),
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
    final type = message['type'] as String? ?? 'unknown';
    final content = message['content'] as String? ?? '';
    final isUser = type == 'user';
    final isError = type == 'error';

    return Container(
      margin: EdgeInsets.only(
        bottom: 32,
        left: isUser ? 60 : 20,
        right: isUser ? 20 : 60,
      ),
      child: isUser
          // User messages are compact, bold pills (M-Chef style)
          ? Align(
              alignment: Alignment.centerRight,
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                decoration: BoxDecoration(
                  color: AppTokens.accent,
                  borderRadius: BorderRadius.circular(100),
                  boxShadow: [
                    BoxShadow(color: AppTokens.accent.withOpacity(0.3), blurRadius: 12, offset: const Offset(0, 6))
                  ],
                ),
                child: type == 'image'
                    ? ClipRRect(
                        borderRadius: BorderRadius.circular(12),
                        child: Image.memory(
                          base64Decode(content),
                          fit: BoxFit.cover,
                        ),
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
            )
          // AI messages are gorgeous raw text on background (Learning Roadmap style)
          : Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  crossAxisAlignment: CrossAxisAlignment.center,
                  children: [
                    Container(
                      width: 8,
                      height: 8,
                      decoration: BoxDecoration(
                        color: isError ? const Color(0xFFEF4444) : AppTokens.accentSecondary,
                        shape: BoxShape.circle,
                      ),
                    ),
                    const SizedBox(width: 12),
                    Text(
                      isError ? 'SYSTEM ERROR' : 'AI ASSISTANT',
                      style: GoogleFonts.spaceGrotesk(
                        color: isError ? const Color(0xFFEF4444) : AppTokens.accentSecondary,
                        fontSize: 11,
                        fontWeight: FontWeight.w800,
                        letterSpacing: 2.0,
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),
                type == 'image'
                    ? ClipRRect(
                        borderRadius: BorderRadius.circular(24),
                        child: Image.memory(
                          base64Decode(content),
                          fit: BoxFit.cover,
                        ),
                      )
                    : CollapsibleOutput(
                        text: content,
                        style: GoogleFonts.outfit(
                          textStyle: TextStyle(
                            color: isError ? const Color(0xFFEF4444) : AppTokens.textPrimary(isDark),
                            fontSize: 18,
                            height: 1.6,
                            fontWeight: FontWeight.w500,
                          ),
                        ),
                      ),
              ],
            ),
    );
  }

  Widget _buildBgTasksSidebar() {
    // Reverse the tasks to show newest first, and limit to last 50 to avoid clutter
    final displayTasks = _bgTasks.reversed.take(50).toList();
    
    return Drawer(
      backgroundColor: AppTokens.bg(appThemeMode.value == ThemeMode.dark),
      child: SafeArea(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                border: Border(bottom: BorderSide(color: AppTokens.border(appThemeMode.value == ThemeMode.dark))),
                color: const Color(0xFF14B8A6).withOpacity(0.05),
              ),
              child: Row(
                children: [
                  const Icon(Icons.memory, color: Color(0xFF2DD4BF), size: 20),
                  const SizedBox(width: 12),
                  const Text('Background Tasks', style: TextStyle(color: Color(0xFF2DD4BF), fontWeight: FontWeight.w800, fontSize: 16)),
                  const Spacer(),
                  Text('${_bgTasks.where((t) => t['status'] == 'running').length} RUNNING', 
                    style: const TextStyle(color: Color(0xFF5EEAD4), fontSize: 10, fontWeight: FontWeight.bold)),
                ],
              ),
            ),
            Expanded(
              child: displayTasks.isEmpty
                  ? const Center(child: Text('No background tasks', style: TextStyle(color: Colors.white54)))
                  : ListView.builder(
                      padding: const EdgeInsets.all(12),
                      itemCount: displayTasks.length,
                      itemBuilder: (context, index) {
                        final task = displayTasks[index];
                        final isDone = task['status'] == 'completed';
                        final isFail = task['status'] == 'failed';
                        final c = isDone ? const Color(0xFF34D399) : (isFail ? const Color(0xFFF87171) : const Color(0xFF2DD4BF));
                        
                        return Padding(
                          padding: const EdgeInsets.only(bottom: 8),
                          child: InkWell(
                            borderRadius: BorderRadius.circular(8),
                            onTap: () {
                              showDialog(
                                context: context,
                                builder: (context) => AlertDialog(
                                  backgroundColor: const Color(0xFF1E1E24),
                                  title: Row(
                                    children: [
                                      Icon(isDone ? Icons.check_circle : (isFail ? Icons.error : Icons.memory), color: c, size: 20),
                                      const SizedBox(width: 8),
                                      const Text('Task Details', style: TextStyle(color: Colors.white, fontSize: 16)),
                                    ],
                                  ),
                                  content: Column(
                                    mainAxisSize: MainAxisSize.min,
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text('ID: ${task["id"]}', style: const TextStyle(color: Colors.white70, fontSize: 12)),
                                      const SizedBox(height: 4),
                                      Text('Status: ${task["status"].toString().toUpperCase()}', style: TextStyle(color: c, fontSize: 12, fontWeight: FontWeight.bold)),
                                      const SizedBox(height: 4),
                                      Text('Duration: ${task["duration"]}', style: const TextStyle(color: Colors.white70, fontSize: 12)),
                                      const SizedBox(height: 12),
                                      const Text('Command:', style: TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold)),
                                      const SizedBox(height: 4),
                                      Container(
                                        padding: const EdgeInsets.all(8),
                                        decoration: BoxDecoration(
                                          color: Colors.black38,
                                          borderRadius: BorderRadius.circular(6),
                                        ),
                                        child: Text(task["command"], style: const TextStyle(color: Colors.greenAccent, fontFamily: 'monospace', fontSize: 11)),
                                      ),
                                    ],
                                  ),
                                  actions: [
                                    TextButton(
                                      onPressed: () => Navigator.pop(context),
                                      child: const Text('Close', style: TextStyle(color: Colors.white70)),
                                    )
                                  ],
                                ),
                              );
                            },
                            child: Container(
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: const Color(0xFF1A1A1F),
                                border: Border.all(color: c.withOpacity(0.3), width: 1),
                                borderRadius: BorderRadius.circular(8),
                              ),
                              child: Row(
                                children: [
                                  Icon(isDone ? Icons.check_circle : (isFail ? Icons.error : Icons.hourglass_top), color: c, size: 16),
                                  const SizedBox(width: 12),
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(task["id"], style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold)),
                                        const SizedBox(height: 4),
                                        Text(task["command"], maxLines: 1, overflow: TextOverflow.ellipsis, style: const TextStyle(color: Colors.white54, fontSize: 10, fontFamily: 'monospace')),
                                      ],
                                    ),
                                  ),
                                  const SizedBox(width: 8),
                                  Text(task["duration"], style: const TextStyle(color: Colors.white54, fontSize: 10)),
                                ],
                              ),
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
              ),
            ],
          ),
        );
      }

      // Minimal floating pill input
      return Container(
        margin: const EdgeInsets.only(left: 20, right: 20, bottom: 30, top: 10),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            GestureDetector(
              onTap: () {
                _controller.text = "__SCREENSHOT__";
                _sendMessage();
              },
              child: Container(
                margin: const EdgeInsets.only(bottom: 2, right: 12),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: AppTokens.cardAlt(isDark),
                  shape: BoxShape.circle,
                  border: Border.all(color: AppTokens.border(isDark)),
                ),
                child: Icon(Icons.camera_alt_rounded, color: AppTokens.textSecondary(isDark), size: 22),
              ),
            ),
            
            Expanded(
              child: Container(
                margin: const EdgeInsets.only(bottom: 2),
                decoration: BoxDecoration(
                  color: AppTokens.cardAlt(isDark),
                  borderRadius: BorderRadius.circular(100),
                  border: Border.all(color: AppTokens.border(isDark)),
                ),
                child: TextField(
                  controller: _controller,
                  minLines: 1,
                  maxLines: 4,
                  style: GoogleFonts.inter(fontSize: 16, color: AppTokens.textPrimary(isDark), fontWeight: FontWeight.w500),
                  decoration: InputDecoration(
                    hintText: 'Ask me anything...',
                    hintStyle: GoogleFonts.inter(color: AppTokens.textSecondary(isDark)),
                    contentPadding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
                    border: InputBorder.none,
                  ),
                ),
              ),
            ),

            const SizedBox(width: 12),
            GestureDetector(
              onTap: () {
                if (_isThinking) {
                  _cancelBackendTask();
                } else if (_controller.text.isNotEmpty) {
                  _sendMessage();
                } else {
                  setState(() { _isLiveSession = true; _showTextInput = false; });
                  _startListening();
                }
              },
              child: Container(
                margin: const EdgeInsets.only(bottom: 2),
                padding: const EdgeInsets.all(16),
                decoration: BoxDecoration(
                  color: _isThinking
                      ? const Color(0xFFEF4444)
                      : (_controller.text.isNotEmpty
                          ? AppTokens.accentSecondary
                          : AppTokens.accent),
                  shape: BoxShape.circle,
                  boxShadow: [
                    BoxShadow(
                      color: (_isThinking ? const Color(0xFFEF4444) : (_controller.text.isNotEmpty ? AppTokens.accentSecondary : AppTokens.accent)).withOpacity(0.4),
                      blurRadius: 16,
                      offset: const Offset(0, 6),
                    )
                  ],
                ),
                child: Icon(
                  _isThinking 
                      ? Icons.stop_rounded 
                      : (_controller.text.isNotEmpty 
                          ? Icons.send_rounded 
                          : Icons.mic_rounded),
                  color: _controller.text.isNotEmpty ? const Color(0xFF09090B) : Colors.white,
                  size: 22,
                ),
              ),
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
            const SizedBox(width: 8),
            GestureDetector(
              onTap: () {
                _controller.text = "__SCREENSHOT__";
                _sendMessage();
              },
              child: Container(
                padding: const EdgeInsets.all(14),
                margin: const EdgeInsets.only(bottom: 2),
                decoration: BoxDecoration(
                  color: AppTokens.cardAlt(isDark),
                  shape: BoxShape.circle,
                ),
                child: Icon(Icons.camera_alt_rounded, color: AppTokens.textSecondary(isDark), size: 20),
              ),
            ),
            const SizedBox(width: 8),
            GestureDetector(
              onTap: _sendMessage,
              child: Container(
                padding: const EdgeInsets.all(14),
                margin: const EdgeInsets.only(bottom: 2),
                decoration: const BoxDecoration(
                  color: AppTokens.accent,
                  shape: BoxShape.circle,
                ),
                child: const Icon(Icons.send_rounded, color: Colors.white, size: 20),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _cancelJob() {
    if (_activeJobId == null) return;
    _channel?.sink.add(jsonEncode({
      'type': 'cancel_job',
      'job_id': _activeJobId,
      'session_token': _sessionToken,
    }));
    if (mounted) setState(() {
      _activeJobStatus = 'cancelling';
    });
  }

  Widget _buildJobStrip(ColorScheme colorScheme) {
    if (_activeJobId == null || _activeJobStatus == '') return const SizedBox.shrink();
    
    bool isDark = appThemeMode.value == ThemeMode.dark;
    Color statusColor = AppTokens.accent;
    IconData icon = Icons.sync;
    bool spinner = false;
    
    switch (_activeJobStatus) {
      case 'running':
        statusColor = AppTokens.accentSecondary;
        spinner = true;
        break;
      case 'waiting_approval':
        statusColor = const Color(0xFFF59E0B);
        icon = Icons.warning_amber_rounded;
        break;
      case 'done':
        statusColor = const Color(0xFF10B981);
        icon = Icons.check_circle_rounded;
        break;
      case 'failed':
      case 'cancelled':
        statusColor = const Color(0xFFEF4444);
        icon = Icons.error_outline_rounded;
        break;
      case 'cancelling':
        statusColor = AppTokens.textSecondary(isDark);
        spinner = true;
        break;
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 200),
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: AppTokens.bentoBox(isDark, radius: 24).copyWith(
        border: Border.all(color: statusColor.withOpacity(0.3), width: 1.5),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: statusColor.withOpacity(0.15),
            ),
            child: spinner 
              ? SizedBox(width: 14, height: 14, child: CircularProgressIndicator(strokeWidth: 2, color: statusColor))
              : Icon(icon, color: statusColor, size: 14),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('BACKGROUND JOB', style: GoogleFonts.outfit(color: statusColor, fontSize: 10, fontWeight: FontWeight.bold, letterSpacing: 1.2)),
                const SizedBox(height: 2),
                Text(_activeJobSummary, style: GoogleFonts.inter(color: AppTokens.textPrimary(isDark), fontSize: 13, fontWeight: FontWeight.w500), maxLines: 1, overflow: TextOverflow.ellipsis),
              ],
            ),
          ),
          if (_activeJobStatus == 'running' || _activeJobStatus == 'waiting_approval')
            GestureDetector(
              onTap: _cancelJob,
              child: Container(
                padding: const EdgeInsets.all(8),
                decoration: BoxDecoration(
                  shape: BoxShape.circle,
                  color: AppTokens.cardAlt(isDark),
                ),
                child: Icon(Icons.close_rounded, color: AppTokens.textSecondary(isDark), size: 16),
              ),
            ),
        ],
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

  const CollapsibleOutput({super.key, required this.text, required this.style});

  @override
  State<CollapsibleOutput> createState() => _CollapsibleOutputState();
}

class _CollapsibleOutputState extends State<CollapsibleOutput> {
  bool _isExpanded = false;
  String _selectedModel = 'flash';
  bool _isFetchingModels = false;
  String _cachedSecurityPhrase = '';

  @override
  Widget build(BuildContext context) {
    final lines = widget.text.split('\n');
    final isLong = lines.length > 10;
    final displayText = (!_isExpanded && isLong) ? lines.take(10).join('\n') + '\n...' : widget.text;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        widget.style.fontFamily == 'Courier'
            ? Container(
                width: double.infinity,
                decoration: BoxDecoration(
                  color: Colors.black.withOpacity(0.3),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.white.withOpacity(0.05)),
                ),
                padding: const EdgeInsets.all(12),
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





