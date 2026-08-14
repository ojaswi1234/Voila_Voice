import 'dart:async';
import 'dart:convert';
import 'dart:io' show Platform;
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
import 'package:uuid/uuid.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

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
  final List<Map<String, dynamic>> _messagesCommand = [];
  final List<Map<String, dynamic>> _messagesAsk = [];
  List<Map<String, dynamic>> get _messages => _currentMode.toUpperCase() == 'ASK' ? _messagesAsk : _messagesCommand;
  bool _isThinking = false;
  bool _willTalk = true;
  FlutterTts flutterTts = FlutterTts();
  String _activeDevice = '';
  bool _isConnected = false;
  bool _isHealthy = false;
  bool _localAgentConnected = false;
  String _backendStatus = 'Checking...';
  Timer? _healthCheckTimer;
  Map<String, dynamic> _devices = {};
  String? _currentDeviceId;
  String? _currentDeviceName;
  String _sessionId = '';
  String _sessionToken = '';
  String _currentMode = 'ask';
  Map<String, dynamic> _savedDevices = {};
  String _currentConversationId = '';
  List<Map<String, String>> _conversations = [];
  
  // Speech-to-text state
  final SpeechToText _speechToText = SpeechToText();
  bool _isListening = false;
  bool _speechAvailable = false;
  bool _speechInitialized = false;
  
  // Security phrase for backend operations
  String _securityPhrase = '';

  @override
  void initState() {
    super.initState();
    _initTts();
    _loadSession();
    _storage.read(key: 'security_phrase').then((val) => _cachedSecurityPhrase = val ?? '');
    _setupWebSocket();
    _initializeSpeech();
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
      _messagesAsk.clear();
      _messagesAsk.insert(0, {'text': 'Started a new conversation.', 'isUser': false});
    });
    Navigator.pop(context); // close drawer
  }
  
  void _resumeConversation(String id, String title) {
    setState(() {
      _currentConversationId = id;
      _messagesAsk.clear();
      _messagesAsk.insert(0, {'text': 'Resumed conversation: ', 'isUser': false});
    });
    Navigator.pop(context); // close drawer
  }
  void _loadSession() async {
    final savedToken = await _storage.read(key: 'session_token');
    if (savedToken != null && savedToken.isNotEmpty) {
      setState(() {
        _sessionToken = savedToken;
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
    if (Platform.isAndroid) {
      await flutterTts.setEngine("com.google.android.tts");
    }
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
      debugPrint("Voice selection error: ");
    }

    await flutterTts.setSpeechRate(0.5);
    await flutterTts.setVolume(1.0);
    await flutterTts.setPitch(1.05); // Slightly elevated pitch for friendly casual tone
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
          } else {
            // Partial result - update text field live
            setState(() {
              _controller.text = result.recognizedWords;
            });
          }
        },
        listenFor: const Duration(seconds: 30),
        pauseFor: const Duration(seconds: 3),
        partialResults: true,
        localeId: 'en_US',
        cancelOnError: true,
      );
    } catch (e) {
      setState(() {
        _isListening = false;
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
    });
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
      
      channel.stream.listen((message) {
        setState(() {
          _isConnected = true;
          
          try {
            final jsonResponse = jsonDecode(message);
            
            if (jsonResponse is Map && jsonResponse['type'] == 'session') {
              setState(() {
                _sessionToken = jsonResponse['session_token'];
                _storage.write(key: 'session_token', value: _sessionToken);
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
                   parsedData = jsonDecode(dec);
                 } catch(e) {}
              } else if (payload is List) {
                 parsedData = payload;
              }
              setState(() {
                _conversations = List<Map<String, String>>.from(
                  parsedData.map((x) => Map<String, String>.from(x))
                );
              });
            } else if (jsonResponse is Map && jsonResponse['type'] == 'models_list') {
              List<dynamic> parsedData = [];
              var payload = jsonResponse['data'] ?? jsonResponse['models'];
              if (payload is Map && payload['encrypted'] != null) {
                 final String phrase = _cachedSecurityPhrase;
                 String dec = CryptoUtils.decrypt(payload['encrypted'], phrase);
                 try {
                   parsedData = jsonDecode(dec);
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
            } else if (jsonResponse is Map && jsonResponse['type'] == 'queued') {
              // Task queued! Keep loader spinning.
              return;
            } else if (jsonResponse is Map && jsonResponse.containsKey('summary')) {
              setState(() {
                _isThinking = false;
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
                _isThinking = false; 
                _isFetchingModels = false;
              });
              if (message.contains('Unauthorized')) {
                _sessionToken = ''; // Clear expired or invalid token
                _storage.delete(key: 'session_token');
              }

              _messages.add({
                'type': 'error',
                'content': message.replace('ERROR: ', ''),
                'timestamp': DateTime.now().toString(),
              });
            } else {
              setState(() { _isThinking = false; });
              _messages.add({
                'type': 'response',
                'content': message,
                'timestamp': DateTime.now().toString(),
              });
            }
          } catch (e) {
            setState(() { 
              _isThinking = false; 
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
        });
      }, onError: (error) {
        setState(() {
          _isThinking = false;
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
        
        Future.delayed(const Duration(seconds: 5), () {
          _connectToBackend();
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
      
      final response = await http.get(Uri.parse(httpUrl));
      
      if (response.statusCode == 200) {
        final healthData = jsonDecode(response.body);
        
        // Use devices_online for presence (registered-but-stale not counted)
        final devicesOnline = healthData['devices_online'] is int 
            ? healthData['devices_online'] as int 
            : 0;
        
        // Check if active device is specifically online and reachable
        bool activeDeviceOnline = false;
        if (healthData['online_devices'] is List) {
          final onlineDevices = healthData['online_devices'] as List;
          for (var device in onlineDevices) {
            if (device['id'] == _activeDevice && device['online'] == true) {
              // Device is online, check if reachable
              final reachable = device['reachable'] == true;
              activeDeviceOnline = reachable;
              break;
            }
          }
        }
        
        setState(() {
          _isHealthy = true;
          _localAgentConnected = activeDeviceOnline; // Only show connected if active device is reachable
          _backendStatus = 'Healthy (${healthData['uptime']})';
        });
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
        _backendStatus = 'Health check failed';
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
        _isThinking = false;
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

  Future<bool> _ensureUnlocked() async {
    if (_sessionToken.isNotEmpty) return true;
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
      if (_sessionToken.isNotEmpty) {
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
    return Drawer(
      backgroundColor: const Color(0xFF191919),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.only(top: 60, bottom: 20, left: 20, right: 20),
            color: const Color(0xFF1E1E1E),
            child: Row(
              children: [
                const Icon(Icons.chat_bubble_outline, color: Colors.white70),
                const SizedBox(width: 12),
                const Text('Conversations', style: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold)),
                const Spacer(),
                IconButton(
                  icon: const Icon(Icons.refresh, color: Colors.white54),
                  onPressed: _fetchConversations,
                )
              ],
            ),
          ),
          ListTile(
            leading: const Icon(Icons.add, color: Colors.white),
            title: const Text('New Chat', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            onTap: _startNewConversation,
          ),
          const Divider(color: Colors.white24),
          Expanded(
            child: ListView.builder(
              padding: EdgeInsets.zero,
              itemCount: _conversations.length,
              itemBuilder: (context, index) {
                final conv = _conversations[index];
                final isSelected = _currentConversationId == conv['id'];
                return ListTile(
                  tileColor: isSelected ? Colors.white.withOpacity(0.1) : null,
                  leading: const Icon(Icons.history, color: Colors.white54),
                  title: Text(conv['title'] ?? 'Unknown', style: const TextStyle(color: Colors.white70)),
                  onTap: () => _resumeConversation(conv['id']!, conv['title']!),
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    
    return Scaffold(
      drawer: _currentMode.toUpperCase() == 'ASK' ? _buildDrawer() : null,
      backgroundColor: const Color(0xFF0F0F12),
      appBar: AppBar(
        title: const Text(
          'Voila Voice',
          style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, letterSpacing: -0.3),
        ),
        actions: [
          if (_currentMode.toUpperCase() == 'ASK')
            IconButton(
              icon: Icon(Icons.auto_awesome, size: 20, color: _selectedModel.isNotEmpty ? colorScheme.secondary : colorScheme.onSurface.withOpacity(0.7)),
              onPressed: _showModelSelector,
            ),
          IconButton(
            icon: Icon(Icons.folder_copy_outlined, size: 20, color: colorScheme.onSurface.withOpacity(0.7)),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(
                  builder: (context) => const ArtifactsPage(),
                ),
              );
            },
          ),
          IconButton(
            icon: Icon(Icons.settings_outlined, size: 20, color: colorScheme.onSurface.withOpacity(0.7)),
            onPressed: () => _showSettingsSheet(context),
          ),
        ],
      ),
      body: Column(
        children: [
          _buildStatusRow(colorScheme),
          const SizedBox(height: 12),
          _buildModeToggle(colorScheme),
          const SizedBox(height: 16),
          Expanded(child: _buildMessagesList(colorScheme)),
          _buildInputArea(colorScheme),
        ],
      ),
    );
  }


  Future<void> _speak(String text) async {
    if (!_willTalk || text.isEmpty) return;
    await flutterTts.speak(text);
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

  Widget _buildStatusRow(ColorScheme colorScheme) {
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 16),
      child: Row(
        children: [
          _buildStatusDot(_isConnected, _isConnected ? colorScheme.secondary : Colors.redAccent),
          const SizedBox(width: 6),
          Text(_isConnected ? 'Connected' : 'Offline', style: TextStyle(fontSize: 12, color: Colors.white54)),
          const Spacer(),
          GestureDetector(
            onTap: () => _showDeviceSelector(context),
            child: Container(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFF1A1A1F),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.white.withOpacity(0.08)),
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
        ],
      ),
    );
  }

  Widget _buildStatusDot(bool active, Color color) {
    return Container(
      width: 8, height: 8,
      decoration: BoxDecoration(color: color, shape: BoxShape.circle, boxShadow: [BoxShadow(color: color.withOpacity(0.4), blurRadius: 4)]),
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
    final isAsk = _currentMode == 'ask';
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
                left: isAsk ? 0 : width,
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
                      onTap: () => setState(() => _currentMode = 'ask'),
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        alignment: Alignment.center,
                        child: Text('Ask', style: TextStyle(fontSize: 13, fontWeight: isAsk ? FontWeight.w600 : FontWeight.w500, color: isAsk ? Colors.white : Colors.white54)),
                      ),
                    ),
                  ),
                  Expanded(
                    child: GestureDetector(
                      behavior: HitTestBehavior.opaque,
                      onTap: () => setState(() => _currentMode = 'command'),
                      child: Container(
                        padding: const EdgeInsets.symmetric(vertical: 8),
                        alignment: Alignment.center,
                        child: Text('Command', style: TextStyle(fontSize: 13, fontWeight: !isAsk ? FontWeight.w600 : FontWeight.w500, color: !isAsk ? Colors.white : Colors.white54)),
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
    final isAsk = _currentMode == 'ask';

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
                  borderRadius: BorderRadius.circular(isAsk ? 24 : 12),
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
                        style: TextStyle(
                          fontSize: 14,
                          color: Colors.white,
                          fontFamily: isAsk ? null : 'Courier',
                        ),
                        decoration: InputDecoration(
                          hintText: _isListening ? 'Listening...' : (isAsk ? 'Ask anything...' : 'Enter command...'),
                          hintStyle: TextStyle(
                            color: Colors.white30,
                            fontFamily: isAsk ? null : 'Courier',
                          ),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                          border: InputBorder.none,
                        ),
                      ),
                    ),
                    AnimatedSize(
                      duration: const Duration(milliseconds: 200),
                      child: isAsk
                          ? GestureDetector(
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
                            )
                          : const SizedBox(width: 0),
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
                  borderRadius: BorderRadius.circular(isAsk ? 24 : 12),
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
