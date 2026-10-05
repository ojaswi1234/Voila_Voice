import sys

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

missing_buttons = '''
                      Divider(color: AppTokens.border(isDark), height: 1),
                      ListTile(
                        title: Text('Lock Session', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: const Color(0xFFF59E0B))),
                        leading: const Icon(Icons.lock_rounded, color: Color(0xFFF59E0B), size: 20),
                        onTap: () async {
                          Navigator.pop(context);
                          await _storage.delete(key: 'session_token');
                          if (mounted) {
                            setState(() {
                              _sessionToken = '';
                            });
                            ScaffoldMessenger.of(context).showSnackBar(
                              const SnackBar(content: Text('Session locked. Token destroyed.')),
                            );
                          }
                        },
                      ),
                      Divider(color: AppTokens.border(isDark), height: 1),
                      ListTile(
                        title: Text('Clear Local Data', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: const Color(0xFFEF4444))),
                        leading: const Icon(Icons.delete_rounded, color: Color(0xFFEF4444), size: 20),
                        onTap: () {
                          Navigator.pop(context);
                          _clearLocalData();
                        },
                      ),
                      Divider(color: AppTokens.border(isDark), height: 1),
                      ListTile(
                        title: Text('Clear Backend Devices', style: GoogleFonts.inter(fontSize: 15, fontWeight: FontWeight.w600, color: const Color(0xFFEF4444))),
                        leading: const Icon(Icons.delete_sweep_rounded, color: Color(0xFFEF4444), size: 20),
                        onTap: () {
                          Navigator.pop(context);
                          _clearBackendData();
                        },
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),
                _TokenUsageRow(tokenData: _lastTokenUsage),
'''

content = content.replace('''
                    ],
                  ),
                ),
                const SizedBox(height: 24),
                _TokenUsageRow(tokenData: _lastTokenUsage),
''', missing_buttons)

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print("Missing settings buttons added.")
