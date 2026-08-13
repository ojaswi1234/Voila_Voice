import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';

class Artifact {
  final String id;
  final String title;
  final String? content;
  final String source;
  String status;
  final DateTime createdAt;

  Artifact({
    required this.id,
    required this.title,
    this.content,
    required this.source,
    this.status = 'pending',
    required this.createdAt,
  });
}

class ArtifactsManager {
  static final List<Artifact> _artifacts = [];

  static List<Artifact> get artifacts => _artifacts;

  static void addArtifact({
    required String title,
    String? content,
    required String source,
  }) {
    _artifacts.insert(
      0,
      Artifact(
        id: const Uuid().v4(),
        title: title,
        content: content,
        source: source,
        createdAt: DateTime.now(),
      ),
    );
  }

  static void updateStatus(String id, String status) {
    final index = _artifacts.indexWhere((a) => a.id == id);
    if (index != -1) {
      _artifacts[index].status = status;
    }
  }
}

class ArtifactsPage extends StatefulWidget {
  const ArtifactsPage({super.key});

  @override
  State<ArtifactsPage> createState() => _ArtifactsPageState();
}

class _ArtifactsPageState extends State<ArtifactsPage> {
  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;
    final artifacts = ArtifactsManager.artifacts;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Artifacts'),
        backgroundColor: colorScheme.surface,
      ),
      body: artifacts.isEmpty
          ? Center(
              child: Text(
                'No artifacts found.',
                style: TextStyle(color: colorScheme.onSurfaceVariant),
              ),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: artifacts.length,
              itemBuilder: (context, index) {
                final artifact = artifacts[index];
                return _buildArtifactCard(artifact, colorScheme);
              },
            ),
    );
  }

  Widget _buildArtifactCard(Artifact artifact, ColorScheme colorScheme) {
    Color statusColor;
    IconData statusIcon;

    switch (artifact.status) {
      case 'approved':
        statusColor = Colors.green;
        statusIcon = Icons.check_circle;
        break;
      case 'rejected':
        statusColor = Colors.red;
        statusIcon = Icons.cancel;
        break;
      default:
        statusColor = Colors.orange;
        statusIcon = Icons.hourglass_empty;
    }

    return Card(
      margin: const EdgeInsets.only(bottom: 12),
      child: InkWell(
        onTap: () {
          Navigator.push(
            context,
            MaterialPageRoute(
              builder: (context) => ArtifactDetailPage(
                artifact: artifact,
                onStatusChanged: () => setState(() {}),
              ),
            ),
          );
        },
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(
                    artifact.source == 'antigravity' ? Icons.terminal : Icons.auto_awesome,
                    size: 16,
                    color: colorScheme.primary,
                  ),
                  const SizedBox(width: 8),
                  Text(
                    artifact.source.toUpperCase(),
                    style: TextStyle(
                      fontSize: 10,
                      fontWeight: FontWeight.bold,
                      color: colorScheme.primary,
                    ),
                  ),
                  const Spacer(),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    decoration: BoxDecoration(
                      color: statusColor.withOpacity(0.1),
                      borderRadius: BorderRadius.circular(12),
                    ),
                    child: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(statusIcon, size: 12, color: statusColor),
                        const SizedBox(width: 4),
                        Text(
                          artifact.status.toUpperCase(),
                          style: TextStyle(
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                            color: statusColor,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                artifact.title,
                style: TextStyle(
                  fontSize: 16,
                  fontWeight: FontWeight.w600,
                  color: colorScheme.onSurface,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                '${artifact.createdAt.toLocal()}'.split('.')[0],
                style: TextStyle(
                  fontSize: 12,
                  color: colorScheme.onSurfaceVariant,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class ArtifactDetailPage extends StatelessWidget {
  final Artifact artifact;
  final VoidCallback onStatusChanged;

  const ArtifactDetailPage({
    super.key,
    required this.artifact,
    required this.onStatusChanged,
  });

  @override
  Widget build(BuildContext context) {
    final colorScheme = Theme.of(context).colorScheme;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Artifact Details'),
        backgroundColor: colorScheme.surface,
      ),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    artifact.title,
                    style: TextStyle(
                      fontSize: 20,
                      fontWeight: FontWeight.w600,
                      color: colorScheme.onSurface,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Source: ${artifact.source} | Date: ${artifact.createdAt.toLocal().toString().split('.')[0]}',
                    style: TextStyle(
                      fontSize: 12,
                      color: colorScheme.onSurfaceVariant,
                    ),
                  ),
                  const SizedBox(height: 24),
                  if (artifact.content != null && artifact.content!.isNotEmpty)
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: Theme.of(context).brightness == Brightness.dark
                            ? Colors.black54
                            : Colors.black.withOpacity(0.05),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: SelectableText(
                        artifact.content!,
                        style: TextStyle(
                          fontFamily: 'monospace',
                          fontSize: 14,
                          color: colorScheme.onSurface,
                        ),
                      ),
                    ),
                ],
              ),
            ),
          ),
          if (artifact.status == 'pending')
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: colorScheme.surface,
                boxShadow: [
                  BoxShadow(
                    color: colorScheme.shadow.withOpacity(0.1),
                    blurRadius: 4,
                    offset: const Offset(0, -2),
                  ),
                ],
              ),
              child: Row(
                children: [
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: () {
                        ArtifactsManager.updateStatus(artifact.id, 'rejected');
                        onStatusChanged();
                        Navigator.pop(context);
                      },
                      icon: const Icon(Icons.close, color: Colors.red),
                      label: const Text('Reject', style: TextStyle(color: Colors.red)),
                      style: OutlinedButton.styleFrom(
                        side: const BorderSide(color: Colors.red),
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                    ),
                  ),
                  const SizedBox(width: 16),
                  Expanded(
                    child: ElevatedButton.icon(
                      onPressed: () {
                        ArtifactsManager.updateStatus(artifact.id, 'approved');
                        onStatusChanged();
                        Navigator.pop(context);
                      },
                      icon: const Icon(Icons.check),
                      label: const Text('Approve'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.green,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(vertical: 16),
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
