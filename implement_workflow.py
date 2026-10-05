import sys

with open('mobile-agent/lib/main.dart', 'r', encoding='utf-8') as f:
    lines = f.read().split('\n')

def replace_method(method_name, new_code):
    global lines
    start = -1
    for i, line in enumerate(lines):
        if f'Widget {method_name}' in line:
            start = i
            break
    if start == -1: return False
    stack = []
    end = start
    for i in range(start, len(lines)):
        for char in lines[i]:
            if char == '{': stack.append('{')
            elif char == '}': 
                if stack: stack.pop()
        if len(stack) == 0 and i > start:
            end = i
            break
    lines = lines[:start] + new_code.split('\n') + lines[end+1:]
    return True

new_workflow = '''  Widget _buildTaskWorkflow(ColorScheme colorScheme) {
    bool isDark = appThemeMode.value == ThemeMode.dark;
    bool isAgent = _currentMode.toUpperCase() == 'AGENT';
    
    // Only show in Agent mode
    if (!isAgent) return const SizedBox.shrink();

    // Get up to 4 most recent tasks for the workflow visualization
    final workflowTasks = _bgTasks.reversed.take(4).toList().reversed.toList();
    if (workflowTasks.isEmpty) return const SizedBox.shrink();

    return Container(
      margin: const EdgeInsets.only(left: 20, right: 20, bottom: 12),
      height: 65,
      child: Center(
        child: ListView.builder(
          scrollDirection: Axis.horizontal,
          shrinkWrap: true,
          itemCount: workflowTasks.length,
          itemBuilder: (context, index) {
            final task = workflowTasks[index];
            final isRunning = task['status'] == 'running';
            final isDone = task['status'] == 'completed' || task['status'] == 'done';
            final isFailed = task['status'] == 'failed' || task['status'] == 'error';
            
            Color nodeColor = AppTokens.border(isDark);
            if (isRunning) nodeColor = AppTokens.accentSecondary;
            else if (isDone) nodeColor = const Color(0xFF10B981);
            else if (isFailed) nodeColor = const Color(0xFFEF4444);

            return Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Column(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Container(
                      width: 24,
                      height: 24,
                      decoration: BoxDecoration(
                        color: isRunning ? nodeColor.withOpacity(0.15) : Colors.transparent,
                        shape: BoxShape.circle,
                        border: Border.all(color: isRunning || isDone || isFailed ? nodeColor : AppTokens.border(isDark), width: isRunning ? 2 : 1.5),
                      ),
                      child: Center(
                        child: isDone
                            ? Icon(Icons.check_rounded, size: 14, color: nodeColor)
                            : (isFailed
                                ? Icon(Icons.close_rounded, size: 14, color: nodeColor)
                                : (isRunning
                                    ? SizedBox(width: 10, height: 10, child: CircularProgressIndicator(color: nodeColor, strokeWidth: 2))
                                    : Icon(Icons.circle, size: 8, color: nodeColor))),
                      ),
                    ),
                    const SizedBox(height: 6),
                    SizedBox(
                      width: 70,
                      child: Text(
                        task['action'] ?? task['id'] ?? 'Task',
                        style: GoogleFonts.inter(
                          color: isRunning ? AppTokens.textPrimary(isDark) : AppTokens.textSecondary(isDark),
                          fontSize: 9,
                          fontWeight: isRunning ? FontWeight.w700 : FontWeight.w500,
                        ),
                        textAlign: TextAlign.center,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                      ),
                    ),
                  ],
                ),
                if (index < workflowTasks.length - 1)
                  Container(
                    width: 30,
                    height: 2,
                    margin: const EdgeInsets.only(top: 11),
                    color: (isDone || isFailed) ? nodeColor.withOpacity(0.5) : AppTokens.border(isDark),
                  ),
              ],
            );
          },
        ),
      ),
    );
  }'''

replace_method('_buildJobStrip', new_workflow)

content = '\n'.join(lines)
content = content.replace('_buildJobStrip(colorScheme),', '_buildTaskWorkflow(colorScheme),')

with open('mobile-agent/lib/main.dart', 'w', encoding='utf-8') as f:
    f.write(content)
print("Workflow implemented.")
