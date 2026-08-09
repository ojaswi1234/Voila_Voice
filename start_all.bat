@echo off
echo Starting Voice CLI System...

echo Starting Local Agent (TUI)...
start "Local Agent" cmd /k "cd local-agent && go run main.go"

timeout /t 3

echo Starting Ngrok...
start "Ngrok" cmd /k "cd scripts && python setup_ngrok.py"

timeout /t 5

echo Starting Backend with Ngrok Auto-Detection...
start "Backend" cmd /k "set NGROK_AUTO_DETECT=true && go run main.go"

echo All services started!
echo Local Agent: TUI Setup in new window
echo Backend: localhost:8090
echo Ngrok: Running in separate window

