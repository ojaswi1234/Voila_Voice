import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';
import 'package:device_info_plus/device_info_plus.dart';
import 'package:uuid/uuid.dart';

class DeviceIdentity {
  static final _storage = FlutterSecureStorage();
  static final _uuid = Uuid();
  static String? _cachedDeviceId;
  static String? _cachedDeviceName;

  static Future<String> getDeviceId() async {
    if (_cachedDeviceId != null) {
      return _cachedDeviceId!;
    }

    String? deviceId = await _storage.read(key: 'device_id');
    if (deviceId != null) {
      _cachedDeviceId = deviceId;
      return deviceId;
    }

    // Use mobile- prefix for mobile devices with UUID
    deviceId = 'mobile-${_uuid.v4().substring(0, 8)}';
    await _storage.write(key: 'device_id', value: deviceId);
    _cachedDeviceId = deviceId;
    return deviceId;
  }

  static Future<String> getDeviceName() async {
    if (_cachedDeviceName != null) {
      return _cachedDeviceName!;
    }

    String? deviceName = await _storage.read(key: 'device_name');
    if (deviceName != null) {
      _cachedDeviceName = deviceName;
      return deviceName;
    }

    try {
      if (defaultTargetPlatform == TargetPlatform.android) {
        final androidInfo = await DeviceInfoPlugin().androidInfo;
        deviceName = '${androidInfo.brand} ${androidInfo.model}';
      } else if (defaultTargetPlatform == TargetPlatform.iOS) {
        final iosInfo = await DeviceInfoPlugin().iosInfo;
        deviceName = iosInfo.model;
      } else {
        deviceName = 'Unknown Device';
      }
    } catch (e) {
      debugPrint('Error getting device name: $e');
      deviceName = 'Unknown Device';
    }

    await _storage.write(key: 'device_name', value: deviceName);
    _cachedDeviceName = deviceName;
    return deviceName;
  }

  static Future<Map<String, dynamic>> getDeviceInfo() async {
    final deviceId = await getDeviceId();
    final deviceName = await getDeviceName();
    
    Map<String, dynamic> deviceInfo = {
      'device_id': deviceId,
      'device_name': deviceName,
      'platform': defaultTargetPlatform.toString().split('.').last,
    };

    try {
      if (defaultTargetPlatform == TargetPlatform.android) {
        final androidInfo = await DeviceInfoPlugin().androidInfo;
        deviceInfo.addAll({
          'os_version': androidInfo.version.release,
          'model': androidInfo.model,
          'manufacturer': androidInfo.manufacturer,
        });
      } else if (defaultTargetPlatform == TargetPlatform.iOS) {
        final iosInfo = await DeviceInfoPlugin().iosInfo;
        deviceInfo.addAll({
          'os_version': iosInfo.systemVersion,
          'model': iosInfo.model,
        });
      }
    } catch (e) {
      debugPrint('Error getting device info: $e');
    }

    return deviceInfo;
  }

  static Future<void> setDeviceName(String name) async {
    await _storage.write(key: 'device_name', value: name);
    _cachedDeviceName = name;
  }

  static Future<void> clearDeviceIdentity() async {
    await _storage.delete(key: 'device_id');
    await _storage.delete(key: 'device_name');
    _cachedDeviceId = null;
    _cachedDeviceName = null;
  }

  // Saved devices management
  static Future<void> saveDevice(String deviceId, Map<String, dynamic> deviceInfo) async {
    final savedDevices = await getSavedDevices();
    savedDevices[deviceId] = deviceInfo;
    await _storage.write(key: 'saved_devices', value: jsonEncode(savedDevices));
  }

  static Future<Map<String, dynamic>> getSavedDevices() async {
    final savedDevicesJson = await _storage.read(key: 'saved_devices');
    if (savedDevicesJson == null) {
      return {};
    }
    try {
      return jsonDecode(savedDevicesJson) as Map<String, dynamic>;
    } catch (e) {
      debugPrint('Error decoding saved devices: $e');
      return {};
    }
  }

  static Future<void> removeSavedDevice(String deviceId) async {
    final savedDevices = await getSavedDevices();
    savedDevices.remove(deviceId);
    await _storage.write(key: 'saved_devices', value: jsonEncode(savedDevices));
  }

  static Future<void> clearAllSavedDevices() async {
    await _storage.delete(key: 'saved_devices');
  }

  static Future<bool> verifyDevice(String deviceId, String deviceFingerprint) async {
    final savedDevices = await getSavedDevices();
    final device = savedDevices[deviceId];
    if (device == null) {
      return false;
    }
    // Verify fingerprint matches to prevent MITM
    return device['fingerprint'] == deviceFingerprint;
  }

  static Future<String> generateDeviceFingerprint() async {
    final deviceInfo = await getDeviceInfo();
    final fingerprintString = jsonEncode(deviceInfo);
    final bytes = utf8.encode(fingerprintString);
    return base64.encode(bytes);
  }
}
