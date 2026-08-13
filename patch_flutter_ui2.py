import re

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Update _buildHeader to include Artifacts button
header_old = """                  ],
                ),
              ],
            ),
          ),
        ],
      ),
    );"""
header_new = """                  ],
                ),
              ],
            ),
          ),
          IconButton(
            icon: const Icon(Icons.inventory_2),
            color: colorScheme.primary,
            tooltip: 'Artifacts',
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (context) => const ArtifactsPage()),
              );
            },
          ),
        ],
      ),
    );"""
content = content.replace(header_old, header_new)

# 2. Complete rewrite of _buildMessageCard
card_old = """  Widget _buildMessageCard(Map<String, dynamic> message, ColorScheme colorScheme) {
    final type = message['type'] as String;
    final content = message['content'] as String;
    
    Color? bgColor;
    IconData? icon;
    
    switch (type) {
      case 'user':
        bgColor = colorScheme.primaryContainer;
        icon = Icons.person;
        break;
      case 'response':
        bgColor = colorScheme.tertiaryContainer;
        icon = Icons.check_circle;
        break;
      case 'error':
        bgColor = colorScheme.errorContainer;
        icon = Icons.error;
        break;
      case 'system':
        bgColor = colorScheme.surfaceContainer;
        icon = Icons.info;
        break;
      default:
        bgColor = colorScheme.surface;
        icon = Icons.message;
    }
    
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      color: bgColor,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18, color: colorScheme.onSurfaceVariant),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    content,
                    style: TextStyle(
                      fontSize: 14,
                      color: colorScheme.onSurface,
                    ),
                  ),
                ),
              ],
            ),
            if (message.containsKey('summary') && message['summary'] != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: colorScheme.secondaryContainer,
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Row(
                    children: [
                      Icon(
                        Icons.auto_awesome,
                        size: 16,
                        color: colorScheme.onSecondaryContainer,
                      ),
                      const SizedBox(width: 4),
                      Expanded(
                        child: Text(
                          message['summary']?.toString() ?? '',
                          style: TextStyle(
                            fontSize: 12,
                            fontWeight: FontWeight.w600,
                            color: colorScheme.onSecondaryContainer,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            const SizedBox(height: 4),
            Text(
              message['timestamp']?.toString() ?? '',
              style: TextStyle(
                fontSize: 10,
                color: colorScheme.onSurfaceVariant,
              ),
            ),
          ],
        ),
      ),
    );
  }"""
card_new = """  Widget _buildMessageCard(Map<String, dynamic> message, ColorScheme colorScheme) {
    final type = message['type'] as String;
    final content = message['content'] as String;
    final mode = message['mode'] as String?;
    final status = message['status'] as String?;
    final summary = message['summary'] as String?;
    
    Color? bgColor;
    IconData? icon;
    
    if (type == 'user') {
      bgColor = colorScheme.primaryContainer;
      icon = Icons.person;
    } else if (type == 'response' || type == 'error') {
      bgColor = (status == 'error' || type == 'error') ? colorScheme.errorContainer : colorScheme.tertiaryContainer;
      icon = (status == 'error' || type == 'error') ? Icons.error : Icons.check_circle;
    } else {
      bgColor = colorScheme.surfaceContainer;
      icon = Icons.info;
    }
    
    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      color: bgColor,
      elevation: 0,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, size: 18, color: colorScheme.onSurfaceVariant),
                const SizedBox(width: 8),
                if (mode != null)
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                    margin: const EdgeInsets.only(right: 8),
                    decoration: BoxDecoration(
                      color: colorScheme.surface.withOpacity(0.5),
                      borderRadius: BorderRadius.circular(4),
                    ),
                    child: Text(
                      mode.toUpperCase(),
                      style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: colorScheme.onSurfaceVariant),
                    ),
                  ),
                Expanded(
                  child: Text(
                    type == 'user' ? content : 'Output',
                    style: TextStyle(
                      fontSize: 12,
                      fontWeight: FontWeight.bold,
                      color: colorScheme.onSurfaceVariant,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            if (summary != null && summary.isNotEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                margin: const EdgeInsets.only(bottom: 8),
                decoration: BoxDecoration(
                  color: colorScheme.secondaryContainer,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: colorScheme.secondary.withOpacity(0.3)),
                ),
                child: Row(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Icon(
                      Icons.auto_awesome,
                      size: 16,
                      color: colorScheme.onSecondaryContainer,
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        summary,
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w500,
                          color: colorScheme.onSecondaryContainer,
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            if (type != 'user' && content.isNotEmpty)
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Theme.of(context).brightness == Brightness.dark 
                      ? Colors.black54 
                      : Colors.black.withOpacity(0.05),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: SelectableText(
                  content,
                  style: GoogleFonts.firaCode(
                    fontSize: 12,
                    color: colorScheme.onSurface,
                  ),
                ),
              ),
            if (type == 'user')
              Text(
                content,
                style: TextStyle(
                  fontSize: 14,
                  color: colorScheme.onSurface,
                ),
              ),
            const SizedBox(height: 8),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  message['timestamp']?.toString() ?? '',
                  style: TextStyle(
                    fontSize: 10,
                    color: colorScheme.onSurfaceVariant,
                  ),
                ),
                if (type == 'response' && summary != null && summary.isNotEmpty)
                  TextButton.icon(
                    icon: const Icon(Icons.save, size: 14),
                    label: const Text('Save as Artifact', style: TextStyle(fontSize: 10)),
                    onPressed: () {
                      _saveArtifact(summary, content);
                    },
                    style: TextButton.styleFrom(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 0),
                      minimumSize: Size.zero,
                      tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                    ),
                  ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  void _saveArtifact(String title, String content) {
    ArtifactsManager.addArtifact(
      title: title,
      content: content,
      source: 'antigravity',
    );
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Saved to Artifacts')),
    );
  }
"""
content = content.replace(card_old, card_new)

# 3. Add import for artifacts_page.dart
content = content.replace("import 'device_identity.dart';", "import 'device_identity.dart';\nimport 'artifacts_page.dart';")

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
