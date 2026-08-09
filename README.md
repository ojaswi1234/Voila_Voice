# Voice-to-CLI Remote Execution Service

Zero Trust voice-controlled remote CLI execution system.

## Architecture

- **Mobile Agent**: Flutter app for voice capture and WebSocket communication
- **Backend**: Go server for routing, device registry, and token optimization  
- **Local Agent**: Go CLI (Antigravity) for secure local execution with offline queue

## Deployment Strategy

**100% Free Solution:**
- **Render**: Free tier backend hosting
- **GitHub Actions**: Keep-alive pings every 10 minutes (prevents sleep)
- **ngrok**: Free tunneling for local agent
- **Total Cost**: $0/month

## Quick Start

### 1. Deploy to Render
1. Push code to GitHub
2. Connect repository to Render.com
3. Render auto-detects `render.yaml`
4. Deploy with free tier

### 2. Setup GitHub Actions
1. Add `RENDER_BACKEND_URL` secret to GitHub
2. Workflow auto-runs every 10 minutes
3. Keeps backend awake 24/7

### 3. Setup Local Agent
```bash
cd local-agent
go run main.go
```

### 4. Setup ngrok
```bash
ngrok http 8088
```

### 5. Build Mobile APK
```bash
cd mobile-agent
flutter build apk --dart-define=BACKEND_URL=wss://your-backend.onrender.com/ws
```

## Project Structure

```
voice-cli-system/
├── backend/              # Go backend server
│   ├── main.go          # Main server with health endpoints
│   ├── go.mod           # Go dependencies
│   └── .gitkeep
├── local-agent/         # Go CLI (Antigravity)
│   ├── main.go          # Local execution agent
│   ├── go.mod           # Go dependencies
│   └── .gitkeep
├── mobile-agent/        # Flutter mobile app
│   ├── lib/
│   │   ├── main.dart    # Flutter app with WebSocket
│   │   └── .gitkeep
│   └── pubspec.yaml     # Flutter dependencies
├── .github/
│   └── workflows/
│       └── keep-alive.yml  # GitHub Actions workflow
├── render.yaml          # Render deployment config
├── .gitignore           # Git ignore rules
└── README.md            # This file
```

## Features

### Backend
- ✅ WebSocket server for mobile connections
- ✅ Device registry with multi-device support
- ✅ Token optimization for command efficiency
- ✅ Health check endpoint (`/health`)
- ✅ Status monitoring endpoint (`/status`)
- ✅ AI-powered task summaries
- ✅ Environment variable configuration

### Local Agent
- ✅ HTTP API with Zero Trust authentication
- ✅ PowerShell command execution
- ✅ Offline task queue with JSON persistence
- ✅ Task history tracking
- ✅ Automatic processing of pending tasks

### Mobile App
- ✅ WebSocket client with auto-reconnection
- ✅ Device switching UI
- ✅ Connection status indicators
- ✅ AI summary display
- ✅ Enhanced error handling

## Configuration

### Environment Variables (Render)
```
PORT=10000
DEVICE_1_NAME=Development Laptop
DEVICE_1_ADDRESS=https://your-ngrok-url.ngrok-free.app
DEVICE_2_NAME=Production Server
DEVICE_2_ADDRESS=https://your-ngrok-url-2.ngrok-free.app
```

### GitHub Secrets
- `RENDER_BACKEND_URL`: Your Render backend URL

### Command Optimization
Backend automatically optimizes commands:
- "start the local development server" → "npm run dev"
- "run tests" → "npm test"
- "git status" → "git status"

## API Endpoints

### Backend
- `GET /health` - Health check for keep-alive
- `GET /status` - Detailed status monitoring
- `WS /ws` - WebSocket connection for mobile apps

### Local Agent
- `POST /auth` - Authentication with passphrase
- `POST /execute` - Execute commands
- `POST /queue` - Add to offline queue
- `POST /process` - Process pending tasks
- `GET /history` - Task history

## Security

- ✅ Zero Trust authentication model
- ✅ Passphrase stored locally only
- ✅ Backend has zero knowledge of credentials
- ✅ ngrok provides HTTPS tunneling
- ✅ Environment variables for sensitive data

## Deployment Guide

See `RENDER_DEPLOYMENT.md` for detailed deployment instructions.

## Prerequisites

- Go 1.26+ (for local development)
- Flutter SDK (for mobile app building)
- ngrok account (for local agent tunneling)
- Render account (for backend hosting)
- GitHub account (for Actions workflow)

## License

MIT License - Feel free to use and modify.
