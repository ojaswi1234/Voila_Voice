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
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;

    return Scaffold(
      backgroundColor: const Color(0xFF0F0F12),
      appBar: AppBar(
        title: const Text('Artifacts', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, letterSpacing: -0.3)),
        backgroundColor: const Color(0xFF0F0F12),
        elevation: 0,
        scrolledUnderElevation: 0,
      ),
      body: ArtifactsManager.artifacts.isEmpty
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.folder_open, size: 48, color: Colors.white.withOpacity(0.2)),
                  const SizedBox(height: 16),
                  Text('No artifacts yet', style: TextStyle(color: Colors.white.withOpacity(0.5))),
                ],
              ),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(16),
              itemCount: ArtifactsManager.artifacts.length,
              itemBuilder: (context, index) {
                final artifact = ArtifactsManager.artifacts[index];
                return _buildArtifactCard(artifact, colorScheme);
              },
            ),
    );
  }

  Widget _buildArtifactCard(Artifact artifact, ColorScheme colorScheme) {
    Color statusColor;
    IconData statusIcon;
    Color statusBgColor;

    switch (artifact.status) {
      case 'approved':
        statusColor = const Color(0xFF3DDC97);
        statusBgColor = const Color(0xFF3DDC97).withOpacity(0.1);
        statusIcon = Icons.check_circle_outline;
        break;
      case 'rejected':
        statusColor = Colors.redAccent;
        statusBgColor = Colors.redAccent.withOpacity(0.1);
        statusIcon = Icons.cancel_outlined;
        break;
      default:
        statusColor = const Color(0xFFFFB86C);
        statusBgColor = const Color(0xFFFFB86C).withOpacity(0.1);
        statusIcon = Icons.hourglass_empty;
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF1A1A1F),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: Colors.white.withOpacity(0.04)),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
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
                      artifact.source == 'voila' ? Icons.terminal : Icons.auto_awesome,
                      size: 14,
                      color: colorScheme.primary,
                    ),
                    const SizedBox(width: 6),
                    Text(
                      artifact.source.toUpperCase(),
                      style: TextStyle(
                        fontSize: 10,
                        fontWeight: FontWeight.w600,
                        color: colorScheme.primary,
                        letterSpacing: 0.5,
                      ),
                    ),
                    const Spacer(),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: statusBgColor,
                        borderRadius: BorderRadius.circular(100),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(statusIcon, size: 10, color: statusColor),
                          const SizedBox(width: 4),
                          Text(
                            artifact.status.toUpperCase(),
                            style: TextStyle(
                              fontSize: 9,
                              fontWeight: FontWeight.w700,
                              color: statusColor,
                              letterSpacing: 0.5,
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
                  style: const TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w600,
                    color: Colors.white,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  ''.split('.')[0],
                  style: TextStyle(
                    fontSize: 11,
                    color: Colors.white.withOpacity(0.5),
                  ),
                ),
              ],
            ),
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
      backgroundColor: const Color(0xFF0F0F12),
      appBar: AppBar(
        title: const Text('Details', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w600, letterSpacing: -0.3)),
        backgroundColor: const Color(0xFF0F0F12),
        elevation: 0,
        scrolledUnderElevation: 0,
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
                    style: const TextStyle(
                      fontSize: 18,
                      fontWeight: FontWeight.w600,
                      color: Colors.white,
                      height: 1.3,
                    ),
                  ),
                  const SizedBox(height: 8),
                  Text(
                    'Source:  • ',
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.white.withOpacity(0.5),
                    ),
                  ),
                  const SizedBox(height: 24),
                  if (artifact.content != null && artifact.content!.isNotEmpty)
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(16),
                      decoration: BoxDecoration(
                        color: const Color(0xFF1A1A1F),
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.white.withOpacity(0.04)),
                      ),
                      child: SelectableText(
                        artifact.content!,
                        style: TextStyle(
                          fontFamily: 'Courier',
                          fontSize: 13,
                          height: 1.5,
                          color: Colors.white.withOpacity(0.9),
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
                color: const Color(0xFF1A1A1F),
                border: Border(top: BorderSide(color: Colors.white.withOpacity(0.04))),
              ),
              child: SafeArea(
                child: Row(
                  children: [
                    Expanded(
                      child: GestureDetector(
                        onTap: () {
                          ArtifactsManager.updateStatus(artifact.id, 'rejected');
                          onStatusChanged();
                          Navigator.pop(context);
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          decoration: BoxDecoration(
                            color: Colors.transparent,
                            borderRadius: BorderRadius.circular(12),
                            border: Border.all(color: Colors.redAccent.withOpacity(0.5)),
                          ),
                          alignment: Alignment.center,
                          child: const Text('Reject', style: TextStyle(color: Colors.redAccent, fontWeight: FontWeight.w600, fontSize: 14)),
                        ),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: GestureDetector(
                        onTap: () {
                          ArtifactsManager.updateStatus(artifact.id, 'approved');
                          onStatusChanged();
                          Navigator.pop(context);
                        },
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 14),
                          decoration: BoxDecoration(
                            color: const Color(0xFF3DDC97),
                            borderRadius: BorderRadius.circular(12),
                          ),
                          alignment: Alignment.center,
                          child: const Text('Approve', style: TextStyle(color: Colors.black, fontWeight: FontWeight.w700, fontSize: 14)),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
            ),
        ],
      ),
    );
  }
}
