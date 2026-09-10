$ErrorActionPreference = "Continue"

Start-Process -FilePath ".\server.exe" -NoNewWindow -RedirectStandardOutput "server.log" -RedirectStandardError "server_err.log"
Start-Process -FilePath ".\local-agent\agent.exe" -NoNewWindow -RedirectStandardOutput "agent.log" -RedirectStandardError "agent_err.log"
Start-Sleep -Seconds 3

function Test-Endpoint {
    param($name, $url, $body)
    Write-Host "
=== $name ==="
    try {
        $req = [System.Net.WebRequest]::Create($url)
        $req.Method = "POST"
        $req.ContentType = "application/json"
        $req.Headers.Add("X-Exec-Secret", "wrong")
        $bytes = [System.Text.Encoding]::UTF8.GetBytes($body)
        $req.ContentLength = $bytes.Length
        $stream = $req.GetRequestStream()
        $stream.Write($bytes, 0, $bytes.Length)
        $stream.Close()
        
        $resp = $req.GetResponse()
        $reader = New-Object System.IO.StreamReader($resp.GetResponseStream())
        Write-Host "Success:
" $reader.ReadToEnd()
    } catch {
        if ($_.Exception.Response) {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            Write-Host "HTTP Error ($(.Exception.Response.StatusCode)):
" $reader.ReadToEnd()
        } else {
            Write-Host $_.Exception.Message
        }
    }
}

Test-Endpoint "T2.1 Direct-to-agent decoy test" "http://localhost:8088/execute" '{"command": "whoami"}'
Test-Endpoint "T2.4 Local threshold/lockdown test (Attempt 2)" "http://localhost:8088/execute" '{"command": "whoami"}'
Test-Endpoint "T2.4 Local threshold/lockdown test (Attempt 3)" "http://localhost:8088/execute" '{"command": "whoami"}'
Test-Endpoint "T2.4 Local threshold/lockdown test (Attempt 4)" "http://localhost:8088/execute" '{"command": "whoami"}'
Test-Endpoint "T2.5 /circuit endpoint" "http://localhost:8088/circuit" '{"state": "closed"}'

Stop-Process -Name server -ErrorAction SilentlyContinue
Stop-Process -Name agent -ErrorAction SilentlyContinue
