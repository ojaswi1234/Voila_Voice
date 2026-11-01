import 'dart:convert';
import 'dart:typed_data';
import 'package:encrypt/encrypt.dart' as enc;
import 'package:crypto/crypto.dart';

class CryptoUtils {
  static String encrypt(String plaintext, String passphrase) {
    try {
      final keyBytes = sha256.convert(utf8.encode(passphrase)).bytes;
      final key = enc.Key(Uint8List.fromList(keyBytes));
      final iv = enc.IV.fromSecureRandom(12);
      final encrypter = enc.Encrypter(enc.AES(key, mode: enc.AESMode.gcm));
      
      final encrypted = encrypter.encrypt(plaintext, iv: iv);
      final combined = Uint8List(iv.bytes.length + encrypted.bytes.length);
      combined.setRange(0, iv.bytes.length, iv.bytes);
      combined.setRange(iv.bytes.length, combined.length, encrypted.bytes);
      return base64Encode(combined);
    } catch (e) {
      return '';
    }
  }

  static String decrypt(String encryptedBase64, String passphrase) {
    try {
      final keyBytes = sha256.convert(utf8.encode(passphrase)).bytes;
      final key = enc.Key(Uint8List.fromList(keyBytes));
      
      final encryptedBytes = base64Decode(encryptedBase64);
      if (encryptedBytes.length < 12) return "Decryption failed: too short";
      
      final nonce = encryptedBytes.sublist(0, 12);
      final ciphertext = encryptedBytes.sublist(12);
      
      final iv = enc.IV(Uint8List.fromList(nonce));
      final encrypter = enc.Encrypter(enc.AES(key, mode: enc.AESMode.gcm));
      
      final encryptedObj = enc.Encrypted(Uint8List.fromList(ciphertext));
      return encrypter.decrypt(encryptedObj, iv: iv);
    } catch (e) {
      return "Decryption error: $e";
    }
  }
}
