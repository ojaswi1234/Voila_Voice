import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Add _currentMode
mode_state = "  String _currentMode = 'ask';"
content = content.replace("  String _sessionToken = '';", "  String _sessionToken = '';\n" + mode_state)

# 2. Add mode to sendMessage
send_msg_old = """      final message = {
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
send_msg_new = """      final message = {
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
        ...deviceInfo,
      };"""
content = content.replace(send_msg_old, send_msg_new)

# 3. Add pill segmented control UI in _buildInputArea
# Look for where _buildInputArea is or where TextField is
# In Flutter, input area usually has a TextField and IconButton
# Let's see if we can find it.
