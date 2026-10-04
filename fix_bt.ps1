$content = Get-Content local-agent\background_tasks.go -Raw
$content = $content -replace '(?s)Label          string    json:"label".*?// Runtime-only', "Label          string    `json:"label"`
	ConversationID string    `json:"conversation_id"`

	// Runtime-only"
Set-Content local-agent\background_tasks.go $content
