import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add _sessionToken
content = content.replace("String _sessionId = '';", "String _sessionId = '';\n  String _sessionToken = '';")

# 2. Extract _promptSecurityPhrase from _clearBackendData
prompt_func = """
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
"""

# Insert it before _clearBackendData
clear_func_start = "void _clearBackendData() async {"
content = content.replace(clear_func_start, prompt_func + "\n  " + clear_func_start)

# Rewrite _clearBackendData to use it
old_clear = """  void _clearBackendData() async {
    final securityPhrase = await showDialog<String>(
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
    
    if (securityPhrase == null || securityPhrase!.isEmpty) {
      return;
    }"""
new_clear = """  void _clearBackendData() async {
    if (!await _ensureUnlocked()) return;
    final securityPhrase = _securityPhrase; // still using it for clear data just in case, but token is better
"""
content = content.replace(old_clear, new_clear)

# 3. Handle session token in WebSocket
ws_handler_old = """            if (jsonResponse is List) {"""
ws_handler_new = """            if (jsonResponse is Map && jsonResponse['type'] == 'session') {
              setState(() {
                _sessionToken = jsonResponse['session_token'];
              });
              if (mounted) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text('Session unlocked successfully.')),
                );
              }
              return;
            } else if (jsonResponse is List) {"""
content = content.replace(ws_handler_old, ws_handler_new)

# Handle Unauthorized
err_handler_old = """            } else if (message.contains('ERROR:')) {"""
err_handler_new = """            } else if (message.contains('ERROR:')) {
              if (message.contains('Unauthorized')) {
                _sessionToken = ''; // Clear expired or invalid token
              }
"""
content = content.replace(err_handler_old, err_handler_new + err_handler_old.replace('            } else if (message.contains(\'ERROR:\')) {', ''))

# 4. Attach token to command
send_msg_old = """      final message = {
        'type': 'command',
        'device_id': _activeDevice,
        'client_device_id': _currentDeviceId,
        'client_device_name': _currentDeviceName,
        'session_id': _sessionId,
        'command': _controller.text,
        'idempotency_key': const Uuid().v4(),
        'client_timestamp': DateTime.now().millisecondsSinceEpoch,
        ...deviceInfo,
      };"""
send_msg_new = """      if (!await _ensureUnlocked()) return;

      final message = {
        'type': 'command',
        'device_id': _activeDevice,
        'client_device_id': _currentDeviceId,
        'client_device_name': _currentDeviceName,
        'session_id': _sessionId,
        'session_token': _sessionToken,
        'command': _controller.text,
        'idempotency_key': const Uuid().v4(),
        'client_timestamp': DateTime.now().millisecondsSinceEpoch,
        ...deviceInfo,
      };"""
content = content.replace(send_msg_old, send_msg_new)

# Also add token to switch_device, lock_device, unlock_device, clear_all_devices
content = content.replace("'type': 'switch_device',", "'type': 'switch_device',\n        'session_token': _sessionToken,")
content = content.replace("'type': 'lock_device',", "'type': 'lock_device',\n        'session_token': _sessionToken,")
content = content.replace("'type': 'unlock_device',", "'type': 'unlock_device',\n        'session_token': _sessionToken,")
content = content.replace("'type': 'clear_all_devices',", "'type': 'clear_all_devices',\n        'session_token': _sessionToken,")

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
