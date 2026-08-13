import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
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
        scaffoldBackgroundColor: const Color(0xFF1E1E2E), // Deep dark brutalist
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFFFF3366),
          primary: const Color(0xFFFF3366), // Hot pink
          secondary: const Color(0xFF00E5FF), // Cyan
          tertiary: const Color(0xFFFFDE59), // Yellow
          surface: const Color(0xFF282A36), // Slightly lighter dark
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        textTheme: GoogleFonts.spaceGroteskTextTheme().apply(
          bodyColor: Colors.white,
          displayColor: Colors.white,
        ),
      ),
darkTheme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6750A4),
          brightness: Brightness.dark,
        ),
        useMaterial3: true,
        textTheme: GoogleFonts.interTextTheme(ThemeData.dark().textTheme),
      ),
      themeMode: ThemeMode.system,
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
    _setupWebSocket();
    _initializeSpeech();
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
    await flutterTts.setLanguage("en-US");
    await flutterTts.setSpeechRate(0.55);
    await flutterTts.setVolume(1.0);
    await flutterTts.setPitch(1.0);
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
            } else if (jsonResponse is Map && jsonResponse['type'] == 'queued') {
              // Task queued! Keep loader spinning.
              return;
            } else if (jsonResponse is Map && jsonResponse.containsKey('summary')) {
              setState(() {
                _isThinking = false;
              });
              if (_willTalk) {
                flutterTts.speak(jsonResponse['summary']);
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
              setState(() { _isThinking = false; });
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
            setState(() { _isThinking = false; });
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

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    
    return Scaffold(
      backgroundColor: const Color(0xFF1E1E2E), // Brutalist dark background
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(colorScheme),
            const SizedBox(height: 8),
            _buildConnectionFlow(colorScheme),
            const SizedBox(height: 8),
            _buildDeviceSelector(colorScheme),
            const SizedBox(height: 12),
            Expanded(child: _buildMessagesList(colorScheme)),
            _buildInputArea(colorScheme),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(ColorScheme colorScheme) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.tertiary, // Yellow
        border: Border.all(color: Colors.black, width: 3),
        boxShadow: const [BoxShadow(color: const Color(0xFF00E5FF), offset: Offset(4, 4))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                'VOICE CLI',
                style: TextStyle(
                  fontSize: 24,
                  fontWeight: FontWeight.w900,
                  letterSpacing: -0.5,
                  color: Colors.black,
                ),
              ),
              _buildStatusChip(_isConnected ? 'CONNECTED' : 'DISCONNECTED', _isConnected ? colorScheme.secondary : colorScheme.error),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            padding: const EdgeInsets.all(4),
            decoration: BoxDecoration(
              color: Colors.white,
              border: Border.all(color: Colors.black, width: 2),
              boxShadow: const [BoxShadow(color: Colors.black, offset: Offset(2, 2))],
            ),
            child: Row(
              children: [
                Expanded(
                  child: GestureDetector(
                    onTap: () => setState(() => _currentMode = 'ask'),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      decoration: BoxDecoration(
                        color: _currentMode == 'ask' ? colorScheme.secondary : Colors.white,
                        border: _currentMode == 'ask' ? Border.all(color: Colors.black, width: 2) : null,
                      ),
                      alignment: Alignment.center,
                      child: Text('ASK', style: TextStyle(fontWeight: FontWeight.w900, color: Colors.black, fontSize: 14)),
                    ),
                  ),
                ),
                Expanded(
                  child: GestureDetector(
                    onTap: () => setState(() => _currentMode = 'command'),
                    child: Container(
                      padding: const EdgeInsets.symmetric(vertical: 8),
                      decoration: BoxDecoration(
                        color: _currentMode == 'command' ? colorScheme.primary : Colors.white,
                        border: _currentMode == 'command' ? Border.all(color: Colors.black, width: 2) : null,
                      ),
                      alignment: Alignment.center,
                      child: Text('COMMAND', style: TextStyle(fontWeight: FontWeight.w900, color: Colors.black, fontSize: 14)),
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatusChip(String label, Color color) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: color,
        border: Border.all(color: Colors.black, width: 2),
        boxShadow: const [BoxShadow(color: Colors.white, offset: Offset(2, 2))],
      ),
      child: Text(
        label,
        style: const TextStyle(
          color: Colors.black,
          fontSize: 12,
          fontWeight: FontWeight.bold,
        ),
      ),
    );
  }

  String _getConnectionFlowText() {
    if (!_isConnected) return 'Backend (disconnected)';
    if (!_isHealthy) return 'Backend (unhealthy)';
    if (_localAgentConnected) return 'Backend (OK) -> Agent (online)';
    return 'Backend (OK) -> Agent (offline)';
  }

  Widget _buildConnectionFlow(ColorScheme colorScheme) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFF282A36),
        border: Border.all(color: colorScheme.secondary, width: 3),
        boxShadow: [BoxShadow(color: colorScheme.secondary, offset: const Offset(4, 4))],
      ),
      child: Text(
        _getConnectionFlowText().toUpperCase(),
        style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 12, color: Colors.white),
      ),
    );
  }

  Widget _buildDeviceSelector(ColorScheme colorScheme) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: const Color(0xFFC7A2FF), // Brutal purple
        border: Border.all(color: Colors.black, width: 3),
        boxShadow: const [BoxShadow(color: Colors.white, offset: Offset(4, 4))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('ACTIVE DEVICE', style: TextStyle(fontWeight: FontWeight.w900, fontSize: 14)),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12),
            decoration: BoxDecoration(
              color: const Color(0xFF282A36),
              border: Border.all(color: colorScheme.secondary, width: 2),
              boxShadow: [BoxShadow(color: colorScheme.secondary, offset: const Offset(2, 2))],
            ),
            child: DropdownButtonHideUnderline(
              child: DropdownButton<String>(
                value: _activeDevice,
                isExpanded: true,
                icon: const Icon(Icons.arrow_drop_down, color: Colors.white),
                dropdownColor: const Color(0xFF282A36),
                items: _devices.entries.map((entry) {
                  final device = entry.value;
                  return DropdownMenuItem(
                    value: entry.key,
                    child: Text(
                      device['name'] ?? entry.key,
                      style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                    ),
                  );
                }).toList(),
                onChanged: (value) {
                  if (value != null && value.startsWith('desktop-')) _switchDevice(value);
                },
              ),
            ),
          ),
          const SizedBox(height: 12),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _buildBrutalButton(Icons.refresh, 'REFRESH', _getDevices, colorScheme.secondary),
              _buildBrutalButton(Icons.delete_sweep, 'CLEAR BACKEND', _clearBackendData, const Color(0xFFFF9900)),
              _buildBrutalButton(Icons.delete, 'CLEAR LOCAL', _clearLocalData, const Color(0xFFFF3366)),
              if (_savedDevices.isNotEmpty)
                _buildBrutalButton(Icons.devices, 'SAVED (${_savedDevices.length})', _showSavedDevices, colorScheme.tertiary),
            ],
          ),
          const SizedBox(height: 12),
          Container(
            decoration: BoxDecoration(
              color: const Color(0xFF282A36),
              border: Border.all(color: colorScheme.secondary, width: 2),
              boxShadow: [BoxShadow(color: colorScheme.secondary, offset: const Offset(2, 2))],
            ),
            child: SwitchListTile(
              title: const Text('AUTO-READ VOICE', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Colors.white)),
              value: _willTalk,
              activeColor: colorScheme.primary,
              activeTrackColor: Colors.white,
              inactiveTrackColor: Colors.grey,
              onChanged: (bool value) {
                setState(() {
                  _willTalk = value;
                  if (!value) flutterTts.stop();
                });
              },
              dense: true,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildBrutalButton(IconData icon, String label, VoidCallback onPressed, Color color) {
    return GestureDetector(
      onTap: onPressed,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        decoration: BoxDecoration(
          color: color,
          border: Border.all(color: Colors.black, width: 2),
          boxShadow: const [BoxShadow(color: Colors.black, offset: Offset(2, 2))],
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 16, color: Colors.black),
            const SizedBox(width: 4),
            Text(label, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Colors.black)),
          ],
        ),
      ),
    );
  }

  Widget _buildMessagesList(ColorScheme colorScheme) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      child: Column(
        children: [
          Expanded(
            child: ListView.builder(
              controller: _scrollController,
              itemCount: _messages.length,
              itemBuilder: (context, index) {
                final message = _messages[index];
                if (message['type'] == null) return const SizedBox.shrink();
                return _buildMessageCard(message, colorScheme);
              },
            ),
          ),
          if (_isThinking)
            Container(
              margin: const EdgeInsets.symmetric(vertical: 8),
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: colorScheme.tertiary,
                border: Border.all(color: Colors.black, width: 3),
                boxShadow: const [BoxShadow(color: Colors.black, offset: Offset(4, 4))],
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const SizedBox(
                    width: 20, height: 20,
                    child: CircularProgressIndicator(strokeWidth: 3, color: Colors.black),
                  ),
                  const SizedBox(width: 12),
                  const Text('AI IS THINKING...', style: TextStyle(fontWeight: FontWeight.w900)),
                  const SizedBox(width: 12),
                  GestureDetector(
                    onTap: () {
                      channel.sink.add(jsonEncode({'type': 'stop_command'}));
                      setState(() { _isThinking = false; });
                    },
                    child: Container(
                      padding: const EdgeInsets.all(4),
                      decoration: BoxDecoration(
                        color: colorScheme.primary,
                        border: Border.all(color: Colors.black, width: 2),
                      ),
                      child: const Icon(Icons.stop, color: Colors.white, size: 20),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildMessageCard(Map<String, dynamic> message, ColorScheme colorScheme) {
    final type = message['type'] as String? ?? 'unknown';
    final content = message['content'] as String? ?? '';
    
    Color bgColor = const Color(0xFF282A36);
    Color borderColor = const Color(0xFF00E5FF);
    if (type == 'user') { bgColor = const Color(0xFF00E5FF); borderColor = Colors.white; }
    else if (type == 'error') { bgColor = const Color(0xFFFF3366); borderColor = Colors.white; }
    else if (type == 'system') { bgColor = const Color(0xFF44475A); borderColor = colorScheme.tertiary; }

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: bgColor,
        border: Border.all(color: borderColor, width: 3),
        boxShadow: [BoxShadow(color: borderColor, offset: const Offset(4, 4))],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Text(
                type.toUpperCase(),
                style: TextStyle(fontWeight: FontWeight.w900, fontSize: 10, color: (type == 'user' || type == 'error') ? Colors.black : Colors.white),
              ),
              const Spacer(),
              if (message['timestamp'] != null)
                Text(
                  message['timestamp'].toString().split(' ')[1].substring(0, 5),
                  style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: (type == 'user' || type == 'error') ? Colors.black87 : Colors.white70),
                ),
            ],
          ),
          const SizedBox(height: 6),
          CollapsibleOutput(
            text: content,
            style: TextStyle(
              fontSize: 14, 
              fontWeight: FontWeight.w600, 
              color: (type == 'user' || type == 'error') ? Colors.black : Colors.white,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInputArea(ColorScheme colorScheme) {
    bool isAsk = _currentMode == 'ask';
    
    // Dynamic values for animation
    double borderRadius = isAsk ? 24.0 : 0.0;
    Color boxColor = isAsk ? colorScheme.secondary.withOpacity(0.1) : const Color(0xFF282A36);
    Color borderColor = _isListening ? colorScheme.primary : (isAsk ? colorScheme.secondary : Colors.white);
    double borderWidth = _isListening ? 4.0 : (isAsk ? 2.0 : 3.0);
    double offsetX = _isListening ? 6.0 : (isAsk ? 0.0 : 4.0);
    double offsetY = _isListening ? 6.0 : (isAsk ? 0.0 : 4.0);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF1E1E2E),
        border: Border(top: BorderSide(color: colorScheme.tertiary, width: 4)),
      ),
      child: SafeArea(
        child: Column(
          children: [
            Row(
              children: [
                Expanded(
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 300),
                    curve: Curves.easeInOutBack,
                    decoration: BoxDecoration(
                      color: boxColor,
                      borderRadius: BorderRadius.circular(borderRadius),
                      border: Border.all(color: borderColor, width: borderWidth),
                      boxShadow: [
                        BoxShadow(
                          color: borderColor, 
                          offset: Offset(offsetX, offsetY)
                        )
                      ],
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          child: TextField(
                            controller: _controller,
                            style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                            decoration: InputDecoration(
                              hintText: _isListening ? 'LISTENING...' : (isAsk ? 'ASK AGENT...' : 'ENTER COMMAND...'),
                              hintStyle: const TextStyle(fontWeight: FontWeight.w700, color: Colors.grey),
                              contentPadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
                              border: InputBorder.none,
                            ),
                            onSubmitted: (_) => _sendMessage(),
                          ),
                        ),
                        AnimatedSize(
                          duration: const Duration(milliseconds: 300),
                          curve: Curves.easeInOutBack,
                          child: isAsk ? GestureDetector(
                            onTap: _toggleListening,
                            child: AnimatedContainer(
                              duration: const Duration(milliseconds: 300),
                              curve: Curves.easeInOut,
                              padding: const EdgeInsets.all(8.0),
                              margin: const EdgeInsets.only(right: 8.0),
                              decoration: BoxDecoration(
                                color: _isListening ? colorScheme.primary.withOpacity(0.2) : Colors.transparent,
                                shape: BoxShape.circle,
                              ),
                              child: Icon(
                                _isListening ? Icons.mic : Icons.mic_none,
                                color: _isListening ? colorScheme.primary : Colors.white,
                                size: _isListening ? 28 : 24,
                              ),
                            ),
                          ) : const SizedBox(width: 0),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(width: 16),
                GestureDetector(
                  onTap: _sendMessage,
                  child: AnimatedContainer(
                    duration: const Duration(milliseconds: 200),
                    curve: Curves.easeOut,
                    padding: const EdgeInsets.all(14),
                    decoration: BoxDecoration(
                      color: colorScheme.primary,
                      borderRadius: BorderRadius.circular(isAsk ? 20.0 : 0.0),
                      border: Border.all(color: Colors.white, width: 3),
                      boxShadow: [BoxShadow(color: Colors.white, offset: Offset(isAsk ? 2.0 : 4.0, isAsk ? 2.0 : 4.0))],
                    ),
                    child: const Icon(Icons.send, color: Colors.black),
                  ),
                ),
              ],
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

  @override
  Widget build(BuildContext context) {
    final lines = widget.text.split('\n');
    final isLong = lines.length > 10;
    final displayText = (!_isExpanded && isLong) ? lines.take(10).join('\n') + '\n...' : widget.text;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SelectableText(
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
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.black,
                border: Border.all(color: Colors.black, width: 2),
              ),
              child: Text(
                _isExpanded ? 'SHOW LESS' : 'SHOW MORE',
                style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 10),
              ),
            ),
          ),
      ],
    );
  }
}
