import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform;
import 'package:flutter/foundation.dart'; // For compute()
import 'package:flutter/material.dart';
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

void main() {
  runApp(const VoiceCliApp());
}

class VoiceCliApp extends StatelessWidget {
  const VoiceCliApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'Voice CLI',
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        scaffoldBackgroundColor: const Color(0xFF0F0F12),
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
}

class VoiceHomePage extends StatefulWidget {
  const VoiceHomePage({super.key});

  @override
  State<VoiceHomePage> createState() => _VoiceHomePageState();
}

class _VoiceHomePageState extends State<VoiceHomePage> {
  late WebSocketChannel channel;
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
  bool _isDataDeparting = false;
  bool _isDataArriving = false;
  bool _willTalk = true;
  FlutterTts flutterTts = FlutterTts();
  String _activeDevice = '';
  bool _isConnected = false;
  bool _isHealthy = false;
  bool _localAgentConnected = false;

  void _triggerDataDeparting() {
    setState(() => _isDataDeparting = true);
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
  void initState() {
    super.initState();
    _initBackground();
    _initTts();
    _loadSession();
    _storage.read(key: 'security_phrase').then((val) => _cachedSecurityPhrase = val ?? '');
    _setupWebSocket();
    _initializeSpeech();
  }

  Future<void> _initBackground() async {
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
    if (channel != null && _isConnected) {
      final msg = jsonEncode({
        "type": "get_conversations",
        "device_id": _activeDevice,
        "session_token": _sessionToken
      });
      channel.sink.add(msg);
    }
  }
  
  void _startNewConversation() {
    setState(() {
      _currentConversationId = '';
      _messagesAgent.clear();
      _messagesAgent.insert(0, {'text': 'Started a new conversation.', 'isUser': false});
    });
    Navigator.pop(context); // close drawer
  }
  
  void _resumeConversation(String id, String title) {
    setState(() {
      _currentConversationId = id;
      _messagesAgent.clear();
      _messagesAgent.insert(0, {'text': 'Resumed conversation: ', 'isUser': false});
    });
    Navigator.pop(context); // close drawer
  }
  void _loadSession() async {
    final savedToken = await _storage.read(key: 'session_token');
    final savedExpiresAt = await _storage.read(key: 'session_expires_at');
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
    _initializeSpeech();

    Future.delayed(const Duration(seconds: 1), _getDevices);
  }

  Future<void> _initTts() async {
    // 100% Legal, Native, Free OS-Level Neural Voices
    // Use system default TTS engine instead of hardcoding Google TTS
    // This ensures compatibility with de-Googled devices and Samsung devices
    await flutterTts.setLanguage("en-US");
    
    // Attempt to select a high-quality network voice (Neural/Wavenet)
    try {
      final voices = await flutterTts.getVoices;
      if (voices != null) {
        for (var voice in voices) {
          // Look for premium Google network voices (typically female, highly natural)
          if (voice['name'] != null && voice['name'].toString().contains('network') && voice['name'].toString().contains('en-us-x-sfg')) {
            await flutterTts.setVoice({"name": voice["name"], "locale": voice["locale"]});
            break;
          }
        }
      }
    } catch (e) {
      debugPrint("Voice selection error: $e");
    }

    await flutterTts.setSpeechRate(0.5);
    await flutterTts.setVolume(1.0);
    await flutterTts.setPitch(1.05); // Slightly elevated pitch for friendly casual tone

    flutterTts.setStartHandler(() {
      setState(() {
        _isAiSpeaking = true;
      });
    });

    flutterTts.setCompletionHandler(() {
      setState(() {
        _isAiSpeaking = false;
      });
      if (_isLiveSession && mounted) {
        // Automatically start listening again after AI finishes speaking
        _startListening();
      }
    });
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

  Future<void> _startListening() async {
    final hasPermission = await _requestMicrophonePermission();
    if (!hasPermission) {
      return;
    }
    
    setState(() {
      _isListening = true;
    });
    
    try {
      await _speechToText.listen(
        onResult: (result) {
          if (result.finalResult) {
            setState(() {
              _controller.text = result.recognizedWords;
              _isListening = false;
            });
            
            // Automatically submit command if in live session
            if (_isLiveSession && _controller.text.isNotEmpty) {
              _sendMessage();
            }
          } else {
            // Partial result - update text field live
            setState(() {
              _controller.text = result.recognizedWords;
            });
          }
        },
        onSoundLevelChange: (level) {
          setState(() {
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
      setState(() {
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
    setState(() {
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
      channel.sink.add(jsonEncode(message));
      
      setState(() {
        _isThinking = false; _triggerDataArriving();
        _messages.add({
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
    setState(() {});
  }

  void _connectToBackend() {
    try {
      final url = backendUrl;
      debugPrint('Connecting WebSocket to: $url');
      channel = WebSocketChannel.connect(
        Uri.parse(url),
      );
      
      channel.stream.listen((message) async {
        setState(() {
          _isConnected = true;
          _reconnectAttempts = 0; // Reset reconnection counter on successful connect
        });
        
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
              
              setState(() {
                _sessionToken = sessionToken;
                _sessionExpiresAt = sessionExpiresAt;
              });
              
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
                    // Track first online desktop for auto-selection
                    if (deviceOnline && firstOnlineDesktop == null) {
                      firstOnlineDesktop = deviceId;
                    }
                    // Auto-save desktop devices for quick reconnect
                    DeviceIdentity.saveDevice(deviceId, device);
                    DeviceIdentity.getSavedDevices().then((devices) {
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
                setState(() {});
              }
              final onlineCount = _devices.values.where((d) => d['online'] == true).length;
              final reachableCount = _devices.values.where((d) => d['reachable'] == true).length;
              _messages.add({
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
              setState(() {
                _conversations = List<Map<String, String>>.from(
                  parsedData.map((x) => Map<String, String>.from(x))
                );
              });
            } else if (jsonResponse is Map && jsonResponse['type'] == 'security_alert') {
              final alert = jsonResponse['alert'];
              if (alert != null) {
                setState(() {
                  _securityAlerts.add(alert);
                });
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
                setState(() {
                  _securityAlerts = List<Map<String, dynamic>>.from(alerts);
                });
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
              setState(() {
                _isFetchingModels = false;
                _modelsList = parsedData.map((e) => e.toString()).toList();
                if (_modelsList.isNotEmpty && _selectedModel.isEmpty) {
                  _selectedModel = _modelsList[0];
                }
              });
            } else if (jsonResponse is Map && jsonResponse['type'] == 'pong') {
              // Silently ignore pong responses
              return;
            } else if (jsonResponse is Map && jsonResponse['type'] == 'queued') {
              // Task queued! Keep loader spinning.
              return;
            } else if (jsonResponse is Map && jsonResponse.containsKey('summary')) {
              setState(() {
                _isThinking = false; _triggerDataArriving();
              });
              if (_willTalk) {
                _speak(jsonResponse['summary']);
              }
              
              if (jsonResponse.containsKey('new_conversation_id') && jsonResponse['new_conversation_id'] != null) {
                final newId = jsonResponse['new_conversation_id'].toString();
                if (newId.isNotEmpty && newId != _currentConversationId) {
                  _currentConversationId = newId;
                  _fetchConversations();
                }
              }

              _messages.add({
                'type': 'response',
                'content': jsonResponse['output'] ?? message,
                'summary': jsonResponse['summary'],
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
                    SnackBar(content: Text('${(jsonResponse['artifacts'] as List).length} artifacts saved!')),
                  );
                }
              }
            } else if (message.contains('OK: All devices cleared')) {
              _messages.add({
                'type': 'system',
                'content': 'Backend data cleared successfully',
                'timestamp': DateTime.now().toString(),
              });
              _devices = {};
              _savedDevices = {};
              DeviceIdentity.clearAllSavedDevices();
              setState(() {});
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

              _messages.add({
                'type': 'error',
                'content': message.replaceFirst('ERROR: ', ''),
                'timestamp': DateTime.now().toString(),
              });
            } else {
              setState(() { _isThinking = false; _triggerDataArriving(); });
              _messages.add({
                'type': 'response',
                'content': message,
                'timestamp': DateTime.now().toString(),
              });
            }
          } catch (e) {
            setState(() { 
              _isThinking = false; _triggerDataArriving(); 
              _isFetchingModels = false;
            });
            _messages.add({
              'type': 'response',
              'content': message,
              'timestamp': DateTime.now().toString(),
            });
          }
          
          _checkBackendHealth();
          _scrollToBottom();
      }, onError: (error) {
        setState(() {
          _isThinking = false; _triggerDataArriving();
          _isConnected = false;
          _messages.add({
            'type': 'error',
            'content': 'Connection error: $error',
            'timestamp': DateTime.now().toString(),
          });
        });
      }, onDone: () {
        setState(() {
          _isConnected = false;
          _messages.add({
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
        try { channel.sink.close(); } catch (_) {}
        Future.delayed(delay, () {
          if (mounted) _connectToBackend();
        });
      });
    } catch (e) {
      setState(() {
        _isConnected = false;
        _messages.add({
          'type': 'error',
          'content': 'Failed to connect: $e',
          'timestamp': DateTime.now().toString(),
        });
      });
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
          
          setState(() {
            _isHealthy = true;
            _localAgentConnected = activeDeviceOnline;
            _backendStatus = 'Healthy (${statusData['uptime']})';
          });
        } else {
          setState(() {
            _isHealthy = false;
            _localAgentConnected = false;
            _backendStatus = 'Status endpoint failed (${statusResponse.statusCode})';
          });
        }
      } else {
        setState(() {
          _isHealthy = false;
          _localAgentConnected = false;
          _backendStatus = 'Unhealthy (${response.statusCode})';
        });
      }
    } catch (e) {
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

  @override
  void dispose() {
    _healthCheckTimer?.cancel();
    channel.sink.close();
    _controller.dispose();
    _scrollController.dispose();
    if (_isListening) {
      _speechToText.stop();
    }
    super.dispose();
  }


  void _stopCommand() {
    if (channel != null && _isConnected) {
      channel.sink.add(jsonEncode({"type": "stop_command"}));
      setState(() {
        _isThinking = false; _triggerDataArriving();
        _messages.add({
          'type': 'response',
          'content': 'Execution stopped by user.',
          'timestamp': DateTime.now().toString(),
        });
      });
    }
  }

  void _fetchModels() {
    if (channel != null && _isConnected) {
      setState(() => _isFetchingModels = true);
      channel.sink.add(jsonEncode({
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
                    Expanded(
                      child: ListView.builder(
                        itemCount: _modelsList.length,
                        itemBuilder: (context, index) {
                          final model = _modelsList[index];
                          return ListTile(
                            title: Text(model, style: const TextStyle(color: Colors.white70)),
                            trailing: _selectedModel == model ? const Icon(Icons.check, color: Colors.greenAccent) : null,
                            onTap: () {
                              setState(() => _selectedModel = model);
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
        setState(() {
          _messages.add({
            'type': 'error',
            'content': 'Not connected to backend. Please wait for reconnection.',
            'timestamp': DateTime.now().toString(),
          });
        });
        _scrollToBottom();
        return;
      }
      
      if (_activeDevice.isEmpty) {
        setState(() {
          _messages.add({
            'type': 'error',
            'content': 'No online desktop device selected. Please wait for devices to load or refresh.',
            'timestamp': DateTime.now().toString(),
          });
        });
        _controller.clear();
        _scrollToBottom();
        return;
      }
      
      // Validate that selected device is actually a desktop device
      if (!_activeDevice.startsWith('desktop-')) {
        setState(() {
          _messages.add({
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
      
      // Check session validity before sending
      if (!_isSessionValid()) {
        setState(() {
          _messages.add({
            'type': 'error',
            'content': 'Session expired — unlock to continue',
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
        'idempotency_key': const Uuid().v4(),
        'client_timestamp': DateTime.now().millisecondsSinceEpoch,
      };
      
      debugPrint('Sending command to device: $_activeDevice');
      debugPrint('Message: $message');
      
      channel.sink.add(jsonEncode(message));
      setState(() {
        _isThinking = true;
        _triggerDataDeparting();
        _messages.add({
          'type': 'user',
          'content': _controller.text,
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
    
    channel.sink.add(jsonEncode(message));
    setState(() {
      _activeDevice = deviceId;
      _messages.add({
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
    
    channel.sink.add(jsonEncode(message));
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
      return 'Unlocked · ${remaining}s left';
    }
    final minutes = remaining ~/ 60;
    return 'Unlocked · ${minutes}m left';
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
          const SnackBar(content: Text('Session expiring soon – consider unlocking again')),
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
    channel.sink.add(jsonEncode(message));
    
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
    final securityPhrase = _securityPhrase; // still using it for clear data just in case, but token is better

    
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
      
      channel.sink.add(jsonEncode(message));
      setState(() {
        _messages.add({
          'type': 'system',
          'content': 'Requesting backend data clear...',
          'timestamp': DateTime.now().toString(),
        });
      });
    }
    
    _securityPhrase = '';
  }

  void _showSecurityAlerts() {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1E1E1E),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      isScrollControlled: true,
      builder: (context) {
        return StatefulBuilder(
          builder: (context, setModalState) {
            return Container(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
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
                                setState(() {
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
                              channel.sink.add(jsonEncode(message));
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
    
    final phrase = await _promptSecurityPhrase();
    if (phrase == null || phrase.isEmpty) return;
    
    final message = {
      'type': 'circuit_reset',
      'device_id': _activeDevice,
      'session_token': _sessionToken,
      'security_phrase': phrase,
    };
    
    channel.sink.add(jsonEncode(message));
    
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
      setState(() {
        _savedDevices = {};
        _devices = {};
        _messages.add({
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
                    setState(() {
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
    return ListTile(
      leading: Icon(icon, color: Colors.white70),
      title: Text(title, style: const TextStyle(color: Colors.white, fontSize: 15)),
      onTap: onTap,
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    
    return Scaffold(
      drawer: _buildDrawer(),
      backgroundColor: const Color(0xFF0F0F12),
      appBar: AppBar(
        title: const Text(
          'Voila Voice',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold, letterSpacing: -0.5),
        ),
        centerTitle: false,
        elevation: 0,
        actions: [
          if (_currentMode.toUpperCase() == 'AGENT')
            IconButton(
              icon: Icon(Icons.auto_awesome, size: 22, color: _selectedModel.isNotEmpty ? colorScheme.secondary : colorScheme.onSurface.withOpacity(0.7)),
              onPressed: _showModelSelector,
            ),
          GestureDetector(
            onTap: () => _showDeviceSelector(context),
            child: Container(
              margin: const EdgeInsets.symmetric(vertical: 10, horizontal: 8),
              padding: const EdgeInsets.symmetric(horizontal: 12),
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A1F),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: Colors.white.withOpacity(0.1)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(Icons.computer, size: 14, color: colorScheme.secondary),
                  const SizedBox(width: 6),
                  Text(
                    _activeDevice.isEmpty ? 'Select Device' : (_devices[_activeDevice]?['name'] ?? 'Desktop'),
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w500),
                  ),
                  const SizedBox(width: 4),
                  const Icon(Icons.keyboard_arrow_down, size: 14, color: Colors.white54),
                ],
              ),
            ),
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: Column(
        children: [
          ConnectionFlowchart(
            isBackendConnected: _isHealthy,
            isLocalAgentConnected: _localAgentConnected,
            isWebSocketConnected: _isConnected,
            isDataDeparting: _isDataDeparting,
            isDataArriving: _isDataArriving,
            activeDeviceName: _activeDevice.isNotEmpty ? (_devices[_activeDevice]?['name'] ?? 'Desktop') : null,
          ),
          const SizedBox(height: 12),
          _buildModeToggle(colorScheme),
          const SizedBox(height: 16),
          if (_currentMode != 'agent')
            Expanded(child: _buildMessagesList(colorScheme))
          else
            const Spacer(),
          _buildInputArea(colorScheme),
        ],
      ),
    );
  }


  String _normalizeForSpeech(String text) {
    String normalized = text;
    
    // --- Smart Speech Techniques ---
    // 1. URLs (e.g., https://github.com/foo/bar -> "a link to github.com")
    normalized = normalized.replaceAllMapped(
      RegExp(r'https?://([a-zA-Z0-9.-]+)[^\s]*'),
      (match) => 'a link to ${match.group(1)}'
    );
    
    // 2. Windows paths (e.g., C:\Users\desktop\file.txt -> "file file.txt")
    // Note: double escaping backslashes for Dart regex
    normalized = normalized.replaceAllMapped(
      RegExp(r'[a-zA-Z]:\\(?:[^\s\\]+\\)+([^\s\\]+\.[a-zA-Z0-9]+)'),
      (match) => 'file ${match.group(1)}'
    );
    
    // 3. Unix/Relative paths with at least 2 slashes (e.g., src/components/button.tsx -> "file button.tsx")
    normalized = normalized.replaceAllMapped(
      RegExp(r'(?:[a-zA-Z0-9_.-]+/){2,}([a-zA-Z0-9_.-]+\.[a-zA-Z0-9]+)'),
      (match) => 'file ${match.group(1)}'
    );
    
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
    normalized = normalized.replaceAll('\n', ' ... ');
    
    // Clean up extra spaces
    normalized = normalized.replaceAll(RegExp(r'\s+'), ' ').trim();
    
    return normalized;
  }

  Future<void> _speak(String text) async {
    if (!_willTalk || text.isEmpty) return;
    String cleanText = _normalizeForSpeech(text);
    await flutterTts.speak(cleanText);
  }

  void _showSettingsSheet(BuildContext context) {
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1A1A1F),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text('Settings', style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600)),
              const SizedBox(height: 20),
              SwitchListTile(
                title: const Text('Auto-read Voice Responses', style: TextStyle(fontSize: 14)),
                value: _willTalk,
                activeColor: const Color(0xFF7C6CFF),
                contentPadding: EdgeInsets.zero,
                onChanged: (bool value) {
                  setState(() => _willTalk = value);
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
                  setState(() {
                    _sessionToken = '';
                  });
                  if (mounted) {
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
    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF1A1A1F),
      shape: const RoundedRectangleBorder(borderRadius: BorderRadius.vertical(top: Radius.circular(20))),
      builder: (context) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
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
    );
  }

  Widget _buildModeToggle(ColorScheme colorScheme) {
    final isAgent = _currentMode == 'agent';
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1F),
        borderRadius: BorderRadius.circular(100),
        border: Border.all(color: Colors.white.withOpacity(0.04)),
      ),
      child: LayoutBuilder(
        builder: (context, constraints) {
          final width = constraints.maxWidth / 2;
          return Stack(
            children: [
              AnimatedPositioned(
                duration: const Duration(milliseconds: 250),
                curve: Curves.easeOutCubic,
                left: isAgent ? 0 : width,
                top: 0,
                bottom: 0,
                width: width,
                child: Container(
                  decoration: BoxDecoration(
                    color: const Color(0xFF222228),
                    borderRadius: BorderRadius.circular(100),
                    boxShadow: [BoxShadow(color: Colors.black.withOpacity(0.2), blurRadius: 4, offset: const Offset(0, 2))],
                  ),
                ),
              ),
              Row(
                children: [
                  Expanded(
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => setState(() => _currentMode = 'agent'),
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        alignment: Alignment.center,
                        child: Text('Agent', style: TextStyle(fontSize: 13, fontWeight: isAgent ? FontWeight.w600 : FontWeight.w500, color: isAgent ? Colors.white : Colors.white54)),
                      ),
                    ),
                  ),
                  Expanded(
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => setState(() => _currentMode = 'shell'),
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        alignment: Alignment.center,
                        child: Text('Shell', style: TextStyle(fontSize: 13, fontWeight: !isAgent ? FontWeight.w600 : FontWeight.w500, color: !isAgent ? Colors.white : Colors.white54)),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          );
        },
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
          Text('Processing...', style: TextStyle(fontSize: 13, color: Colors.white.withOpacity(0.6))),
        ],
      ),
    );
  }

  Widget _buildMessageCard(Map<String, dynamic> message, ColorScheme colorScheme) {
    final type = message['type'] as String? ?? 'unknown';
    final content = message['content'] as String? ?? '';
    final isUser = type == 'user';
    final isError = type == 'error';
    final isSystem = type == 'system';

    Color bgColor = const Color(0xFF1A1A1F);
    Color borderColor = Colors.white.withOpacity(0.04);
    
    if (isUser) {
      bgColor = const Color(0xFF222228);
    } else if (isError) {
      bgColor = Colors.redAccent.withOpacity(0.05);
      borderColor = Colors.redAccent.withOpacity(0.2);
    }

    return Container(
      margin: EdgeInsets.only(
        bottom: 16,
        left: isUser ? 32 : 0,
        right: isUser ? 0 : 32,
      ),
      decoration: BoxDecoration(
        color: bgColor,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: borderColor),
      ),
      child: ClipRRect(
        borderRadius: BorderRadius.circular(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(
                        isUser ? 'You' : (isSystem ? 'System' : 'Agent'),
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                          color: isUser ? Colors.white70 : (isError ? Colors.redAccent : colorScheme.primary),
                        ),
                      ),
                      if (message['timestamp'] != null)
                        Text(
                          message['timestamp'].toString().split(' ')[1].substring(0, 5),
                          style: const TextStyle(fontSize: 10, color: Colors.white30),
                        ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  CollapsibleOutput(
                    text: content,
                    style: TextStyle(
                      fontSize: 14,
                      height: 1.5,
                      fontFamily: isUser || isSystem ? null : 'Courier',
                      color: isError ? Colors.red.shade200 : Colors.white.withOpacity(0.9),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInputArea(ColorScheme colorScheme) {
    final isAgent = _currentMode == 'agent';

    if (isAgent) {
      return Container(
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: const Color(0xFF0F0F12),
          border: Border(top: BorderSide(color: Colors.white.withOpacity(0.05))),
        ),
        child: SafeArea(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
               if (_isLiveSession || _isAiSpeaking) 
                 AudioVisualizer(
                   isListening: _isListening,
                   isSpeaking: _isAiSpeaking,
                   soundLevel: _currentSoundLevel,
                 ),
               if (_isLiveSession || _isAiSpeaking) 
                 const SizedBox(height: 16),
               
               GestureDetector(
                 onTap: () {
                   if (_isLiveSession) {
                     _stopListening();
                     flutterTts.stop();
                     setState(() => _isAiSpeaking = false);
                     _cancelBackendTask();
                   } else {
                     setState(() => _isLiveSession = true);
                     _startListening();
                   }
                 },
                 child: Container(
                   padding: const EdgeInsets.all(20),
                   decoration: BoxDecoration(
                     color: _isLiveSession ? Colors.redAccent.withOpacity(0.15) : colorScheme.primary.withOpacity(0.15),
                     shape: BoxShape.circle,
                     border: Border.all(
                       color: _isLiveSession ? Colors.redAccent : colorScheme.primary,
                       width: 2,
                     ),
                   ),
                   child: Icon(
                     _isLiveSession ? Icons.stop_rounded : Icons.mic_rounded,
                     color: _isLiveSession ? Colors.redAccent : colorScheme.primary,
                     size: 36,
                   ),
                 ),
               ),
               const SizedBox(height: 12),
               Text(
                 _isLiveSession 
                    ? (_isAiSpeaking ? 'AI is speaking...' : (_isListening ? 'Listening...' : 'Processing...')) 
                    : 'Tap to start Voila Live',
                 style: const TextStyle(color: Colors.white54, fontSize: 13, fontWeight: FontWeight.w500),
               ),
            ],
          ),
        ),
      );
    }

    // SHELL mode - standard text input
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0F0F12),
        border: Border(top: BorderSide(color: Colors.white.withOpacity(0.05))),
      ),
      child: SafeArea(
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.end,
          children: [
            Expanded(
              child: Container(
                decoration: BoxDecoration(
                  color: const Color(0xFF1A1A1F),
                  borderRadius: BorderRadius.circular(12),
                  border: Border.all(color: _isListening ? colorScheme.primary.withOpacity(0.5) : Colors.white.withOpacity(0.08)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.end,
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _controller,
                        minLines: 1,
                        maxLines: 5,
                        style: const TextStyle(
                          fontSize: 14,
                          color: Colors.white,
                          fontFamily: 'Courier',
                        ),
                        decoration: InputDecoration(
                          hintText: _isListening ? 'Listening...' : 'Enter shell command...',
                          hintStyle: const TextStyle(
                            color: Colors.white30,
                            fontFamily: 'Courier',
                          ),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                          border: InputBorder.none,
                        ),
                      ),
                    ),
                    AnimatedSize(
                      duration: const Duration(milliseconds: 200),
                      child: GestureDetector(
                        onTap: _toggleListening,
                        child: Container(
                          padding: const EdgeInsets.all(12),
                          margin: const EdgeInsets.only(right: 4, bottom: 4),
                          decoration: BoxDecoration(
                            color: _isListening ? colorScheme.primary.withOpacity(0.15) : Colors.transparent,
                            shape: BoxShape.circle,
                          ),
                          child: Icon(
                            _isListening ? Icons.mic : Icons.mic_none,
                            color: _isListening ? colorScheme.primary : Colors.white54,
                            size: 20,
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(width: 12),
            GestureDetector(
              onTap: _sendMessage,
              child: Container(
                padding: const EdgeInsets.all(14),
                margin: const EdgeInsets.only(bottom: 2),
                decoration: BoxDecoration(
                  color: colorScheme.primary,
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(Icons.send_rounded, color: Colors.white, size: 20),
              ),
            ),
          ],
        ),
      ),
    );
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
              setState(() { _isExpanded = !_isExpanded; });
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
