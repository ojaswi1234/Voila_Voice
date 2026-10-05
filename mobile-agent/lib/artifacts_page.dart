import 'package:flutter/material.dart';
import 'package:uuid/uuid.dart';
import 'package:google_fonts/google_fonts.dart';
import 'main.dart'; // To access AppTokens and appThemeMode

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
    this.status = 'completed',
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
    bool isDark = appThemeMode.value == ThemeMode.dark;

    return Scaffold(
      backgroundColor: AppTokens.bg(isDark),
      appBar: AppBar(
        title: Text('ARTIFACTS', style: GoogleFonts.spaceGrotesk(fontSize: 16, fontWeight: FontWeight.w800, letterSpacing: 1.5, color: AppTokens.textPrimary(isDark))),
        backgroundColor: AppTokens.bg(isDark),
        elevation: 0,
        scrolledUnderElevation: 0,
        iconTheme: IconThemeData(color: AppTokens.textPrimary(isDark)),
        centerTitle: true,
      ),
      body: ArtifactsManager.artifacts.isEmpty
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(Icons.dashboard_customize_rounded, size: 64, color: AppTokens.textSecondary(isDark).withOpacity(0.3)),
                  const SizedBox(height: 24),
                  Text('No Artifacts Yet', style: GoogleFonts.spaceGrotesk(color: AppTokens.textPrimary(isDark), fontSize: 20, fontWeight: FontWeight.w800)),
                  const SizedBox(height: 8),
                  Text('Ask Voila to generate documents or run research\nto see artifacts appear here.', textAlign: TextAlign.center, style: GoogleFonts.inter(color: AppTokens.textSecondary(isDark), fontSize: 14)),
                  const SizedBox(height: 32),
                  ElevatedButton.icon(
                    icon: Icon(Icons.arrow_back_rounded, size: 16, color: AppTokens.textPrimary(isDark)),
                    label: Text('Back to Chat', style: GoogleFonts.inter(fontWeight: FontWeight.bold, color: AppTokens.textPrimary(isDark))),
                    style: ElevatedButton.styleFrom(backgroundColor: AppTokens.cardAlt(isDark), elevation: 0, padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16), shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16))),
                    onPressed: () => Navigator.pop(context),
                  )
                ],
              ),
            )
          : ListView.builder(
              padding: const EdgeInsets.all(20),
              itemCount: ArtifactsManager.artifacts.length,
              itemBuilder: (context, index) {
                final artifact = ArtifactsManager.artifacts[index];
                return _buildArtifactCard(artifact, isDark);
              },
            ),
    );
  }

  Widget _buildArtifactCard(Artifact artifact, bool isDark) {
    Color statusColor;
    IconData statusIcon;

    switch (artifact.status) {
      case 'approved':
        statusColor = const Color(0xFF10B981);
        statusIcon = Icons.check_circle_rounded;
        break;
      case 'rejected':
        statusColor = const Color(0xFFEF4444);
        statusIcon = Icons.cancel_rounded;
        break;
      default:
        statusColor = const Color(0xFFF59E0B);
        statusIcon = Icons.hourglass_empty_rounded;
    }

    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      decoration: BoxDecoration(
        color: AppTokens.card(isDark),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: AppTokens.border(isDark)),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          borderRadius: BorderRadius.circular(24),
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
            padding: const EdgeInsets.all(20),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      artifact.source == 'voila' ? Icons.terminal_rounded : Icons.auto_awesome_rounded,
                      size: 16,
                      color: AppTokens.accentSecondary,
                    ),
                    const SizedBox(width: 8),
                    Text(
                      artifact.source.toUpperCase(),
                      style: GoogleFonts.spaceGrotesk(
                        fontSize: 11,
                        fontWeight: FontWeight.w800,
                        color: AppTokens.accentSecondary,
                        letterSpacing: 1.0,
                      ),
                    ),
                    const Spacer(),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: statusColor.withOpacity(0.15),
                        borderRadius: BorderRadius.circular(100),
                      ),
                      child: Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(statusIcon, size: 12, color: statusColor),
                          const SizedBox(width: 4),
                          Text(
                            artifact.status.toUpperCase(),
                            style: GoogleFonts.inter(
                              fontSize: 10,
                              fontWeight: FontWeight.bold,
                              color: statusColor,
                              letterSpacing: 0.5,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 16),
                Text(
                  artifact.title,
                  style: GoogleFonts.inter(
                    fontSize: 16,
                    fontWeight: FontWeight.w600,
                    color: AppTokens.textPrimary(isDark),
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
    bool isDark = appThemeMode.value == ThemeMode.dark;

    return Scaffold(
      backgroundColor: AppTokens.bg(isDark),
      appBar: AppBar(
        title: Text('DETAILS', style: GoogleFonts.spaceGrotesk(fontSize: 16, fontWeight: FontWeight.w800, letterSpacing: 1.5, color: AppTokens.textPrimary(isDark))),
        backgroundColor: AppTokens.bg(isDark),
        elevation: 0,
        scrolledUnderElevation: 0,
        iconTheme: IconThemeData(color: AppTokens.textPrimary(isDark)),
        centerTitle: true,
      ),
      body: Column(
        children: [
          Expanded(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    artifact.title,
                    style: GoogleFonts.inter(
                      fontSize: 20,
                      fontWeight: FontWeight.bold,
                      color: AppTokens.textPrimary(isDark),
                      height: 1.3,
                    ),
                  ),
                  const SizedBox(height: 24),
                  if (artifact.content != null && artifact.content!.isNotEmpty)
                    Container(
                      width: double.infinity,
                      padding: const EdgeInsets.all(20),
                      decoration: BoxDecoration(
                        color: AppTokens.cardAlt(isDark),
                        borderRadius: BorderRadius.circular(24),
                        border: Border.all(color: AppTokens.border(isDark)),
                      ),
                      child: SelectableText(
                        artifact.content!,
                        style: GoogleFonts.firaCode(
                          fontSize: 13,
                          height: 1.5,
                          color: AppTokens.textPrimary(isDark),
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