import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    code = f.read()

# 1. Add TTS import
if "import 'package:flutter_tts/flutter_tts.dart';" not in code:
    code = code.replace("import 'package:speech_to_text/speech_to_text.dart' as stt;", "import 'package:speech_to_text/speech_to_text.dart' as stt;\nimport 'package:flutter_tts/flutter_tts.dart';")

# 2. Add properties
if "FlutterTts flutterTts = FlutterTts();" not in code:
    code = code.replace(
        "bool _isThinking = false;",
        "bool _isThinking = false;\n  bool _willTalk = true;\n  FlutterTts flutterTts = FlutterTts();"
    )

# 3. Add _initTts() to initState
if "_initTts()" not in code:
    init_tts = '''
  Future<void> _initTts() async {
    await flutterTts.setLanguage("en-US");
    await flutterTts.setSpeechRate(0.55);
    await flutterTts.setVolume(1.0);
    await flutterTts.setPitch(1.0);
  }
'''
    code = code.replace("void initState() {\n    super.initState();", "void initState() {\n    super.initState();\n    _initTts();")
    code = code.replace("  Future<void> _initSpeech() async {", init_tts + "\n  Future<void> _initSpeech() async {")

# 4. Modify channel.stream.listen logic
# We must clear _isThinking = false ONLY on final responses or errors, not on "queued".
listener_replacement = '''            if (jsonResponse is Map && jsonResponse['type'] == 'queued') {
              // Task queued! Keep loader spinning.
              return;
            } else if (jsonResponse is Map && jsonResponse.containsKey('summary')) {
              setState(() {
                _isThinking = false;
              });
              if (_willTalk) {
                flutterTts.speak(jsonResponse['summary']);
              }
'''
code = code.replace("            } else if (jsonResponse is Map && jsonResponse.containsKey('summary')) {", listener_replacement)

# Set isThinking to false on error strings
code = code.replace("            } else if (message.contains('ERROR:')) {", "            } else if (message.contains('ERROR:')) {\n              setState(() { _isThinking = false; });")

# Also on generic responses
code = code.replace(
'''            } else {
              _messages.add({
                'type': 'response',''',
'''            } else {
              setState(() { _isThinking = false; });
              _messages.add({
                'type': 'response','''
)

# And in catch block
code = code.replace(
'''          } catch (e) {
            _messages.add({
              'type': 'response',''',
'''          } catch (e) {
            setState(() { _isThinking = false; });
            _messages.add({
              'type': 'response','''
)

# And in onError
code = code.replace(
'''      }, onError: (error) {
        setState(() {
          _isConnected = false;''',
'''      }, onError: (error) {
        setState(() {
          _isThinking = false;
          _isConnected = false;'''
)

# 5. Fix _sendMessage to set _isThinking = true
code = code.replace(
'''      _messages.add({
        'type': 'system',
        'content': command,
        'timestamp': DateTime.now().toString(),
      });
''',
'''      _messages.add({
        'type': 'system',
        'content': command,
        'timestamp': DateTime.now().toString(),
      });
      setState(() { _isThinking = true; });
'''
)

# 6. Fix _isThinking UI block
code = code.replace(
'''          if (_isThinking && _currentMode.toUpperCase() == 'ASK')
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
            ),''',
'''          if (_isThinking)
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
                  const SizedBox(width: 12),
                  IconButton(
                    icon: Icon(Icons.stop_circle, color: colorScheme.error),
                    onPressed: () {
                       channel.sink.add(jsonEncode({'type': 'stop_command'}));
                       setState(() { _isThinking = false; });
                    },
                    tooltip: 'Stop AI Task',
                  ),
                ],
              ),
            ),'''
)

# 7. Add "Will Talk" toggle to drawer or app bar
# The user asked for "a seperate section in which add a toggle 'Will talk'"
toggle_widget = '''
          const Divider(),
          SwitchListTile(
            title: const Text('Will Talk (Auto-read responses)'),
            value: _willTalk,
            onChanged: (bool value) {
              setState(() {
                _willTalk = value;
                if (!value) flutterTts.stop();
              });
            },
            secondary: const Icon(Icons.record_voice_over),
          ),
'''
# Let's insert it into the Drawer UI (which already has DeviceIdentity logic)
if 'const Divider(),\n          SwitchListTile(' not in code:
    code = code.replace(
'''          const Divider(),
          ListTile(
            title: const Text('Connection Status'),''',
toggle_widget + '''          const Divider(),
          ListTile(
            title: const Text('Connection Status'),'''
    )

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(code)

print("Flutter app patched!")
