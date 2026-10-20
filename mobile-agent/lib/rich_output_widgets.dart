import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'visualizer.dart';

// ─── THEME TOKENS ───
class _OutputTokens {
  static const Color accent = Color(0xFF6366F1);
  static const Color accentCyan = Color(0xFF00E5FF);
  static const Color accentEmerald = Color(0xFF10B981);
  static const Color accentAmber = Color(0xFFF59E0B);
  static const Color accentRose = Color(0xFFEF4444);

  static Color terminalBg(bool isDark) => const Color(0xFF0A0D14);
  static Color terminalBorder(bool isDark) => const Color(0xFF1E2330);
  static Color terminalHeader(bool isDark) => const Color(0xFF131822);
}

// ═══════════════════════════════════════════════════════════════════════════
// 1. SHELL MODE: AUTHENTIC TERMINAL OUTPUT CARD
// ═══════════════════════════════════════════════════════════════════════════

class ShellOutputCard extends StatefulWidget {
  final Map<String, dynamic> message;
  final bool isDark;
  final String? commandExecuted;

  const ShellOutputCard({
    Key? key,
    required this.message,
    required this.isDark,
    this.commandExecuted,
  }) : super(key: key);

  @override
  State<ShellOutputCard> createState() => _ShellOutputCardState();
}

class _ShellOutputCardState extends State<ShellOutputCard> {
  bool _isExpanded = false;
  bool _copied = false;

