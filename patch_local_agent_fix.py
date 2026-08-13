import re

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    code = f.read()

# Fix 1: Add "sync" to imports
if '"sync"' not in code:
    code = code.replace(
        '"strings"',
        '"strings"\n\t"sync"'
    )

# Fix 2: Update auth check in /stop
bad_auth = '''		secretHeader := r.Header.Get("X-Exec-Secret")
		if secretHeader != connData.SecurityPhraseHash {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}'''
good_auth = '''		expectedSecret := hashPhrase(connData.SecurityPhrase, connData.DeviceID)
		providedSecret := r.Header.Get("X-Exec-Secret")
		if subtle.ConstantTimeCompare([]byte(providedSecret), []byte(expectedSecret)) != 1 {
			http.Error(w, "Unauthorized", http.StatusUnauthorized)
			return
		}'''
code = code.replace(bad_auth, good_auth)

with open('local-agent/main.go', 'w', encoding='utf-8') as f:
    f.write(code)

print("Patched local-agent/main.go")
