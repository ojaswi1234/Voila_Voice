import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class SurveillanceSheet extends StatefulWidget {
  final String backendUrl;
  final String deviceId;
  const SurveillanceSheet({Key? key, required this.backendUrl, required this.deviceId}) : super(key: key);

  @override
  _SurveillanceSheetState createState() => _SurveillanceSheetState();
}

class _SurveillanceSheetState extends State<SurveillanceSheet> {
  bool armed = false;
  bool locked = false;
  bool loading = true;
  String lastAlert = "";

  @override
  void initState() {
    super.initState();
    _fetchStatus();
  }

  String _getUrl(String endpoint) {
    String url = widget.backendUrl.replaceAll('wss://', 'https://').replaceAll('ws://', 'http://');
    url = url.replaceAll('/ws', '/proxy/\/surveillance/\');
    return url;
  }

  Future<void> _fetchStatus() async {
    setState(() => loading = true);
    try {
      final res = await http.get(Uri.parse(_getUrl('status')));
      if (res.statusCode == 200) {
        final data = jsonDecode(res.body);
        setState(() {
          armed = data['armed'] ?? false;
          locked = data['locked'] ?? false;
          lastAlert = data['last_alert_reason'] ?? '';
        });
      }
    } catch (e) {}
    setState(() => loading = false);
  }

  Future<void> _sendCommand(String cmd) async {
    setState(() => loading = true);
    try {
      await http.get(Uri.parse(_getUrl(cmd)));
    } catch (e) {}
    await _fetchStatus();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: const BoxDecoration(
        color: Color(0xFF1E1E24),
        borderRadius: BorderRadius.only(topLeft: Radius.circular(24), topRight: Radius.circular(24)),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          const Text('Surveillance Mode', style: TextStyle(color: Colors.white, fontSize: 20, fontWeight: FontWeight.bold)),
          const SizedBox(height: 24),
          if (loading) const Center(child: CircularProgressIndicator())
          else ...[
            Text('Status: \', 
              style: TextStyle(color: armed ? (locked ? Colors.redAccent : Colors.orangeAccent) : Colors.greenAccent, fontSize: 16, fontWeight: FontWeight.bold)),
            if (lastAlert.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('Last Alert: \', style: const TextStyle(color: Colors.white70, fontSize: 14)),
            ],
            const SizedBox(height: 24),
            Row(
              children: [
                Expanded(child: ElevatedButton(onPressed: () => _sendCommand('arm'), style: ElevatedButton.styleFrom(backgroundColor: Colors.orangeAccent, foregroundColor: Colors.black), child: const Text('Arm'))),
                const SizedBox(width: 12),
                Expanded(child: ElevatedButton(onPressed: () => _sendCommand('disarm'), style: ElevatedButton.styleFrom(backgroundColor: Colors.greenAccent, foregroundColor: Colors.black), child: const Text('Disarm'))),
              ],
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(child: ElevatedButton(onPressed: () => _sendCommand('lock'), style: ElevatedButton.styleFrom(backgroundColor: Colors.redAccent, foregroundColor: Colors.white), child: const Text('Lock'))),
                const SizedBox(width: 12),
                Expanded(child: ElevatedButton(onPressed: () => _sendCommand('unlock'), style: ElevatedButton.styleFrom(backgroundColor: Colors.blueAccent, foregroundColor: Colors.white), child: const Text('Unlock'))),
              ],
            ),
          ],
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}
