import 'package:flutter/material.dart';

class ConnectionFlowchart extends StatefulWidget {
  final bool isBackendConnected;
  final bool isLocalAgentConnected;
  final bool isWebSocketConnected;
  final bool isDataDeparting;
  final bool isDataArriving;
  final String? activeDeviceName;

  const ConnectionFlowchart({
    super.key,
    required this.isBackendConnected,
    required this.isLocalAgentConnected,
    required this.isWebSocketConnected,
    this.isDataDeparting = false,
    this.isDataArriving = false,
    this.activeDeviceName,
  });

  @override
  State<ConnectionFlowchart> createState() => _ConnectionFlowchartState();
}

class _ConnectionFlowchartState extends State<ConnectionFlowchart>
    with TickerProviderStateMixin {
  late AnimationController _pulseController;
  late Animation<double> _pulseAnimation;
  
  late AnimationController _flowController;

  @override
  void initState() {
    super.initState();
    _pulseController = AnimationController(
      duration: const Duration(milliseconds: 1500),
      vsync: this,
    );
    _pulseAnimation = Tween<double>(begin: 0.6, end: 1.0).animate(
      CurvedAnimation(parent: _pulseController, curve: Curves.easeInOut),
    );
    _pulseController.repeat(reverse: true);

    _flowController = AnimationController(
      duration: const Duration(milliseconds: 1000),
      vsync: this,
    );
    _flowController.repeat();
  }

  @override
  void dispose() {
    _pulseController.dispose();
    _flowController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      height: 76,
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      decoration: BoxDecoration(
        color: const Color(0xFF131316),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: Colors.white.withOpacity(0.05),
          width: 1.0,
        ),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.3),
            blurRadius: 10,
            spreadRadius: 1,
            offset: const Offset(0, 4),
          ),
        ],
      ),
      child: AnimatedBuilder(
        animation: Listenable.merge([_pulseAnimation, _flowController]),
        builder: (context, child) {
          return CustomPaint(
            painter: _ElegantFlowchartPainter(
              pulse: _pulseAnimation.value,
              flow: _flowController.value,
              isBackendConnected: widget.isBackendConnected,
              isLocalAgentConnected: widget.isLocalAgentConnected,
              isWebSocketConnected: widget.isWebSocketConnected,
              isDataDeparting: widget.isDataDeparting,
              isDataArriving: widget.isDataArriving,
            ),
            child: Stack(
              children: [
                Positioned(
                  top: 12, left: 24,
                  child: _buildNodeLabel('Phone', Icons.smartphone, widget.isWebSocketConnected ? Colors.purpleAccent : Colors.grey),
                ),
                Positioned(
                  top: 12, left: MediaQuery.of(context).size.width / 2 - 36,
                  child: _buildNodeLabel('Cloud', Icons.cloud, widget.isBackendConnected ? Colors.blueAccent : Colors.grey),
                ),
                Positioned(
                  top: 12, right: 24,
                  child: _buildNodeLabel(widget.activeDeviceName ?? 'Desktop', Icons.computer, widget.isLocalAgentConnected ? Colors.greenAccent : Colors.grey),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  Widget _buildNodeLabel(String text, IconData icon, Color color) {
    return Column(
      mainAxisSize: MainAxisSize.min,
      crossAxisAlignment: CrossAxisAlignment.center,
      children: [
        Icon(icon, size: 16, color: color),
        const SizedBox(height: 4),
        Text(
          text,
          style: TextStyle(
            fontSize: 10,
            color: color.withOpacity(0.9),
            fontWeight: FontWeight.w600,
            letterSpacing: 0.2,
          ),
        ),
      ],
    );
  }
}

class _ElegantFlowchartPainter extends CustomPainter {
  final double pulse;
  final double flow;
  final bool isBackendConnected;
  final bool isLocalAgentConnected;
  final bool isWebSocketConnected;
  final bool isDataDeparting;
  final bool isDataArriving;

  _ElegantFlowchartPainter({
    required this.pulse,
    required this.flow,
    required this.isBackendConnected,
    required this.isLocalAgentConnected,
    required this.isWebSocketConnected,
    required this.isDataDeparting,
    required this.isDataArriving,
  });

  @override
  void paint(Canvas canvas, Size size) {
    final double nodeY = size.height * 0.7;
    final double phoneX = 40;
    final double cloudX = size.width * 0.5 - 16;
    final double deskX = size.width - 72; // Width minus margin

    // Draw static connection lines
    final linePaint = Paint()
      ..strokeWidth = 2.0
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;

    // Phone -> Cloud Line
    linePaint.color = (isWebSocketConnected && isBackendConnected) ? Colors.blueAccent.withOpacity(0.3) : Colors.grey.withOpacity(0.2);
    canvas.drawLine(Offset(phoneX, nodeY), Offset(cloudX, nodeY), linePaint);
    
    // Cloud -> Desk Line
    linePaint.color = (isBackendConnected && isLocalAgentConnected) ? Colors.greenAccent.withOpacity(0.3) : Colors.grey.withOpacity(0.2);
    canvas.drawLine(Offset(cloudX, nodeY), Offset(deskX, nodeY), linePaint);

    // Draw Data Flow Packets
    if (isDataDeparting && isWebSocketConnected && isBackendConnected && isLocalAgentConnected) {
      _drawDataPacket(canvas, phoneX, cloudX, nodeY, Colors.purpleAccent, flow);
      _drawDataPacket(canvas, cloudX, deskX, nodeY, Colors.blueAccent, flow);
    }
    if (isDataArriving && isWebSocketConnected && isBackendConnected && isLocalAgentConnected) {
      _drawDataPacket(canvas, deskX, cloudX, nodeY, Colors.greenAccent, flow);
      _drawDataPacket(canvas, cloudX, phoneX, nodeY, Colors.blueAccent, flow);
    }

    // Draw Nodes
    _drawGlowingNode(canvas, phoneX, nodeY, isWebSocketConnected ? Colors.purpleAccent : Colors.grey);
    _drawGlowingNode(canvas, cloudX, nodeY, isBackendConnected ? Colors.blueAccent : Colors.grey);
    _drawGlowingNode(canvas, deskX, nodeY, isLocalAgentConnected ? Colors.greenAccent : Colors.grey);
  }

  void _drawDataPacket(Canvas canvas, double startX, double endX, double y, Color color, double progress) {
    final double currentX = startX + (endX - startX) * progress;
    final paint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;
    
    final glow = Paint()
      ..color = color.withOpacity(0.6)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 6);

    canvas.drawCircle(Offset(currentX, y), 5, glow);
    canvas.drawCircle(Offset(currentX, y), 2.5, paint);
  }

  void _drawGlowingNode(Canvas canvas, double x, double y, Color color) {
    final glowRadius = 10.0 * pulse;
    final glowPaint = Paint()
      ..color = color.withOpacity(0.4)
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 8);
    
    canvas.drawCircle(Offset(x, y), glowRadius, glowPaint);
    
    final nodePaint = Paint()
      ..color = color
      ..style = PaintingStyle.fill;
    canvas.drawCircle(Offset(x, y), 4.0, nodePaint);
    
    final corePaint = Paint()
      ..color = Colors.white
      ..style = PaintingStyle.fill;
    canvas.drawCircle(Offset(x, y), 2.0, corePaint);
  }

  @override
  bool shouldRepaint(covariant _ElegantFlowchartPainter oldDelegate) {
    return oldDelegate.pulse != pulse || 
           oldDelegate.flow != flow ||
           oldDelegate.isDataDeparting != isDataDeparting ||
           oldDelegate.isDataArriving != isDataArriving ||
           oldDelegate.isBackendConnected != isBackendConnected ||
           oldDelegate.isLocalAgentConnected != isLocalAgentConnected ||
           oldDelegate.isWebSocketConnected != isWebSocketConnected;
  }
}