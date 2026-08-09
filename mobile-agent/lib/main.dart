import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:google_fonts/google_fonts.dart';
import 'device_identity.dart';
import 'package:uuid/uuid.dart';

// Backend URL from build-time configuration
var backendUrl = String.fromEnvironment('BACKEND_URL', defaultValue: 'wss://voila-voice.onrender.com/ws');

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
  final List<Map<String, dynamic>> _messages = [];
  String _activeDevice = 'laptop-1';
  bool _isConnected = false;
  bool _isHealthy = false;
  bool _localAgentConnected = false;
  String _backendStatus = 'Checking...';
  Timer? _healthCheckTimer;
  Map<String, dynamic> _devices = {};
  String? _currentDeviceId;
  String? _currentDeviceName;
  String _sessionId = '';
  Map<String, dynamic> _savedDevices = {};

  @override
  void initState() {
    super.initState();
    _initializeDeviceIdentity();
    _connectToBackend();
    _startHealthChecks();
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
      channel = WebSocketChannel.connect(
        Uri.parse(backendUrl),
      );
      
      channel.stream.listen((message) {
        setState(() {
          _isConnected = true;
          
          try {
            final jsonResponse = jsonDecode(message);
            
            if (jsonResponse is List) {
              _devices = {};
              for (var device in jsonResponse) {
                final deviceId = device['id'];
                if (deviceId != null && deviceId.startsWith('desktop-')) {
                  // Only show desktop devices, prevent MITM with fingerprint verification
                  final deviceFingerprint = device['fingerprint'];
                  if (deviceFingerprint != null) {
                    _devices[deviceId] = device;
                    // Auto-save desktop devices for quick reconnect
                    DeviceIdentity.saveDevice(deviceId, device);
                    DeviceIdentity.getSavedDevices().then((devices) {
                      _savedDevices = devices;
                      setState(() {});
                    });
                  }
                }
              }
              _messages.add({
                'type': 'system',
                'content': 'Desktop devices updated: ${_devices.length} devices',
                'timestamp': DateTime.now().toString(),
              });
            } else if (jsonResponse is Map && jsonResponse.containsKey('summary')) {
              _messages.add({
                'type': 'response',
                'content': jsonResponse['output'] ?? message,
                'summary': jsonResponse['summary'],
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
    _healthCheckTimer = Timer.periodic(const Duration(seconds: 30), (_) {
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
        
        final deviceCount = healthData['devices'] is int 
            ? healthData['devices'] as int 
            : (healthData['devices'] as List?)?.length ?? 0;
        _localAgentConnected = deviceCount > 0;
        
        setState(() {
          _isHealthy = true;
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
    super.dispose();
  }

  void _sendMessage() async {
    if (_controller.text.isNotEmpty) {
      final deviceInfo = await DeviceIdentity.getDeviceInfo();
      final message = {
        'type': 'command',
        'device_id': _activeDevice,
        'client_device_id': _currentDeviceId,
        'client_device_name': _currentDeviceName,
        'session_id': _sessionId,
        'command': _controller.text,
        'idempotency_key': const Uuid().v4(),
        'client_timestamp': DateTime.now().millisecondsSinceEpoch,
        ...deviceInfo,
      };
      
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
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    
    return Scaffold(
      backgroundColor: colorScheme.surface,
      body: SafeArea(
        child: Column(
          children: [
            _buildHeader(colorScheme),
            _buildConnectionFlow(colorScheme),
            _buildDeviceSelector(colorScheme),
            Expanded(
              child: _buildMessagesList(colorScheme),
            ),
            _buildInputArea(colorScheme),
          ],
        ),
      ),
    );
  }

  Widget _buildHeader(ColorScheme colorScheme) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surface,
        boxShadow: [
          BoxShadow(
            color: colorScheme.shadow.withOpacity(0.1),
            blurRadius: 4,
            offset: const Offset(0, 2),
          ),
        ],
      ),
      child: Row(
        children: [
          Icon(
            Icons.graphic_eq,
            color: colorScheme.primary,
            size: 28,
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Voice CLI',
                  style: TextStyle(
                    fontSize: 20,
                    fontWeight: FontWeight.w600,
                    color: colorScheme.onSurface,
                  ),
                ),
                const SizedBox(height: 4),
                Row(
                  children: [
                    _buildStatusChip(
                      _isConnected ? 'Connected' : 'Disconnected',
                      _isConnected ? Colors.green : Colors.red,
                    ),
                    const SizedBox(width: 8),
                    _buildStatusChip(
                      _backendStatus,
                      _isHealthy ? Colors.blue : Colors.orange,
                    ),
                  ],
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
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 12,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildConnectionFlow(ColorScheme colorScheme) {
    return Container(
      margin: const EdgeInsets.all(16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerHighest,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Column(
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              _buildFlowIndicator('Mobile', true, colorScheme),
              const Icon(Icons.arrow_forward, size: 16, color: Colors.grey),
              _buildFlowIndicator('Backend', _isHealthy, colorScheme),
              const Icon(Icons.arrow_forward, size: 16, color: Colors.grey),
              _buildFlowIndicator('Local Agent', _localAgentConnected, colorScheme),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'Mobile → Backend → Local Agent → Backend → Mobile',
            style: TextStyle(
              fontSize: 11,
              color: colorScheme.onSurfaceVariant,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFlowIndicator(String label, bool isActive, ColorScheme colorScheme) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
      decoration: BoxDecoration(
        color: isActive ? colorScheme.primary : colorScheme.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: isActive ? colorScheme.primary : colorScheme.outline,
          width: 1,
        ),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: isActive ? colorScheme.onPrimary : colorScheme.onSurfaceVariant,
          fontSize: 12,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildDeviceSelector(ColorScheme colorScheme) {
    return Column(
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
          child: Row(
            children: [
              Text(
                'Active Device:',
                style: TextStyle(
                  fontSize: 14,
                  fontWeight: FontWeight.w500,
                  color: colorScheme.onSurface,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Container(
                  padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                  decoration: BoxDecoration(
                    color: colorScheme.surfaceContainerLow,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: colorScheme.outline),
                  ),
                  child: DropdownButtonHideUnderline(
                    child: DropdownButton<String>(
                      value: _activeDevice,
                      isExpanded: true,
                      items: _devices.entries.map((entry) {
                        final device = entry.value;
                        final isLocked = device['locked'] == true;
                        return DropdownMenuItem(
                          value: entry.key,
                          child: Row(
                            children: [
                              Text(device['name'] ?? entry.key),
                              if (isLocked) ...[
                                const SizedBox(width: 8),
                                Icon(Icons.lock, size: 16, color: colorScheme.error),
                              ],
                            ],
                          ),
                        );
                      }).toList(),
                      onChanged: (value) {
                        if (value != null) {
                          _switchDevice(value);
                        }
                      },
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              IconButton(
                onPressed: _getDevices,
                icon: const Icon(Icons.refresh),
                tooltip: 'Refresh Devices',
              ),
            ],
          ),
        ),
        if (_savedDevices.isNotEmpty)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                Text(
                  'Saved Devices (${_savedDevices.length})',
                  style: TextStyle(
                    fontSize: 12,
                    fontWeight: FontWeight.w500,
                    color: colorScheme.onSurfaceVariant,
                  ),
                ),
                const Spacer(),
                TextButton.icon(
                  onPressed: _showSavedDevices,
                  icon: const Icon(Icons.devices, size: 16),
                  label: const Text('Manage'),
                  style: TextButton.styleFrom(
                    textStyle: const TextStyle(fontSize: 12),
                  ),
                ),
              ],
            ),
          ),
      ],
    );
  }

  Widget _buildMessagesList(ColorScheme colorScheme) {
    return Container(
      margin: const EdgeInsets.symmetric(horizontal: 16),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: colorScheme.surfaceContainerLow,
        borderRadius: BorderRadius.circular(12),
      ),
      child: ListView.builder(
        controller: _scrollController,
        itemCount: _messages.length,
        itemBuilder: (context, index) {
          final message = _messages[index];
          final type = message['type'] as String?;
          final content = message['content'] as String?;
          
          if (type == null || content == null) {
            return const SizedBox.shrink();
          }
          
          return _buildMessageCard(message, colorScheme);
        },
      ),
    );
  }

  Widget _buildMessageCard(Map<String, dynamic> message, ColorScheme colorScheme) {
    final type = message['type'] as String;
    final content = message['content'] as String;
    
    Color? bgColor;
    IconData? icon;
    
    switch (type) {
      case 'user':
        bgColor = colorScheme.primaryContainer;
        icon = Icons.person;
        break;
      case 'response':
        bgColor = colorScheme.tertiaryContainer;
        icon = Icons.check_circle;
        break;
      case 'error':
        bgColor = colorScheme.errorContainer;
        icon = Icons.error;
        break;
      case 'system':
        bgColor = colorScheme.surfaceContainer;
        icon = Icons.info;
        break;
      default:
        bgColor = colorScheme.surface;
        icon = Icons.message;
    }
    
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      color: bgColor,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18, color: colorScheme.onSurfaceVariant),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    content,
                    style: TextStyle(
                      fontSize: 14,
                      color: colorScheme.onSurface,
                    ),
                  ),
                ),
              ],
            ),
            if (message.containsKey('summary') && message['summary'] != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: colorScheme.secondaryContainer,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        Icons.auto_awesome,
                        size: 16,
                        color: colorScheme.onSecondaryContainer,
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          message['summary']?.toString() ?? '',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: colorScheme.onSecondaryContainer,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 4),
            Text(
              message['timestamp']?.toString() ?? '',
              style: TextStyle(
                fontSize: 10,
                color: colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
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
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _controller,
              decoration: InputDecoration(
                hintText: 'Enter command...',
                hintStyle: TextStyle(color: colorScheme.onSurfaceVariant),
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
                  icon: const Icon(Icons.mic),
                  onPressed: () {
                    ScaffoldMessenger.of(context).showSnackBar(
                      const SnackBar(content: Text('Speech-to-text coming soon!')),
                    );
                  },
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
    );
  }
}
