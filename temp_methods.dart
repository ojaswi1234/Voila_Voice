  void _cancelJob() {
    if (_activeJobId == null) return;
    _channel?.sink.add(jsonEncode({
      'type': 'cancel_job',
      'job_id': _activeJobId,
      'session_token': _sessionToken,
    }));
    setState(() {
      _activeJobStatus = 'cancelling';
    });
  }

  Widget _buildJobStrip(ColorScheme colorScheme) {
    if (_activeJobId == null || _activeJobStatus == '') return const SizedBox.shrink();
    
    Color statusColor = colorScheme.primary;
    IconData icon = Icons.sync;
    bool spinner = false;
    
    switch (_activeJobStatus) {
      case 'running':
        statusColor = colorScheme.primary;
        spinner = true;
        break;
      case 'waiting_approval':
        statusColor = Colors.orange;
        icon = Icons.warning_amber_rounded;
        break;
      case 'done':
        statusColor = Colors.green;
        icon = Icons.check_circle;
        break;
      case 'failed':
      case 'cancelled':
        statusColor = Colors.red;
        icon = Icons.error_outline;
        break;
      case 'cancelling':
        statusColor = Colors.grey;
        spinner = true;
        break;
    }

    return AnimatedContainer(
      duration: const Duration(milliseconds: 300),
      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
      decoration: BoxDecoration(
        color: statusColor.withOpacity(0.15),
        border: Border.all(color: statusColor.withOpacity(0.3)),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          spinner 
            ? SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: statusColor))
            : Icon(icon, color: statusColor, size: 18),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Job: \', style: TextStyle(color: statusColor, fontSize: 10, fontWeight: FontWeight.bold)),
                Text(_activeJobSummary, style: const TextStyle(color: Colors.white, fontSize: 13), maxLines: 1, overflow: TextOverflow.ellipsis),
              ],
            ),
          ),
          if (_activeJobStatus == 'running' || _activeJobStatus == 'waiting_approval')
            IconButton(
              icon: const Icon(Icons.cancel, color: Colors.white54, size: 20),
              onPressed: _cancelJob,
              padding: EdgeInsets.zero,
              constraints: const BoxConstraints(),
            ),
        ],
      ),
    );
  }
