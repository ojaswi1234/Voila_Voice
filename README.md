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
- **ngrok**: Free tunneling for local agent (automated)
- **Total Cost**: $0/month

## Quick Start

### 1. Start All Services (Windows)
```bash
start_all.bat
```

### 2. Manual Setup (All Platforms)
```bash
# Terminal 1: Start local agent (TUI)
cd local-agent
go run main.go

# Terminal 2: Start ngrok (automated)
cd scripts
python setup_ngrok.py  # or: npm install && npm start

# Terminal 3: Start backend with auto-detection
cd backend
NGROK_AUTO_DETECT=true go run main.go
```

### 3. Deploy to Render
1. Push code to GitHub
2. Connect repository to Render.com
3. Update Render environment variables with ngrok URL
4. Deploy with free tier

### 4. Setup GitHub Actions
1. Add `RENDER_BACKEND_URL` secret to GitHub
2. Workflow auto-runs every 10 minutes
3. Keeps backend awake 24/7

### 5. Build Mobile APK
```bash
cd mobile-agent
flutter build apk --dart-define=BACKEND_URL=wss://your-backend.onrender.com/ws
```

## Project Structure

```
voice-cli-system/
├── backend/              # Go backend server
│   ├── main.go          # Main server with health endpoints & ngrok auto-detect
│   ├── go.mod           # Go dependencies
│   └── .gitkeep
├── local-agent/         # Go CLI (Antigravity)
│   ├── main.go           # Local execution agent
│   ├── go.mod           # Go dependencies
│   └── .gitkeep
├── mobile-agent/        # Flutter mobile app
│   ├── lib/
│   │   ├── main.dart    # Flutter app with health checks & connection flow
│   │   └── .gitkeep
│   └── pubspec.yaml     # Flutter dependencies
├── scripts/              # Automation scripts
│   ├── setup_ngrok.py   # Python ngrok automation (no dependencies)
│   ├── setup_ngrok.js   # Node.js ngrok automation
│   ├── package.json     # Node.js dependencies
│   └── .gitkeep
├── .github/
│   └── workflows/
│       └── keep-alive.yml  # GitHub Actions workflow
├── render.yaml          # Render deployment config
├── start_all.bat         # Windows startup script
├── .gitignore           # Git ignore rules
└── README.md            # This file
```

## Features

### Backend
- ✅ WebSocket server for mobile connections
- ✅ Device registry with multi-device support
- ✅ **Device locking** (1 laptop = 1 mobile device at a time)
- ✅ Multi-client support (1 mobile app = multiple laptops)
- ✅ Token optimization for command efficiency
- ✅ Health check endpoint (`/health`)
- ✅ Status monitoring endpoint (`/status`)
- ✅ AI-powered task summaries
- ✅ **Automatic ngrok URL detection** (when enabled)
- ✅ Manual device address update endpoint
- ✅ Environment variable configuration

### Local Agent
- ✅ **TUI interface** with bubbletea for setup and management
- ✅ **One-time connection setup** with interactive wizard
- ✅ **Auto-start on device boot** after initial setup
- ✅ **Device management** with delete connection option
- ✅ **Stop/start controls** for service management
- ✅ **Security disconnect** handling for auth/anomaly issues
- ✅ HTTP API with Zero Trust authentication
- ✅ PowerShell command execution
- ✅ Offline task queue with JSON persistence
- ✅ Task history tracking
- ✅ Automatic processing of pending tasks

### Mobile App
- ✅ WebSocket client with auto-reconnection
- ✅ **Health check monitoring** (every 30 seconds)
- ✅ **Connection flow visualization** (Mobile → Backend → Local Agent)
- ✅ Device switching UI with lock status
- ✅ **Device lock/unlock controls**
- ✅ Connection status indicators
- ✅ AI summary display
- ✅ Enhanced error handling

### Automation Scripts
- ✅ **Python ngrok setup** (no external dependencies)
- ✅ **Node.js ngrok setup** (npm install required)
- ✅ **Automatic ngrok download** (cross-platform)
- ✅ **Automatic URL extraction** from ngrok API
- ✅ **URL persistence** for backend detection

## Configuration

### Environment Variables
```bash
# Backend
PORT=10000
NGROK_AUTO_DETECT=true  # Enable automatic ngrok URL detection
DEVICE_1_NAME=Development Laptop
DEVICE_1_ADDRESS=http://localhost:8088  # Auto-updated when NGROK_AUTO_DETECT=true
DEVICE_2_NAME=Production Server
DEVICE_2_ADDRESS=http://localhost:8091
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
- `POST /update-device` - Manual device address update
- `WS /ws` - WebSocket connection for mobile apps

### WebSocket Messages
- `{"type": "command", "device_id": "laptop-1", "command": "npm run dev"}` - Execute command
- `{"type": "switch_device", "device_id": "laptop-2"}` - Switch active device
- `{"type": "lock_device", "device_id": "laptop-1"}` - Lock device for exclusive access
- `{"type": "unlock_device", "device_id": "laptop-1"}` - Unlock device
- `{"type": "get_devices"}` - Get device list with lock status
- `{"type": "get_stats"}` - Get system statistics

### Local Agent
- `POST /auth` - Authentication with passphrase
- `POST /execute` - Execute commands
- `POST /queue` - Add to offline queue
- `POST /process` - Process pending tasks
- `GET /history` - Task history

## Device Locking System

**Constraint:** 1 laptop = 1 mobile device at a time (1 mobile app = multiple laptops)

**How it works:**
- Mobile devices get unique client IDs on connection
- Locking prevents conflicts between multiple mobile users
- Commands automatically lock/unlock during execution
- Manual lock/unlock available for extended sessions
- Auto-unlock on client disconnection

**Use cases:**
- Team collaboration with shared laptops
- Preventing command conflicts
- Managing exclusive access to devices
- Session-based device control

## Local Agent TUI

**Interactive Terminal Interface:**
- One-time setup wizard for connection configuration
- Enter backend URL, device name, and passphrase
- Visual feedback with styled UI elements
- Auto-saves connection data for future use

**Menu Options:**
- **Stop/Start Service** - Control local agent HTTP server
- **Delete Connection** - Remove saved connection data
- **View Status** - Check connection and server status
- **Exit** - Clean shutdown

**Auto-Start:**
- After initial setup, creates startup script
- Automatically starts on device boot
- Runs in background with saved connection
- No manual intervention needed

**Security Features:**
- Security disconnect handling for auth anomalies
- Immediate service stop on security events
- Connection deletion option for compromised credentials
- Passphrase stored locally only (Zero Trust)

## Ngrok Automation

### Python Script (Recommended)
```bash
cd scripts
python setup_ngrok.py
```
- No external dependencies
- Cross-platform support
- Automatic download and setup

### Node.js Script
```bash
cd scripts
npm install
npm start
```
- Requires npm install
- Uses unzipper package
- Graceful shutdown

### Backend Auto-Detection
```bash
NGROK_AUTO_DETECT=true go run main.go
```
- Checks ngrok API every 30 seconds
- Auto-updates device address
- No manual URL configuration needed

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
- Python 3.x (for ngrok automation) OR Node.js 14+ (alternative)
- Render account (for backend hosting)
- GitHub account (for Actions workflow)

## License

MIT License - Feel free to use and modify.
