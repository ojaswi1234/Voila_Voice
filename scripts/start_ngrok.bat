@echo off
echo Starting ngrok tunnel for port 8088...

REM Check if ngrok is in PATH
where ngrok >nul 2>&1
if %ERRORLEVEL% EQU 0 (
    echo Using ngrok from PATH
    ngrok http 8088
) else (
    echo Ngrok not found in PATH
    echo Please install ngrok from https://ngrok.com/download
    echo Or add it to your system PATH
    pause
)
