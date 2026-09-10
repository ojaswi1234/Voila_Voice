import re
with open('lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Imports
imports = '''
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
'''
content = content.replace("import 'dart:async';", "import 'dart:async';" + imports)

# 2. Main replacement
bg_handler = '''
@pragma('vm:entry-point')
Future<void> _firebaseMessagingBackgroundHandler(RemoteMessage message) async {
  await Firebase.initializeApp();
  debugPrint("Handling a background message: ${message.messageId}");
}
'''
main_replacement = bg_handler + '''
void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await Firebase.initializeApp();
  FirebaseMessaging.onBackgroundMessage(_firebaseMessagingBackgroundHandler);
  
  runApp(const VoiceCliApp());
}
'''
content = re.sub(r'void main\(\) \{\s*runApp\(const VoiceCliApp\(\)\);\s*\}', main_replacement, content)

# 3. Add FCM methods inside _VoiceHomePageState
fcm_methods = '''
  String? _fcmToken;
  final FlutterLocalNotificationsPlugin _flutterLocalNotificationsPlugin = FlutterLocalNotificationsPlugin();

  Future<void> _setupFCM() async {
    NotificationSettings settings = await FirebaseMessaging.instance.requestPermission(
      alert: true, announcement: false, badge: true, carPlay: false, criticalAlert: false, provisional: false, sound: true,
    );
    debugPrint('User granted permission: ${settings.authorizationStatus}');

    const AndroidNotificationChannel channel = AndroidNotificationChannel(
      'security_alerts_channel', 
      'High Severity Security Alerts', 
      description: 'This channel is used for important security alerts.',
      importance: Importance.max,
    );
    await _flutterLocalNotificationsPlugin
        .resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>()
        ?.createNotificationChannel(channel);

    String? token = await FirebaseMessaging.instance.getToken();
    if (token != null) {
      _fcmToken = token;
      _sendFCMToken(token);
    }

    FirebaseMessaging.instance.onTokenRefresh.listen((newToken) {
      _fcmToken = newToken;
      _sendFCMToken(newToken);
    });

    FirebaseMessaging.onMessageOpenedApp.listen((RemoteMessage message) {
      if (message.data['type'] == 'security_alert') {
        _showSecurityAlerts();
      }
    });

    RemoteMessage? initialMessage = await FirebaseMessaging.instance.getInitialMessage();
    if (initialMessage != null && initialMessage.data['type'] == 'security_alert') {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _showSecurityAlerts();
      });
    }
  }

  void _sendFCMToken(String token) {
    if (_activeDevice.isNotEmpty && _isConnected) {
      channel.sink.add(jsonEncode({
        'type': 'register_fcm_token',
        'device_id': _activeDevice,
        'token': token,
        'session_token': _sessionToken,
      }));
    }
  }
'''

# Note: Since there is a with WidgetsBindingObserver in the class, it's easier to just insert after it
content = content.replace('  void initState() {', fcm_methods + '\n  @override\n  void initState() {', 1)

# 4. Call _setupFCM in initState and session unlock
content = content.replace('    _initializeSpeech();\n  }', '    _initializeSpeech();\n    _setupFCM();\n  }')
content = content.replace('                _sessionExpiresAt = sessionExpiresAt;\n              });', '                _sessionExpiresAt = sessionExpiresAt;\n              });\n              if (_fcmToken != null) _sendFCMToken(_fcmToken!);')

with open('lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print('Patched main.dart')
