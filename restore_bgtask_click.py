import sys

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

old_block = '''                        return Container(
                          padding: const EdgeInsets.all(12),
                          decoration: BoxDecoration(
                            color: AppTokens.cardAlt(isDark),
                            borderRadius: BorderRadius.circular(16),
                            border: Border.all(color: isRunning ? AppTokens.accentSecondary.withOpacity(0.5) : AppTokens.border(isDark)),
                          ),'''

new_block = '''                        return InkWell(
                          borderRadius: BorderRadius.circular(16),
                          onTap: () {
                            showDialog(
                              context: context,
                              builder: (context) => AlertDialog(
                                backgroundColor: AppTokens.bg(isDark),
                                title: Row(
                                  children: [
                                    Icon(isRunning ? Icons.play_circle_fill_rounded : Icons.check_circle_rounded, color: isRunning ? AppTokens.accentSecondary : AppTokens.textSecondary(isDark), size: 20),
                                    const SizedBox(width: 8),
                                    Text('Task Details', style: GoogleFonts.spaceGrotesk(color: AppTokens.textPrimary(isDark), fontSize: 16, fontWeight: FontWeight.bold)),
                                  ],
                                ),
                                content: Column(
                                  mainAxisSize: MainAxisSize.min,
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text('ID: \', style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark), fontSize: 12)),
                                    const SizedBox(height: 4),
                                    Text('Status: \', style: GoogleFonts.inter(color: isRunning ? AppTokens.accentSecondary : AppTokens.textPrimary(isDark), fontSize: 12, fontWeight: FontWeight.bold)),
                                    const SizedBox(height: 4),
                                    if (task["duration"] != null) Text('Duration: \', style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark), fontSize: 12)),
                                    const SizedBox(height: 12),
                                    Text('Command:', style: GoogleFonts.inter(color: AppTokens.textPrimary(isDark), fontSize: 12, fontWeight: FontWeight.bold)),
                                    const SizedBox(height: 4),
                                    Container(
                                      padding: const EdgeInsets.all(8),
                                      decoration: BoxDecoration(
                                        color: AppTokens.cardAlt(isDark),
                                        borderRadius: BorderRadius.circular(6),
                                        border: Border.all(color: AppTokens.border(isDark)),
                                      ),
                                      child: Text(task["command"] ?? '', style: GoogleFonts.jetBrainsMono(color: AppTokens.accentPrimary, fontSize: 11)),
                                    ),
                                  ],
                                ),
                                actions: [
                                  TextButton(
                                    onPressed: () => Navigator.pop(context),
                                    child: Text('Close', style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark))),
                                  )
                                ],
                              ),
                            );
                          },
                          child: Container(
                            padding: const EdgeInsets.all(12),
                            decoration: BoxDecoration(
                              color: AppTokens.cardAlt(isDark),
                              borderRadius: BorderRadius.circular(16),
                              border: Border.all(color: isRunning ? AppTokens.accentSecondary.withOpacity(0.5) : AppTokens.border(isDark)),
                            ),'''

if old_block in content:
    content = content.replace(old_block, new_block)
    # We must also add the closing parenthesis for InkWell
    old_end = '''                                ],
                              ),
                            ],
                          ),
                        );'''
    new_end = '''                                ],
                              ),
                            ],
                          ),
                        ),
                      );'''
    content = content.replace(old_end, new_end)
    with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
        f.write(content)
    print("Fixed BG Task clickability!")
else:
    print("Block not found!")
