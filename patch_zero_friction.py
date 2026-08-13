import re

# 1. Patch main.go (Backend)
with open('main.go', 'r', encoding='utf-8') as f:
    backend_content = f.read()

# Add crypto/rand for random key generation
if '"crypto/rand"' not in backend_content:
    backend_content = backend_content.replace('"crypto/subtle"', '"crypto/rand"\n\t"crypto/subtle"')

# Add global sessionSigningKey
backend_content = backend_content.replace(
    'var (',
    'var (\n\tsessionSigningKey []byte\n'
)

# Generate session key in init or main. We can do it dynamically in createSessionToken/verify if nil
session_key_logic = """
func getSessionSigningKey() []byte {
	if len(sessionSigningKey) > 0 {
		return sessionSigningKey
	}
	key := os.Getenv("SESSION_SIGNING_KEY")
	if key != "" {
		sessionSigningKey = []byte(key)
		return sessionSigningKey
	}
	// Generate random 32-byte key
	sessionSigningKey = make([]byte, 32)
	rand.Read(sessionSigningKey)
	return sessionSigningKey
}
"""
backend_content = backend_content.replace(
    'func createSessionToken(deviceID, clientID string) string {',
    session_key_logic + '\nfunc createSessionToken(deviceID, clientID string) string {'
)

# Update createSessionToken
old_create = """	secret := os.Getenv("SESSION_SIGNING_KEY")
	if secret == "" {
		secret = "default_unsafe_secret"
	}
	payload := map[string]interface{}{"""
new_create = """	secret := getSessionSigningKey()
	payload := map[string]interface{}{"""
backend_content = backend_content.replace(old_create, new_create)

# Update verifySessionToken
old_verify = """	secret := os.Getenv("SESSION_SIGNING_KEY")
	if secret == "" {
		secret = "default_unsafe_secret"
	}"""
new_verify = """	secret := getSessionSigningKey()"""
backend_content = backend_content.replace(old_verify, new_verify)
backend_content = backend_content.replace(
    """mac.Write([]byte(dataPart))
	expectedSignature := hex.EncodeToString(mac.Sum(nil))""",
    """mac.Write([]byte(dataPart))
	expectedSignature := hex.EncodeToString(mac.Sum(nil))"""
) # ensure we use secret not []byte(secret)
backend_content = backend_content.replace('mac := hmac.New(sha256.New, []byte(secret))', 'mac := hmac.New(sha256.New, secret)')

# Remove AGENT_REGISTER_SECRET
old_register = """	// Shared secret so random internet clients can't register devices
	expected := os.Getenv("AGENT_REGISTER_SECRET")
	if expected == "" {
		http.Error(w, "Registration disabled", http.StatusServiceUnavailable)
		return
	}
	if r.Header.Get("X-Agent-Secret") != expected {
		log.Printf("Registration denied: invalid or missing X-Agent-Secret header")
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}"""
backend_content = backend_content.replace(old_register, "\t// AGENT_REGISTER_SECRET removed for zero-friction mode. Open registration.")

# Replace AGENT_EXEC_SECRET with SecurityPhraseHash
old_exec_secret = """	if execSecret := os.Getenv("AGENT_EXEC_SECRET"); execSecret != "" {
		req.Header.Set("X-Exec-Secret", execSecret)
	}"""
new_exec_secret = """	req.Header.Set("X-Exec-Secret", device.SecurityPhraseHash)"""
backend_content = backend_content.replace(old_exec_secret, new_exec_secret)

# Remove CLEAR_DATA_SECRET from HTTP handler
old_clear = """	adminSecret := os.Getenv("CLEAR_DATA_SECRET")
	if adminSecret == "" || req.SecurityPhrase != adminSecret {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}"""
new_clear = """	// In zero-friction mode, we require a valid security phrase matching the active device
	backend.mu.RLock()
	var expectedHash string
	if backend.activeDevice != "" && backend.devices[backend.activeDevice] != nil {
		expectedHash = backend.devices[backend.activeDevice].SecurityPhraseHash
	}
	backend.mu.RUnlock()
	
	if expectedHash == "" || hashPhrase(req.SecurityPhrase, backend.activeDevice) != expectedHash {
		http.Error(w, "Unauthorized", http.StatusUnauthorized)
		return
	}"""
backend_content = backend_content.replace(old_clear, new_clear)

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(backend_content)


# 2. Patch local-agent/main.go
with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    agent_content = f.read()

# Add hashPhrase if missing
hash_logic = """
func hashPhrase(phrase, deviceID string) string {
	h := sha256.New()
	h.Write([]byte(phrase + ":" + deviceID))
	return hex.EncodeToString(h.Sum(nil))
}
"""
if "func hashPhrase(" not in agent_content:
    agent_content = agent_content.replace("func main() {", hash_logic + "\nfunc main() {")

# Update startHTTPServer to use SecurityPhraseHash
old_execute = """		expectedSecret := os.Getenv("AGENT_EXEC_SECRET")
		if expectedSecret != "" {
			providedSecret := r.Header.Get("X-Exec-Secret")
			if subtle.ConstantTimeCompare([]byte(providedSecret), []byte(expectedSecret)) != 1 {
				http.Error(w, "Unauthorized", http.StatusUnauthorized)
				return
			}
		}"""
new_execute = """		// Zero-friction mode: Authenticate using SecurityPhraseHash
		connData, err := loadConnectionData()
		if err != nil || connData.SecurityPhrase == "" {
			http.Error(w, "Agent not configured", http.StatusServiceUnavailable)
			return
		}
		expectedSecret := hashPhrase(connData.SecurityPhrase, connData.DeviceID)
		providedSecret := r.Header.Get("X-Exec-Secret")
		if subtle.ConstantTimeCompare([]byte(providedSecret), []byte(expectedSecret)) != 1 {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}"""
agent_content = agent_content.replace(old_execute, new_execute)

# Remove X-Agent-Secret from registerWithBackend
old_reg_header = """	req.Header.Set("Content-Type", "application/json")
	if secret := os.Getenv("AGENT_REGISTER_SECRET"); secret != "" {
		req.Header.Set("X-Agent-Secret", secret)
	}"""
new_reg_header = """	req.Header.Set("Content-Type", "application/json")"""
agent_content = agent_content.replace(old_reg_header, new_reg_header)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(agent_content)
