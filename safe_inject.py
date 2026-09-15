import sys

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    text = f.read()

# 1. Inject toolUsageSummary and guardrails into executeOllamaCommand
ollama_prompt_start = """	var systemPrompt string
	if strings.HasPrefix(taskID, "node-") {
		systemPrompt = `You are a highly advanced AI agent participating in a distributed Graphify workflow."""

new_ollama_prompt = """	var toolUsageSummary strings.Builder
	var systemPrompt string
	if strings.HasPrefix(taskID, "node-") {
		systemPrompt = `You are a highly advanced AI agent participating in a distributed Graphify workflow."""
text = text.replace(ollama_prompt_start, new_ollama_prompt, 1)

old_ollama_guardrail = """3. ONCE YOU HAVE ACHIEVED YOUR SPECIFIC NODE'S GOAL, YOU MUST STOP CALLING TOOLS IMMEDIATELY. Output your final response text and do NOT include any tool calls in your final message, otherwise you will be trapped in an infinite loop.
4. If you have all the information you need from the context, do NOT call tools just to verify it. Just output the final result.`
	} else {"""
new_ollama_guardrail = """3. ONCE YOU HAVE ACHIEVED YOUR SPECIFIC NODE'S GOAL, YOU MUST STOP CALLING TOOLS IMMEDIATELY. Output your final response text and do NOT include any tool calls in your final message, otherwise you will be trapped in an infinite loop.
4. If you have all the information you need from the context, do NOT call tools just to verify it. Just output the final result.
5. SECURITY GUARDRAILS: You are operating in a sandboxed environment. Do NOT execute destructive terminal commands (e.g., del, format, rm -rf, diskpart). Do NOT modify system registries, alter user permissions, or access secure credentials. Any attempt to bypass system security will be logged and terminated.`
	} else {"""
text = text.replace(old_ollama_guardrail, new_ollama_guardrail, 1)

old_ollama_tools = """		// Execute each tool and collect results
		for _, tc := range result.Message.ToolCalls {
			debugLog.Printf("================================================================")
			debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] 2. TOOL EXECUTION PHASE")"""
new_ollama_tools = """		// Execute each tool and collect results
		for _, tc := range result.Message.ToolCalls {
			toolUsageSummary.WriteString(fmt.Sprintf("> Executed tool: %s (args: %s)\\n", tc.Function.Name, string(tc.Function.Arguments)))
			debugLog.Printf("================================================================")
			debugLog.Printf("[DEBUG_LIFECYCLE: OLLAMA] 2. TOOL EXECUTION PHASE")"""
text = text.replace(old_ollama_tools, new_ollama_tools, 1)

old_ollama_final = """			debugLog.Printf("================================================================")
			debugLog.Printf("[executeOllamaCommand] iter=%d final answer len=%d", iter, len(result.Message.Content))
			finalAnswer := strings.TrimSpace(result.Message.Content)
			saveCloudHistory(convID, command, finalAnswer)
			return finalAnswer, nil"""
new_ollama_final = """			debugLog.Printf("================================================================")
			debugLog.Printf("[executeOllamaCommand] iter=%d final answer len=%d", iter, len(result.Message.Content))
			finalAnswer := strings.TrimSpace(result.Message.Content)
			if toolUsageSummary.Len() > 0 {
				finalAnswer = "Actions taken during execution:\\n" + toolUsageSummary.String() + "\\nFinal Output:\\n" + finalAnswer
			}
			saveCloudHistory(convID, command, finalAnswer)
			return finalAnswer, nil"""
text = text.replace(old_ollama_final, new_ollama_final, 1)

# 2. Inject toolUsageSummary and guardrails into executeGroqCommand
groq_prompt_start = """	var systemPrompt string
	if strings.HasPrefix(taskID, "node-") {
		systemPrompt = `You are a highly advanced AI agent participating in a distributed Graphify workflow."""

# Find the second occurrence (which is groq, since ollama was replaced)
idx = text.find(groq_prompt_start)
if idx != -1:
    text = text[:idx] + new_ollama_prompt + text[idx+len(groq_prompt_start):]

# Groq guardrails
idx = text.find(old_ollama_guardrail)
if idx != -1:
    text = text[:idx] + new_ollama_guardrail + text[idx+len(old_ollama_guardrail):]

old_groq_tools = """		// Execute each tool and collect results
		for _, tc := range choice.Message.ToolCalls {
			debugLog.Printf("================================================================")
			debugLog.Printf("[DEBUG_LIFECYCLE: GROQ] 2. TOOL EXECUTION PHASE")"""
new_groq_tools = """		// Execute each tool and collect results
		for _, tc := range choice.Message.ToolCalls {
			toolUsageSummary.WriteString(fmt.Sprintf("> Executed tool: %s (args: %s)\\n", tc.Function.Name, string(tc.Function.Arguments)))
			debugLog.Printf("================================================================")
			debugLog.Printf("[DEBUG_LIFECYCLE: GROQ] 2. TOOL EXECUTION PHASE")"""
text = text.replace(old_groq_tools, new_groq_tools, 1)

old_groq_final = """			debugLog.Printf("================================================================")
			debugLog.Printf("[executeGroqCommand] iter=%d final answer len=%d", iter, len(choice.Message.Content))
			finalAnswer := strings.TrimSpace(choice.Message.Content)
			saveCloudHistory(convID, command, finalAnswer)
			return finalAnswer, nil"""
new_groq_final = """			debugLog.Printf("================================================================")
			debugLog.Printf("[executeGroqCommand] iter=%d final answer len=%d", iter, len(choice.Message.Content))
			finalAnswer := strings.TrimSpace(choice.Message.Content)
			if toolUsageSummary.Len() > 0 {
				finalAnswer = "Actions taken during execution:\\n" + toolUsageSummary.String() + "\\nFinal Output:\\n" + finalAnswer
			}
			saveCloudHistory(convID, command, finalAnswer)
			return finalAnswer, nil"""
text = text.replace(old_groq_final, new_groq_final, 1)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(text)

print("Safely injected into main.go!")
