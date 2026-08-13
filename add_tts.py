import re

with open('mobile-agent/pubspec.yaml', 'r', encoding='utf-8') as f:
    pubspec = f.read()

if 'flutter_tts:' not in pubspec:
    pubspec = pubspec.replace('dependencies:\n  flutter:\n    sdk: flutter', 'dependencies:\n  flutter:\n    sdk: flutter\n  flutter_tts: ^3.8.5')
    with open('mobile-agent/pubspec.yaml', 'w', encoding='utf-8') as f:
        f.write(pubspec)
    print("Added flutter_tts")
else:
    print("Already added flutter_tts")
