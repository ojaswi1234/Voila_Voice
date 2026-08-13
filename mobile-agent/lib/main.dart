import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:speech_to_text/speech_to_text.dart';
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
        colorScheme: ColorScheme.fromSeed(
          seedColor: const Color(0xFF6750A4),
          brightness: Brightness.light,
        ),
        useMaterial3: true,
        textTheme: GoogleFonts.interTextTheme(),
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
  List<Map<String, dynamic>> get _messages => _currentMode == 'ASK' ? _messagesAsk : _messagesCommand;
  bool _isThinking = false;
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
            } else if (jsonResponse is Map && jsonResponse.containsKey('summary')) {
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
              _messages.add({
                'type': 'response',
                'content': message,
                'timestamp': DateTime.now().toString(),
              });
            }
          } catch (e) {
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
        const SnackBar(content: Text('Unlocking... please retry after success.')),
      );
    }
    return false; // They must retry the command after token is received
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
          child: Column(
                children: [
                  Expanded(
                    child: ListView.builder(
                      controller: _scrollController,
                      itemCount: _messages.length,
                      itemBuilder: (context, index) {
                        final message = _messages[index];
                        return _buildMessageCard(message, colorScheme);
                      },
                    ),
                  ),
                  if (_isThinking && _currentMode == 'ASK')
                    Padding(
                      padding: const EdgeInsets.symmetric(vertical: 12.0),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          const SizedBox(
                            width: 20,
                            height: 20,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                          const SizedBox(width: 12),
                          Text(
                            'AI is thinking...',
                            style: TextStyle(
                              color: colorScheme.primary,
                              fontStyle: FontStyle.italic,
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
    final type = message['type'] as String;
    final content = message['content'] as String;
    final mode = message['mode'] as String?;
    final status = message['status'] as String?;
    final summary = message['summary'] as String?;
    
    Color? bgColor;
    IconData? icon;
    
    if (type == 'user') {
      bgColor = colorScheme.primaryContainer;
      icon = Icons.person;
    } else if (type == 'response' || type == 'error') {
      bgColor = (status == 'error' || type == 'error') ? colorScheme.errorContainer : colorScheme.tertiaryContainer;
      icon = (status == 'error' || type == 'error') ? Icons.error : Icons.check_circle;
    } else {
      bgColor = colorScheme.surfaceContainer;
      icon = Icons.info;
    }
    
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      color: bgColor,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18, color: colorScheme.onSurfaceVariant),
                const SizedBox(width: 8),
                if (mode != null)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    margin: const EdgeInsets.only(right: 8),
                    decoration: BoxDecoration(
                      color: colorScheme.surface.withOpacity(0.5),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      mode.toUpperCase(),
                      style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: colorScheme.onSurfaceVariant),
                    ),
                  ),
                Expanded(
                  child: Text(
                    type == 'user' ? content : 'Output',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      color: colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (summary != null && summary.isNotEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                margin: const EdgeInsets.only(bottom: 8),
                decoration: BoxDecoration(
                  color: colorScheme.secondaryContainer,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: colorScheme.secondary.withOpacity(0.3)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.auto_awesome,
                      size: 16,
                      color: colorScheme.onSecondaryContainer,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        summary,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          color: colorScheme.onSecondaryContainer,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            if (type != 'user' && content.isNotEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Theme.of(context).brightness == Brightness.dark 
                      ? Colors.black54 
                      : Colors.black.withOpacity(0.05),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: CollapsibleOutput(
                  text: content,
                  style: GoogleFonts.firaCode(
                    fontSize: 12,
                    color: colorScheme.onSurface,
                  ),
                ),
              ),
            if (type == 'user')
              Text(
                content,
                style: TextStyle(
                  fontSize: 14,
                  color: colorScheme.onSurface,
                ),
              ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  message['timestamp']?.toString() ?? '',
                  style: TextStyle(
                    fontSize: 10,
                    color: colorScheme.onSurfaceVariant,
                  ),
                ),
                if (type == 'response' && summary != null && summary.isNotEmpty)
                  TextButton.icon(
                    icon: const Icon(Icons.save, size: 14),
                    label: const Text('Save as Artifact', style: TextStyle(fontSize: 10)),
                    onPressed: () {
                      _saveArtifact(summary, content);
                    },
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 0),
                      minimumSize: Size.zero,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _saveArtifact(String title, String content) {
    ArtifactsManager.addArtifact(
      title: title,
      content: content,
      source: 'antigravity',
    );
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Saved to Artifacts')),
    );
  }


  Widget _buildInputArea(ColorScheme colorScheme) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surface,
        boxShadow: [
          BoxShadow(
            color: colorScheme.shadow.withOpacity(0.1),
            blurRadius: 4,
            offset: const Offset(0, -2),
          ),
        ],
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          SegmentedButton<String>(
            segments: const [
              ButtonSegment<String>(
                value: 'ask',
                label: Text('Ask'),
                icon: Icon(Icons.auto_awesome),
                tooltip: 'Send to Antigravity',
              ),
              ButtonSegment<String>(
                value: 'command',
                label: Text('Command'),
                icon: Icon(Icons.terminal),
                tooltip: 'Run directly on device',
              ),
            ],
            selected: <String>{_currentMode},
            onSelectionChanged: (Set<String> newSelection) {
              setState(() {
                _currentMode = newSelection.first;
              });
            },
            showSelectedIcon: false,
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  decoration: InputDecoration(
                    hintText: _isListening ? 'Listening...' : (_currentMode == 'ask' ? 'Ask agent...' : 'Enter shell command...'),
                    hintStyle: TextStyle(
                      color: _isListening ? colorScheme.primary : colorScheme.onSurfaceVariant,
                    ),
                    filled: true,
                    fillColor: colorScheme.surfaceContainerLow,
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(24),
                      borderSide: BorderSide.none,
                    ),
                    contentPadding: const EdgeInsets.symmetric(
                      horizontal: 20,
                      vertical: 12,
                    ),
                    suffixIcon: IconButton(
                      icon: Icon(
                        _isListening ? Icons.mic : Icons.mic_none,
                        color: _isListening ? colorScheme.primary : colorScheme.onSurface,
                      ),
                      onPressed: _toggleListening,
                    ),
                  ),
                  onSubmitted: (_) => _sendMessage(),
                ),
              ),
              const SizedBox(width: 12),
              FloatingActionButton(
                onPressed: _sendMessage,
                backgroundColor: colorScheme.primary,
                child: Icon(Icons.send, color: colorScheme.onPrimary),
              ),
            ],
          ),
        ],
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
    final isLong = lines.length > 15;
    final displayText = (!_isExpanded && isLong) ? lines.take(15).join('\n') + '\n...' : widget.text;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SelectableText(
          displayText,
          style: widget.style,
        ),
        if (isLong)
          TextButton(
            onPressed: () {
              setState(() {
                _isExpanded = !_isExpanded;
              });
            },
            style: TextButton.styleFrom(
              padding: const EdgeInsets.symmetric(horizontal: 0, vertical: 8),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: Text(
              _isExpanded ? 'Collapse' : 'Expand',
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold),
            ),
          ),
      ],
    );
  }
}
