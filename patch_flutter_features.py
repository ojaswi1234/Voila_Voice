import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Update _messages declaration
code = code.replace(
    "final List<Map<String, dynamic>> _messages = [];",
    "final List<Map<String, dynamic>> _messagesCommand = [];\n  final List<Map<String, dynamic>> _messagesAsk = [];\n  List<Map<String, dynamic>> get _messages => _currentMode == 'ASK' ? _messagesAsk : _messagesCommand;\n  bool _isThinking = false;"
)

# 2. Add _stopCommand function
stop_func = '''
  void _stopCommand() {
    if (!_isConnected || _activeDevice.isEmpty) return;
    
    final message = {
      'type': 'stop_command',
      'device_id': _activeDevice,
      'client_id': _clientId,
      'session_id': _sessionId,
      'session_token': _sessionToken,
      'client_timestamp': DateTime.now().millisecondsSinceEpoch,
    };
    channel.sink.add(jsonEncode(message));
    setState(() {
      _isThinking = false;
      _messages.add({
        'type': 'system',
        'content': 'Stopping command execution...',
        'timestamp': DateTime.now().toString(),
      });
    });
    _scrollToBottom();
  }
'''
if "void _stopCommand" not in code:
    code = code.replace("void _sendMessage() {", stop_func + "\n  void _sendMessage() {")

# 3. Set _isThinking = true when sending message
code = code.replace(
    "channel.sink.add(jsonEncode(message));\n        setState(() {\n          _messages.add({",
    "channel.sink.add(jsonEncode(message));\n        setState(() {\n          _isThinking = true;\n          _messages.add({"
)

# 4. Set _isThinking = false when receiving messages (in handleWebSocket)
code = code.replace(
    "_messages.add({\n                  'type': 'response',\n                  'content': jsonResponse['output'] ?? message,",
    "_isThinking = false;\n                _messages.add({\n                  'type': 'response',\n                  'content': jsonResponse['output'] ?? message,"
)
code = code.replace(
    "_messages.add({\n                  'type': 'error',\n                  'content': message.replace('ERROR: ', ''),",
    "_isThinking = false;\n                _messages.add({\n                  'type': 'error',\n                  'content': message.replace('ERROR: ', ''),"
)
code = code.replace(
    "_messages.add({\n                  'type': 'response',\n                  'content': message,\n                  'timestamp': DateTime.now().toString(),\n                });\n              }\n            } catch (e) {\n              _messages.add({\n                'type': 'response',\n                'content': message,",
    "_isThinking = false;\n                _messages.add({\n                  'type': 'response',\n                  'content': message,\n                  'timestamp': DateTime.now().toString(),\n                });\n              }\n            } catch (e) {\n              _isThinking = false;\n              _messages.add({\n                'type': 'response',\n                'content': message,"
)

# 5. Add Stop button instead of Send button if _isThinking
send_btn_pattern = r"(IconButton\(\s*icon: const Icon\(Icons.send\),\s*onPressed: _sendMessage,\s*\))"
new_send_btn = r'''_isThinking
                        ? IconButton(
                            icon: const Icon(Icons.stop_circle_outlined, size: 32),
                            color: colorScheme.error,
                            onPressed: _stopCommand,
                          )
                        : \1'''
code = re.sub(send_btn_pattern, new_send_btn, code)

# 6. Add Loader to the chat window
chat_list_pattern = r"(child: ListView\.builder\([\s\S]*?itemBuilder: \(context, index\) \{[\s\S]*?return _buildMessageCard\(message, colorScheme\);\n\s*},\n\s*\),)"
new_chat_list = r'''child: Column(
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
              ),'''
code = re.sub(chat_list_pattern, new_chat_list, code)

# 7. Add Mode switch trigger to scroll to bottom since list changes
mode_switch_pattern = r"setState\(\(\) \{\n\s*_currentMode = mode;\n\s*\}\);"
new_mode_switch = r"setState(() {\n                            _currentMode = mode;\n                          });\n                          Future.delayed(const Duration(milliseconds: 50), _scrollToBottom);"
code = re.sub(mode_switch_pattern, new_mode_switch, code)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(code)

print("Patched flutter app successfully")
