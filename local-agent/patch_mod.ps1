$mod = Get-Content go.mod -Raw
if ($mod -notmatch "replace voice-cli-system") {
    $mod += "
replace voice-cli-system => ../"
    Set-Content go.mod $mod
}
