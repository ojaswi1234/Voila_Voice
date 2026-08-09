import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:web_socket_channel/web_socket_channel.dart';

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
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(seedColor: Colors.deepPurple),
        useMaterial3: true,
      ),
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
  final List<Map<String, dynamic>> _messages = [];
  String _activeDevice = 'laptop-1';
  bool _isConnected = false;
  bool _isHealthy = false;
  bool _localAgentConnected = false;
  String _backendStatus = 'Checking...';
  Timer? _healthCheckTimer;
  Map<String, dynamic> _devices = {};

  @override
  void initState() {
    super.initState();
    _connectToBackend();
    _startHealthChecks();
  }

  void _connectToBackend() {
    try {
      // Use backend URL from build-time configuration
      channel = WebSocketChannel.connect(
        Uri.parse(backendUrl),
      );
      
      channel.stream.listen((message) {
        setState(() {
          _isConnected = true;
          
          // Try to parse as JSON for enhanced responses
          try {
            final jsonResponse = jsonDecode(message);
            
            // Handle device list response
            if (jsonResponse is List) {
              _devices = {};
              for (var device in jsonResponse) {
                _devices[device['id']] = device;
              }
              _messages.add({
                'type': 'system',
                'content': 'Device list updated: ${_devices.length} devices',
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
          
          // Trigger health check after successful connection
          _checkBackendHealth();
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
        
        // Auto-reconnect after delay
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
    // Check health every 30 seconds
    _healthCheckTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      _checkBackendHealth();
    });
    
    // Initial check
    _checkBackendHealth();
  }

  Future<void> _checkBackendHealth() async {
    try {
      // Convert WebSocket URL to HTTP URL for health check
      String httpUrl = backendUrl;
      httpUrl = httpUrl.replaceAll('ws://', 'http://');
      httpUrl = httpUrl.replaceAll('wss://', 'https://');
      httpUrl = httpUrl.replaceAll('/ws', '/health');
      
      final response = await http.get(Uri.parse(httpUrl));
      
      if (response.statusCode == 200) {
        final healthData = jsonDecode(response.body);
        
        // Check if local agents are connected
        final deviceCount = healthData['devices'] as int;
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

  @override
  void dispose() {
    _healthCheckTimer?.cancel();
    channel.sink.close();
    _controller.dispose();
    super.dispose();
  }

  void _sendMessage() {
    if (_controller.text.isNotEmpty) {
      final message = {
        'type': 'command',
        'device_id': _activeDevice,
        'command': _controller.text,
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
    }
  }

  void _switchDevice(String deviceId) {
    final message = {
      'type': 'switch_device',
      'device_id': deviceId,
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

  void _getDevices() {
    final message = {
      'type': 'get_devices',
    };
    
    channel.sink.add(jsonEncode(message));
  }

  void _lockDevice(String deviceId) {
    final message = {
      'type': 'lock_device',
      'device_id': deviceId,
    };
    
    channel.sink.add(jsonEncode(message));
    setState(() {
      _messages.add({
        'type': 'system',
        'content': 'Attempting to lock device: $deviceId',
        'timestamp': DateTime.now().toString(),
      });
    });
  }

  void _unlockDevice(String deviceId) {
    final message = {
      'type': 'unlock_device',
      'device_id': deviceId,
    };
    
    channel.sink.add(jsonEncode(message));
    setState(() {
      _messages.add({
        'type': 'system',
        'content': 'Attempting to unlock device: $deviceId',
        'timestamp': DateTime.now().toString(),
      });
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Theme.of(context).colorScheme.inversePrimary,
        title: Row(
          children: [
            const Text('Voice CLI Remote'),
            const Spacer(),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: _isConnected ? Colors.green : Colors.red,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                _isConnected ? 'Connected' : 'Disconnected',
                style: const TextStyle(color: Colors.white, fontSize: 12),
              ),
            ),
            const SizedBox(width: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
              decoration: BoxDecoration(
                color: _isHealthy ? Colors.blue : Colors.orange,
                borderRadius: BorderRadius.circular(12),
              ),
              child: Text(
                _backendStatus,
                style: const TextStyle(color: Colors.white, fontSize: 10),
              ),
            ),
          ],
        ),
      ),
      body: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Column(
          children: [
            // Device switcher
            Row(
              children: [
                const Text('Active Device: ', style: TextStyle(fontWeight: FontWeight.bold)),
                DropdownButton<String>(
                  value: _activeDevice,
                  items: _devices.entries.map((entry) {
                    final device = entry.value;
                    final isLocked = device['locked'] == true;
                    return DropdownMenuItem(
                      value: entry.key,
                      child: Row(
                        children: [
                          Text(device['name']),
                          if (isLocked) ...[
                            const SizedBox(width: 8),
                            Icon(Icons.lock, size: 16, color: Colors.red),
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
                const Spacer(),
                ElevatedButton(
                  onPressed: _getDevices,
                  child: const Text('Refresh Devices'),
                ),
                ElevatedButton(
                  onPressed: _checkBackendHealth,
                  child: const Text('Check Health'),
                ),
                ElevatedButton(
                  onPressed: () => _lockDevice(_activeDevice),
                  child: const Text('Lock Device'),
                ),
                ElevatedButton(
                  onPressed: () => _unlockDevice(_activeDevice),
                  child: const Text('Unlock Device'),
                ),
              ],
            ),
            const Divider(),
            
            // Connection flow indicator
            Container(
              padding: const EdgeInsets.all(8),
              decoration: BoxDecoration(
                color: Colors.grey[100],
                borderRadius: BorderRadius.circular(8),
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      _buildFlowIndicator('Mobile', true), // Mobile is always running
                      const Icon(Icons.arrow_forward, size: 16),
                      _buildFlowIndicator('Backend (Render)', _isHealthy),
                      const Icon(Icons.arrow_forward, size: 16),
                      _buildFlowIndicator('Local Agent', _localAgentConnected),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Complete Chain: Mobile → Backend → Local Agent → Backend → Mobile',
                    style: const TextStyle(fontSize: 10, color: Colors.grey),
                  ),
                ],
              ),
            ),
            const Divider(),
            
            // Messages list
            Expanded(
              child: ListView.builder(
                itemCount: _messages.length,
                itemBuilder: (context, index) {
                  final message = _messages[index];
                  final type = message['type'] as String;
                  final content = message['content'] as String;
                  
                  Color? bgColor;
                  IconData? icon;
                  
                  switch (type) {
                    case 'user':
                      bgColor = Colors.blue[100];
                      icon = Icons.person;
                      break;
                    case 'response':
                      bgColor = Colors.green[100];
                      icon = Icons.check_circle;
                      break;
                    case 'error':
                      bgColor = Colors.red[100];
                      icon = Icons.error;
                      break;
                    case 'system':
                      bgColor = Colors.grey[200];
                      icon = Icons.info;
                      break;
                    default:
                      bgColor = Colors.white;
                      icon = Icons.message;
                  }
                  
                  return Card(
                    color: bgColor,
                    margin: const EdgeInsets.symmetric(vertical: 4),
                    child: ListTile(
                      leading: Icon(icon),
                      title: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            content,
                            style: const TextStyle(fontSize: 14),
                          ),
                          if (message.containsKey('summary') && message['summary'] != null)
                            Padding(
                              padding: const EdgeInsets.only(top: 8.0),
                              child: Container(
                                padding: const EdgeInsets.all(8),
                                decoration: BoxDecoration(
                                  color: Colors.amber[50],
                                  borderRadius: BorderRadius.circular(8),
                                  border: Border.all(color: Colors.amber),
                                ),
                                child: Row(
                                  children: [
                                    const Icon(Icons.auto_awesome, size: 16, color: Colors.amber),
                                    const SizedBox(width: 4),
                                    Expanded(
                                      child: Text(
                                        message['summary'] as String,
                                        style: const TextStyle(
                                          fontSize: 12,
                                          fontWeight: FontWeight.bold,
                                          color: Colors.amber,
                                        ),
                                      ),
                                    ),
                                  ],
                                ),
                              ),
                            ),
                        ],
                      ),
                      subtitle: Text(
                        message['timestamp'] as String,
                        style: const TextStyle(fontSize: 10, color: Colors.grey),
                      ),
                    ),
                  );
                },
              ),
            ),
            const Divider(),
            
            // Input field
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _controller,
                    decoration: InputDecoration(
                      hintText: 'Enter command (e.g., "start the local development server")',
                      border: const OutlineInputBorder(),
                      suffixIcon: IconButton(
                        icon: const Icon(Icons.mic),
                        onPressed: () {
                          // TODO: Implement speech-to-text
                          ScaffoldMessenger.of(context).showSnackBar(
                            const SnackBar(content: Text('Speech-to-text coming soon!')),
                          );
                        },
                      ),
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: _sendMessage,
                  child: const Text('Send'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildFlowIndicator(String label, bool isActive) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: isActive ? Colors.green : Colors.grey,
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        label,
        style: const TextStyle(color: Colors.white, fontSize: 10),
      ),
    );
  }
}