  void _copyToClipboard(String text) {
    Clipboard.setData(ClipboardData(text: text));
    HapticFeedback.lightImpact();
    setState(() => _copied = true);
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Terminal output copied to clipboard'),
        duration: Duration(seconds: 1),
        behavior: SnackBarBehavior.floating,
      ),
    );
  }

  Color _getLineColor(String line) {
    final lower = line.toLowerCase();
    if (lower.contains('error') || lower.contains('fail') || lower.contains('fatal') || lower.contains('exception') || lower.contains('denied')) {
      return const Color(0xFFF87171); // Soft Red
    }
    if (lower.contains('warn') || lower.contains('notice') || lower.contains('caution')) {
      return const Color(0xFFFBBF24); // Amber
    }
    if (lower.contains('success') || lower.contains('done') || lower.contains('ok') || lower.contains('passed') || lower.contains('completed')) {
      return const Color(0xFF34D399); // Mint Emerald
    }
    if (lower.contains('http://') || lower.contains('https://') || lower.contains('c:\\') || lower.startsWith('/')) {
      return const Color(0xFF38BDF8); // Sky Blue
    }
    if (line.trim().startsWith('\$') || line.trim().startsWith('PS >') || line.trim().startsWith('>')) {
      return const Color(0xFF00E5FF); // Electric Cyan
    }
    return const Color(0xFFE2E8F0); // Crisp light slate
  }

  @override
  Widget build(BuildContext context) {
    final content = (widget.message['content'] as String? ?? '').trim();
    final summary = widget.message['summary'] as String? ?? '';
    final status = widget.message['status'] as String? ?? 'ok';
    final isError = status == 'error' || content.toLowerCase().contains('command failed') || content.toLowerCase().contains('error:');

    final lines = content.isEmpty ? ['(No output returned)'] : content.split('\n');
    final isLong = lines.length > 12;
    final displayLines = (!_isExpanded && isLong) ? lines.take(12).toList() : lines;

    return Container(
      width: double.infinity,
      decoration: BoxDecoration(
        color: _OutputTokens.terminalBg(widget.isDark),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isError ? _OutputTokens.accentRose.withOpacity(0.5) : _OutputTokens.terminalBorder(widget.isDark),
          width: 1.5,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.35),
            blurRadius: 16,
            offset: const Offset(0, 8),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // ─── TERMINAL HEADER BAR ───
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: _OutputTokens.terminalHeader(widget.isDark),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(14)),
              border: Border(bottom: BorderSide(color: _OutputTokens.terminalBorder(widget.isDark))),
            ),
            child: Row(
              children: [
                // macOS / Linux traffic lights
                Row(
                  children: [
                    Container(width: 10, height: 10, decoration: const BoxDecoration(color: Color(0xFFFF5F56), shape: BoxShape.circle)),
                    const SizedBox(width: 6),
                    Container(width: 10, height: 10, decoration: const BoxDecoration(color: Color(0xFFFFBD2E), shape: BoxShape.circle)),
                    const SizedBox(width: 6),
                    Container(width: 10, height: 10, decoration: const BoxDecoration(color: Color(0xFF27C93F), shape: BoxShape.circle)),
                  ],
                ),
                const SizedBox(width: 14),
                const Icon(Icons.terminal_rounded, size: 14, color: Color(0xFF00E5FF)),
                const SizedBox(width: 6),
                Text(
                  'TERMINAL',
                  style: GoogleFonts.spaceGrotesk(
                    color: Colors.white70,
                    fontSize: 11,
                    fontWeight: FontWeight.w800,
                    letterSpacing: 1.5,
                  ),
                ),
                const Spacer(),
                // Status pill (EXIT 0 / EXIT 1)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: isError ? _OutputTokens.accentRose.withOpacity(0.2) : _OutputTokens.accentEmerald.withOpacity(0.2),
                    borderRadius: BorderRadius.circular(6),
                    border: Border.all(
                      color: isError ? _OutputTokens.accentRose.withOpacity(0.6) : _OutputTokens.accentEmerald.withOpacity(0.6),
                    ),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Container(
                        width: 6,
                        height: 6,
                        decoration: BoxDecoration(
                          color: isError ? _OutputTokens.accentRose : _OutputTokens.accentEmerald,
                          shape: BoxShape.circle,
                        ),
                      ),
                      const SizedBox(width: 5),
                      Text(
                        isError ? 'EXIT 1' : 'EXIT 0',
                        style: GoogleFonts.firaCode(
                          color: isError ? _OutputTokens.accentRose : _OutputTokens.accentEmerald,
                          fontSize: 10,
                          fontWeight: FontWeight.bold,
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(width: 8),
                // Copy Button
                IconButton(
                  padding: EdgeInsets.zero,
                  constraints: const BoxConstraints(),
                  icon: Icon(
                    _copied ? Icons.check_circle_rounded : Icons.copy_rounded,
                    size: 16,
                    color: _copied ? _OutputTokens.accentEmerald : Colors.white60,
                  ),
                  onPressed: () => _copyToClipboard(content),
                  tooltip: 'Copy Output',
                ),
              ],
            ),
          ),

          // ─── COMMAND BAR (IF PROVIDED) ───
          if (widget.commandExecuted != null && widget.commandExecuted!.isNotEmpty)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              color: const Color(0xFF0F131C),
              child: Row(
                children: [
                  Text(
                    '\$ ',
                    style: GoogleFonts.firaCode(color: const Color(0xFF00E5FF), fontSize: 13, fontWeight: FontWeight.bold),
                  ),
                  Expanded(
                    child: Text(
                      widget.commandExecuted!,
                      style: GoogleFonts.firaCode(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600),
                      overflow: TextOverflow.ellipsis,
                    ),
                  ),
                ],
              ),
            ),

          // ─── TERMINAL BODY ───
          Padding(
            padding: const EdgeInsets.all(14),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: displayLines.map((line) {
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 1.5),
                    child: SelectableText(
                      line,
                      style: GoogleFonts.firaCode(
                        color: _getLineColor(line),
                        fontSize: 12.5,
                        height: 1.4,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  );
                }).toList(),
              ),
            ),
          ),

          // ─── EXPAND / COLLAPSE BAR ───
          if (isLong)
            GestureDetector(
              onTap: () => setState(() => _isExpanded = !_isExpanded),
              child: Container(
                padding: const EdgeInsets.symmetric(vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.white.withOpacity(0.04),
                  border: Border(top: BorderSide(color: _OutputTokens.terminalBorder(widget.isDark))),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    Text(
                      _isExpanded ? 'Collapse Log' : 'Show full terminal log (${lines.length} lines)',
                      style: GoogleFonts.inter(color: const Color(0xFF00E5FF), fontSize: 12, fontWeight: FontWeight.w600),
                    ),
                    const SizedBox(width: 4),
                    Icon(
                      _isExpanded ? Icons.keyboard_arrow_up_rounded : Icons.keyboard_arrow_down_rounded,
                      size: 16,
                      color: const Color(0xFF00E5FF),
                    ),
                  ],
                ),
              ),
            ),

          // ─── TERMINAL SUMMARY FOOTER ───
          if (summary.isNotEmpty)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
              decoration: BoxDecoration(
                color: Colors.black.withOpacity(0.4),
                borderRadius: const BorderRadius.vertical(bottom: Radius.circular(14)),
                border: Border(top: BorderSide(color: _OutputTokens.terminalBorder(widget.isDark))),
              ),
              child: Row(
                children: [
                  Icon(
                    isError ? Icons.error_outline_rounded : Icons.check_circle_outline_rounded,
                    size: 13,
                    color: isError ? _OutputTokens.accentRose : _OutputTokens.accentEmerald,
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      summary,
                      style: GoogleFonts.inter(
                        color: isError ? _OutputTokens.accentRose : Colors.white70,
                        fontSize: 11.5,
                        fontWeight: FontWeight.w500,
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

// ═══════════════════════════════════════════════════════════════════════════
// 2. AGENT MODE: RICH STRUCTURED SUMMARY ENGINE (MARKDOWN, CODE, CALLOUTS)
// ═══════════════════════════════════════════════════════════════════════════

class VoilaRichSummaryView extends StatelessWidget {
  final String text;
  final bool isDark;
  final Color primaryTextColor;

  // Lightweight LRU Block Cache for 60/120 FPS jank-free scrolling
  static final Map<int, List<_RichBlock>> _blockCache = {};
  static final RegExp _inlineRegex = RegExp(r'(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|==[^=]+==|~~[^~]+~~)');

  const VoilaRichSummaryView({
    Key? key,
    required this.text,
    required this.isDark,
    required this.primaryTextColor,
  }) : super(key: key);

  List<_RichBlock> _getOrParseBlocks() {
    final key = text.hashCode;
    if (_blockCache.containsKey(key)) {
      return _blockCache[key]!;
    }
    final blocks = _parseBlocks(text);
    if (_blockCache.length > 80) {
      _blockCache.remove(_blockCache.keys.first);
    }
    _blockCache[key] = blocks;
    return blocks;
  }

  @override
  Widget build(BuildContext context) {
    final blocks = _getOrParseBlocks();

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: blocks.map((block) => _renderBlock(context, block)).toList(),
    );
  }

  List<_RichBlock> _parseBlocks(String input) {
    final List<_RichBlock> blocks = [];
    final lines = input.split('\n');
    int i = 0;

    while (i < lines.length) {
      final line = lines[i];
      final trimmed = line.trim();

      // Fenced Code Block: ```lang ... ```
      if (trimmed.startsWith('```')) {
        final lang = trimmed.substring(3).trim();
        final List<String> codeLines = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith('```')) {
          codeLines.add(lines[i]);
          i++;
        }
        blocks.add(_RichBlock(_BlockType.codeBlock, codeLines.join('\n'), meta: lang));
        i++;
        continue;
      }

      // Callout Block: > [!NOTE] or > Note: or > ...
      if (trimmed.startsWith('>')) {
        final List<String> calloutLines = [];
        while (i < lines.length && lines[i].trim().startsWith('>')) {
          calloutLines.add(lines[i].trim().substring(1).trim());
          i++;
        }
        blocks.add(_RichBlock(_BlockType.callout, calloutLines.join('\n')));
        continue;
      }

      // Heading 1: # ...
      if (trimmed.startsWith('# ')) {
        blocks.add(_RichBlock(_BlockType.h1, trimmed.substring(2)));
        i++;
        continue;
      }

      // Heading 2: ## ...
      if (trimmed.startsWith('## ')) {
        blocks.add(_RichBlock(_BlockType.h2, trimmed.substring(3)));
        i++;
        continue;
      }

      // Heading 3: ### ...
      if (trimmed.startsWith('### ')) {
        blocks.add(_RichBlock(_BlockType.h3, trimmed.substring(4)));
        i++;
        continue;
      }

      // Unordered list item: * or -
      if (RegExp(r'^[-*•]\s+').hasMatch(trimmed)) {
        final itemText = trimmed.replaceFirst(RegExp(r'^[-*•]\s+'), '');
        blocks.add(_RichBlock(_BlockType.bullet, itemText));
        i++;
        continue;
      }

      // Numbered list item: 1. 2.
      final numMatch = RegExp(r'^(\d+)\.\s+').firstMatch(trimmed);
      if (numMatch != null) {
        final numStr = numMatch.group(1)!;
        final itemText = trimmed.substring(numMatch.group(0)!.length);
        blocks.add(_RichBlock(_BlockType.numbered, itemText, meta: numStr));
        i++;
        continue;
      }

      // Empty line / spacer
      if (trimmed.isEmpty) {
        blocks.add(_RichBlock(_BlockType.spacer, ''));
        i++;
        continue;
      }

      // Regular Paragraph
      blocks.add(_RichBlock(_BlockType.paragraph, line));
      i++;
    }

    return blocks;
  }

  Widget _renderBlock(BuildContext context, _RichBlock block) {
    switch (block.type) {
      case _BlockType.h1:
        return Padding(
          padding: const EdgeInsets.only(top: 14, bottom: 8),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                block.content,
                style: GoogleFonts.spaceGrotesk(
                  color: primaryTextColor,
                  fontSize: 19,
                  fontWeight: FontWeight.w800,
                  letterSpacing: -0.5,
                ),
              ),
              const SizedBox(height: 4),
              Container(
                height: 2,
                width: 40,
                decoration: BoxDecoration(
                  gradient: const LinearGradient(colors: [Color(0xFF00E5FF), Color(0xFF6366F1)]),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
            ],
          ),
        );

      case _BlockType.h2:
        return Padding(
          padding: const EdgeInsets.only(top: 12, bottom: 6),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [
              Container(
                width: 4,
                height: 16,
                decoration: BoxDecoration(
                  color: const Color(0xFF00E5FF),
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  block.content,
                  style: GoogleFonts.spaceGrotesk(
                    color: primaryTextColor,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                    letterSpacing: -0.3,
                  ),
                ),
              ),
            ],
          ),
        );

      case _BlockType.h3:
        return Padding(
          padding: const EdgeInsets.only(top: 10, bottom: 4),
          child: Text(
            block.content,
            style: GoogleFonts.spaceGrotesk(
              color: primaryTextColor.withOpacity(0.9),
              fontSize: 14.5,
              fontWeight: FontWeight.w600,
            ),
          ),
        );

      case _BlockType.bullet:
        return Padding(
          padding: const EdgeInsets.only(left: 6, bottom: 6),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                margin: const EdgeInsets.only(top: 6, right: 10),
                width: 6,
                height: 6,
                decoration: const BoxDecoration(
                  color: Color(0xFF00E5FF),
                  shape: BoxShape.circle,
                ),
              ),
              Expanded(
                child: _buildRichInlineText(block.content),
              ),
            ],
          ),
        );

      case _BlockType.numbered:
        return Padding(
          padding: const EdgeInsets.only(left: 4, bottom: 6),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                margin: const EdgeInsets.only(top: 2, right: 8),
                padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: const Color(0xFF6366F1).withOpacity(0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Text(
                  block.meta ?? '1',
                  style: GoogleFonts.spaceGrotesk(
                    color: const Color(0xFF6366F1),
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              Expanded(
                child: _buildRichInlineText(block.content),
              ),
            ],
          ),
        );

      case _BlockType.codeBlock:
        return _CodeSnippetBlock(
          code: block.content,
          language: block.meta ?? 'TEXT',
          isDark: isDark,
        );

      case _BlockType.callout:
        return _CalloutAlertBlock(content: block.content, isDark: isDark);

      case _BlockType.spacer:
        return const SizedBox(height: 6);

      case _BlockType.paragraph:
      default:
        return Padding(
          padding: const EdgeInsets.only(bottom: 6),
          child: _buildRichInlineText(block.content),
        );
    }
  }

  Widget _buildRichInlineText(String text) {
    // Parse inline bold (**bold**), italic (*italic*), and inline code (`code`)
    final List<InlineSpan> spans = [];
    final regex = RegExp(r'(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|==[^=]+==)');
    int lastEnd = 0;

    for (final match in regex.allMatches(text)) {
      if (match.start > lastEnd) {
        spans.add(TextSpan(
          text: text.substring(lastEnd, match.start),
          style: GoogleFonts.inter(color: primaryTextColor, fontSize: 14.5, height: 1.6),
        ));
      }

      final raw = match.group(0)!;
      if (raw.startsWith('**') && raw.endsWith('**')) {
        spans.add(TextSpan(
          text: raw.substring(2, raw.length - 2),
          style: GoogleFonts.inter(
            color: primaryTextColor,
            fontSize: 14.5,
            fontWeight: FontWeight.w700,
            height: 1.6,
          ),
        ));
      } else if (raw.startsWith('`') && raw.endsWith('`')) {
        spans.add(WidgetSpan(
          alignment: PlaceholderAlignment.middle,
          child: Container(
            margin: const EdgeInsets.symmetric(horizontal: 3),
            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
            decoration: BoxDecoration(
              color: isDark ? const Color(0xFF232733) : const Color(0xFFE2E8F0),
              borderRadius: BorderRadius.circular(4),
              border: Border.all(color: isDark ? Colors.white12 : Colors.black12),
            ),
            child: Text(
              raw.substring(1, raw.length - 1),
              style: GoogleFonts.firaCode(
                color: const Color(0xFF00E5FF),
                fontSize: 12.5,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ));
      } else if (raw.startsWith('*') && raw.endsWith('*')) {
        spans.add(TextSpan(
          text: raw.substring(1, raw.length - 1),
          style: GoogleFonts.inter(
            color: primaryTextColor,
            fontSize: 14.5,
            fontStyle: FontStyle.italic,
            height: 1.6,
          ),
        ));
      } else if (raw.startsWith('==') && raw.endsWith('==')) {
        spans.add(WidgetSpan(
          alignment: PlaceholderAlignment.middle,
          child: Container(
            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 1),
            decoration: BoxDecoration(
              color: const Color(0xFFFBBF24).withOpacity(0.2),
              borderRadius: BorderRadius.circular(4),
            ),
            child: Text(
              raw.substring(2, raw.length - 2),
              style: GoogleFonts.inter(
                color: const Color(0xFFFBBF24),
                fontWeight: FontWeight.w600,
                fontSize: 14,
              ),
            ),
          ),
        ));
      } else if (raw.startsWith('~~') && raw.endsWith('~~')) {
        spans.add(TextSpan(
          text: raw.substring(2, raw.length - 2),
          style: GoogleFonts.inter(
            color: primaryTextColor.withOpacity(0.5),
            fontSize: 14.5,
            decoration: TextDecoration.lineThrough,
            height: 1.6,
          ),
        ));
      }

      lastEnd = match.end;
    }

    if (lastEnd < text.length) {
      spans.add(TextSpan(
        text: text.substring(lastEnd),
        style: GoogleFonts.inter(color: primaryTextColor, fontSize: 14.5, height: 1.6),
      ));
    }

    return SelectableText.rich(TextSpan(children: spans));
  }
}

enum _BlockType { h1, h2, h3, bullet, numbered, codeBlock, callout, spacer, paragraph }

class _RichBlock {
  final _BlockType type;
  final String content;
  final String? meta;

  _RichBlock(this.type, this.content, {this.meta});
}

// ─── CODE SNIPPET CARD WITH COPY BUTTON ───
class _CodeSnippetBlock extends StatefulWidget {
  final String code;
  final String language;
  final bool isDark;

  const _CodeSnippetBlock({
    Key? key,
    required this.code,
    required this.language,
    required this.isDark,
  }) : super(key: key);

  @override
  State<_CodeSnippetBlock> createState() => _CodeSnippetBlockState();
}

class _CodeSnippetBlockState extends State<_CodeSnippetBlock> {
  bool _copied = false;

  void _copy() {
    Clipboard.setData(ClipboardData(text: widget.code));
    HapticFeedback.lightImpact();
    setState(() => _copied = true);
    Future.delayed(const Duration(seconds: 2), () {
      if (mounted) setState(() => _copied = false);
    });
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF0D1117),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: const Color(0xFF21262D)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // Header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
            decoration: const BoxDecoration(
              color: Color(0xFF161B22),
              borderRadius: BorderRadius.vertical(top: Radius.circular(11)),
            ),
            child: Row(
              children: [
                Text(
                  widget.language.toUpperCase(),
                  style: GoogleFonts.firaCode(
                    color: const Color(0xFF00E5FF),
                    fontSize: 11,
                    fontWeight: FontWeight.bold,
                  ),
                ),
                const Spacer(),
                GestureDetector(
                  onTap: _copy,
                  child: Row(
                    children: [
                      Icon(
                        _copied ? Icons.check_circle_rounded : Icons.copy_rounded,
                        size: 14,
                        color: _copied ? const Color(0xFF10B981) : Colors.white60,
                      ),
                      const SizedBox(width: 4),
                      Text(
                        _copied ? 'Copied!' : 'Copy',
                        style: GoogleFonts.inter(
                          color: _copied ? const Color(0xFF10B981) : Colors.white70,
                          fontSize: 11,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          // Code body
          Padding(
            padding: const EdgeInsets.all(12),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: SelectableText(
                widget.code,
                style: GoogleFonts.firaCode(
                  color: const Color(0xFFE6EDF3),
                  fontSize: 12.5,
                  height: 1.45,
                ),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─── CALLOUT ALERT BLOCK ───
class _CalloutAlertBlock extends StatelessWidget {
  final String content;
  final bool isDark;

  const _CalloutAlertBlock({Key? key, required this.content, required this.isDark}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    Color accent = const Color(0xFF6366F1);
    IconData icon = Icons.info_outline_rounded;
    String cleanContent = content;

    final lower = content.toLowerCase();
    if (lower.startsWith('[!tip]') || lower.startsWith('tip:')) {
      accent = const Color(0xFF10B981);
      icon = Icons.lightbulb_outline_rounded;
      cleanContent = content.replaceFirst(RegExp(r'(\[!tip\]|tip:)', caseSensitive: false), '').trim();
    } else if (lower.startsWith('[!warning]') || lower.startsWith('warning:')) {
      accent = const Color(0xFFF59E0B);
      icon = Icons.warning_amber_rounded;
      cleanContent = content.replaceFirst(RegExp(r'(\[!warning\]|warning:)', caseSensitive: false), '').trim();
    } else if (lower.startsWith('[!note]') || lower.startsWith('note:')) {
      accent = const Color(0xFF00E5FF);
      icon = Icons.info_outline_rounded;
      cleanContent = content.replaceFirst(RegExp(r'(\[!note\]|note:)', caseSensitive: false), '').trim();
    } else if (lower.startsWith('[!important]') || lower.startsWith('important:')) {
      accent = const Color(0xFF8B5CF6);
      icon = Icons.priority_high_rounded;
      cleanContent = content.replaceFirst(RegExp(r'(\[!important\]|important:)', caseSensitive: false), '').trim();
    } else if (lower.startsWith('[!caution]') || lower.startsWith('caution:') || lower.startsWith('[!danger]') || lower.startsWith('danger:')) {
      accent = const Color(0xFFEF4444);
      icon = Icons.dangerous_rounded;
      cleanContent = content.replaceFirst(RegExp(r'(\[!caution\]|caution:|\[!danger\]|danger:)', caseSensitive: false), '').trim();
    } else if (lower.startsWith('[!success]') || lower.startsWith('success:')) {
      accent = const Color(0xFF10B981);
      icon = Icons.check_circle_outline_rounded;
      cleanContent = content.replaceFirst(RegExp(r'(\[!success\]|success:)', caseSensitive: false), '').trim();
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: accent.withOpacity(0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border(left: BorderSide(color: accent, width: 3.5)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: accent),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              cleanContent,
              style: GoogleFonts.inter(
                color: isDark ? Colors.white : Colors.black87,
                fontSize: 13.5,
                height: 1.5,
                fontWeight: FontWeight.w500,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ═══════════════════════════════════════════════════════════════════════════
// 3. GEMINI LIVE MODE: REAL-TIME BIDIRECTIONAL VOICE SHEET
// ═══════════════════════════════════════════════════════════════════════════

class VoilaLiveModeSheet extends StatefulWidget {
  final String host;
  final String? apiKey;
  final VoidCallback onClose;

  const VoilaLiveModeSheet({
    Key? key,
    required this.host,
    this.apiKey,
    required this.onClose,
  }) : super(key: key);

  @override
  State<VoilaLiveModeSheet> createState() => _VoilaLiveModeSheetState();
}

class _VoilaLiveModeSheetState extends State<VoilaLiveModeSheet> with SingleTickerProviderStateMixin {
  WebSocketChannel? _channel;
  String _liveState = 'CONNECTING'; // CONNECTING, LISTENING, THINKING, SPEAKING, TOOL_EXEC, DISCONNECTED
  String _userTranscript = '';
  String _aiTranscript = '';
  String _activeToolAction = '';
  bool _isMuted = false;
  final TextEditingController _liveInputController = TextEditingController();
  late AnimationController _pulseController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat(reverse: true);
    _connectLiveWebSocket();
  }

  void _connectLiveWebSocket() {
    try {
      final wsUrl = 'ws://${widget.host}:19890';
      _channel = WebSocketChannel.connect(Uri.parse(wsUrl));

      _channel!.stream.listen(
        (data) {
          try {
            final json = jsonDecode(data.toString()) as Map<String, dynamic>;
            final type = json['type'] as String? ?? '';

            if (type == 'live_state') {
              if (mounted) setState(() => _liveState = json['state'] ?? 'LISTENING');
            } else if (type == 'user_transcript') {
              if (mounted) setState(() => _userTranscript = json['text'] ?? '');
            } else if (type == 'ai_transcript') {
              if (mounted) setState(() => _aiTranscript = json['text'] ?? '');
            } else if (type == 'tool_action') {
              if (mounted) {
                setState(() {
                  _activeToolAction = '${json['tool']}: ${json['status']}';
                });
              }
            } else if (type == 'interrupted') {
              if (mounted) {
                setState(() {
                  _liveState = 'LISTENING';
                  _aiTranscript += ' [Interrupted]';
                });
              }
            }
          } catch (_) {}
        },
        onError: (err) {
          if (mounted) setState(() => _liveState = 'DISCONNECTED');
        },
        onDone: () {
          if (mounted) setState(() => _liveState = 'DISCONNECTED');
        },
      );

      // Send start message
      _channel!.sink.add(jsonEncode({
        'type': 'start',
        'apiKey': widget.apiKey ?? '',
        'model': 'gemini-3.8-live',
      }));
    } catch (e) {
      if (mounted) setState(() => _liveState = 'DISCONNECTED');
    }
  }

  void _sendInterrupt() {
    HapticFeedback.heavyImpact();
    _channel?.sink.add(jsonEncode({'type': 'interrupt'}));
    setState(() => _liveState = 'LISTENING');
  }

  void _sendLiveText() {
    final text = _liveInputController.text.trim();
    if (text.isEmpty) return;
    if (_liveState == 'SPEAKING') {
      _sendInterrupt();
    }
    _channel?.sink.add(jsonEncode({'type': 'text', 'text': text}));
    HapticFeedback.selectionClick();
    setState(() {
      _userTranscript = text;
      _liveInputController.clear();
      _liveState = 'THINKING';
    });
  }

  @override
  void dispose() {
    _liveInputController.dispose();
    _pulseController.dispose();
    _channel?.sink.add(jsonEncode({'type': 'stop'}));
    _channel?.sink.close();
    super.dispose();
  }

  Color _getStateColor() {
    switch (_liveState) {
      case 'SPEAKING':
        return const Color(0xFF00E5FF);
      case 'THINKING':
      case 'TOOL_EXEC':
        return const Color(0xFFF59E0B);
      case 'LISTENING':
        return const Color(0xFF10B981);
      default:
        return const Color(0xFF6B7280);
    }
  }

  @override
  Widget build(BuildContext context) {
    final stateColor = _getStateColor();

    return Container(
      height: MediaQuery.of(context).size.height * 0.75,
      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 16),
      decoration: const BoxDecoration(
        color: Color(0xFF0B0E14),
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      child: Column(
        children: [
          // Drag handle
          Container(width: 40, height: 4, decoration: BoxDecoration(color: Colors.white24, borderRadius: BorderRadius.circular(2))),
          const SizedBox(height: 16),

          // Header
          Row(
            children: [
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  gradient: const LinearGradient(colors: [Color(0xFF6366F1), Color(0xFF8B5CF6)]),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    const Icon(Icons.stream_rounded, size: 14, color: Colors.white),
                    const SizedBox(width: 6),
                    Text(
                      'GEMINI 3.8 LIVE',
                      style: GoogleFonts.spaceGrotesk(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold),
                    ),
                  ],
                ),
              ),
              const Spacer(),
              // Live state pill
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: stateColor.withOpacity(0.15),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: stateColor.withOpacity(0.5)),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(width: 6, height: 6, decoration: BoxDecoration(color: stateColor, shape: BoxShape.circle)),
                    const SizedBox(width: 6),
                    Text(
                      _liveState,
                      style: GoogleFonts.spaceGrotesk(color: stateColor, fontSize: 10, fontWeight: FontWeight.w800),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 12),
              IconButton(
                icon: const Icon(Icons.close_rounded, color: Colors.white70),
                onPressed: widget.onClose,
              ),
            ],
          ),

          const SizedBox(height: 20),

          // Visualizer Area
          Expanded(
            flex: 3,
            child: Center(
              child: Stack(
                alignment: Alignment.center,
                children: [
                  // Pulsing animated glow ring
                  AnimatedBuilder(
                    animation: _pulseController,
                    builder: (context, child) {
                      return Container(
                        width: 140 + (_pulseController.value * 25),
                        height: 140 + (_pulseController.value * 25),
                        decoration: BoxDecoration(
                          shape: BoxShape.circle,
                          color: stateColor.withOpacity(0.06),
                          border: Border.all(color: stateColor.withOpacity(0.2)),
                        ),
                      );
                    },
                  ),
                  AudioVisualizer(
                    isListening: _liveState == 'LISTENING',
                    isSpeaking: _liveState == 'SPEAKING',
                    soundLevel: _liveState == 'LISTENING' ? 0.6 : 0.1,
                  ),
                ],
              ),
            ),
          ),

          // Live tool execution status
          if (_activeToolAction.isNotEmpty)
            Container(
              margin: const EdgeInsets.only(bottom: 12),
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
              decoration: BoxDecoration(
                color: const Color(0xFFF59E0B).withOpacity(0.12),
                borderRadius: BorderRadius.circular(20),
                border: Border.all(color: const Color(0xFFF59E0B).withOpacity(0.4)),
              ),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Icon(Icons.precision_manufacturing_rounded, size: 14, color: Color(0xFFF59E0B)),
                  const SizedBox(width: 6),
                  Text(
                    _activeToolAction,
                    style: GoogleFonts.firaCode(color: const Color(0xFFF59E0B), fontSize: 11, fontWeight: FontWeight.bold),
                  ),
                ],
              ),
            ),

          // Live Transcripts
          Expanded(
            flex: 2,
            child: Container(
              width: double.infinity,
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: const Color(0xFF131822),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(color: Colors.white10),
              ),
              child: SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (_userTranscript.isNotEmpty) ...[
                      Text('YOU', style: GoogleFonts.spaceGrotesk(color: Colors.white54, fontSize: 10, fontWeight: FontWeight.bold)),
                      const SizedBox(height: 2),
                      Text(_userTranscript, style: GoogleFonts.inter(color: Colors.white, fontSize: 13, fontWeight: FontWeight.w600)),
                      const SizedBox(height: 10),
                    ],
                    if (_aiTranscript.isNotEmpty) ...[
                      Text('VOILA LIVE', style: GoogleFonts.spaceGrotesk(color: const Color(0xFF00E5FF), fontSize: 10, fontWeight: FontWeight.bold)),
                      const SizedBox(height: 2),
                      Text(_aiTranscript, style: GoogleFonts.inter(color: const Color(0xFFE2E8F0), fontSize: 13, height: 1.4)),
                    ],
                    if (_userTranscript.isEmpty && _aiTranscript.isEmpty)
                      Center(
                        child: Text(
                          'Speak freely... Gemini Live is listening in real time.',
                          style: GoogleFonts.inter(color: Colors.white38, fontSize: 12),
                        ),
                      ),
                  ],
                ),
              ),
            ),
          ),

          const SizedBox(height: 12),

          // Live Text / Voice Prompt Bar
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xFF131822),
              borderRadius: BorderRadius.circular(100),
              border: Border.all(color: Colors.white12),
            ),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _liveInputController,
                    style: GoogleFonts.inter(color: Colors.white, fontSize: 13),
                    decoration: InputDecoration(
                      hintText: 'Talk or type live with Gemini...',
                      hintStyle: GoogleFonts.inter(color: Colors.white38, fontSize: 13),
                      border: InputBorder.none,
                      contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                    ),
                    onSubmitted: (_) => _sendLiveText(),
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.arrow_upward_rounded, size: 18, color: Color(0xFF00E5FF)),
                  onPressed: _sendLiveText,
                ),
              ],
            ),
          ),

          const SizedBox(height: 12),

          // Bottom Controls: Interrupt, Mute, End
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceEvenly,
            children: [
              // Interrupt Button (Barge-In)
              ElevatedButton.icon(
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF1E2330),
                  foregroundColor: const Color(0xFF00E5FF),
                  padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
                  shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(100),
                    side: const BorderSide(color: Color(0xFF00E5FF), width: 1.2),
                  ),
                ),
                icon: const Icon(Icons.back_hand_rounded, size: 16),
                label: Text('Interrupt AI', style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.bold)),
                onPressed: _sendInterrupt,
              ),

              // Mic Mute toggle
              IconButton(
                iconSize: 28,
                icon: Icon(
                  _isMuted ? Icons.mic_off_rounded : Icons.mic_rounded,
                  color: _isMuted ? _OutputTokens.accentRose : Colors.white,
                ),
                onPressed: () => setState(() => _isMuted = !_isMuted),
              ),

              // End Session
              ElevatedButton(
                style: ElevatedButton.styleFrom(
                  backgroundColor: _OutputTokens.accentRose,
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(100)),
                ),
                child: Text('End Live', style: GoogleFonts.inter(fontSize: 12, fontWeight: FontWeight.bold)),
                onPressed: widget.onClose,
              ),
            ],
          ),
          const SizedBox(height: 8),
        ],
      ),
    );
  }
}
