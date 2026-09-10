import io

with open('local-agent/main.go', 'r', encoding='utf-8') as f:
    content = f.read()

old_code = '''		outBytes, _ := cmdObj.CombinedOutput()'''

new_code = '''		// Bug #21 Fix: Prevent RAM exhaustion on massive outputs
		stdoutReader, _ := cmdObj.StdoutPipe()
		stderrReader, _ := cmdObj.StderrPipe()
		cmdObj.Start()
		
		outReader := io.MultiReader(stdoutReader, stderrReader)
		var outBuf bytes.Buffer
		buf := make([]byte, 1024)
		totalBytes := 0
		maxBytes := 2 * 1024 * 1024 // 2MB limit
		
		for {
			n, err := outReader.Read(buf)
			if n > 0 {
				if totalBytes+n > maxBytes {
					outBuf.Write(buf[:maxBytes-totalBytes])
					outBuf.WriteString("\\n... [OUTPUT TRUNCATED (2MB LIMIT)]")
					break
				}
				outBuf.Write(buf[:n])
				totalBytes += n
			}
			if err != nil {
				break
			}
		}
		cmdObj.Wait()
		outBytes := outBuf.Bytes()'''

if old_code in content:
    content = content.replace(old_code, new_code)
    with open('local-agent/main.go', 'w', encoding='utf-8') as f:
        f.write(content)
    print('Patched Bug #21')
else:
    print('Could not find old_code')
