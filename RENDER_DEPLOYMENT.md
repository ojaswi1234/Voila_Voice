# Render + GitHub Actions Deployment Guide

## 100% Free Deployment Strategy

**Architecture:**
```
GitHub Actions (Every 10 min) → Render Backend (Stays Awake) → 
Mobile App → WebSocket → Backend → Local Agent
```

---

## 🚀 Deployment Steps

### 1. Push Code to GitHub

```bash
cd voice-cli-system
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/voice-cli-system.git
git push -u origin main
```

### 2. Deploy to Render

**Option A: Via Render Dashboard**
1. Go to [render.com](https://render.com)
2. Sign up/login
3. Click "New +" → "Web Service"
4. Connect your GitHub repository
5. Render will detect `render.yaml` automatically
6. Click "Deploy Web Service"

**Option B: Via Render CLI**
```bash
# Install Render CLI
npm install -g @render/cli

# Login
render login

# Deploy
render deploy
```

### 3. Configure Render Environment Variables

In Render Dashboard → Your Service → Environment Variables:

```
PORT = 10000
DEVICE_1_NAME = Development Laptop
DEVICE_1_ADDRESS = https://your-ngrok-url.ngrok-free.app
DEVICE_2_NAME = Production Server  
DEVICE_2_ADDRESS = https://your-ngrok-url-2.ngrok-free.app
```

### 4. Setup GitHub Actions

**Add GitHub Secret:**
1. Go to your GitHub repository
2. Settings → Secrets and variables → Actions
3. Click "New repository secret"
4. Name: `RENDER_BACKEND_URL`
5. Value: `https://your-backend.onrender.com`
6. Click "Add secret"

**The workflow will automatically start pinging every 10 minutes.**

### 5. Setup ngrok for Local Agent

```bash
# Install ngrok
# Go to ngrok.com, download and install

# Start ngrok for local agent
ngrok http 8088

# Copy the https URL (e.g., https://abc123.ngrok-free.app)
# Update DEVICE_1_ADDRESS in Render environment variables
```

### 6. Update Mobile App for Production

**Option A: Build with environment variable**
```bash
cd mobile-agent
flutter build apk --dart-define=BACKEND_URL=wss://your-backend.onrender.com/ws
```

**Option B: Hardcode for testing**
Update `lib/main.dart`:
```dart
final backendUrl = 'wss://your-backend.onrender.com/ws';
```

### 7. Build APK

```bash
cd mobile-agent
flutter pub get
flutter build apk --release
```

APK location: `build/app/outputs/flutter-apk/app-release.apk`

---

## 🔧 Configuration Files

### render.yaml (Already Created)
```yaml
services:
  - type: web
    name: voice-cli-backend
    runtime: go
    plan: free
    buildCommand: cd backend && go build -o main main.go
    startCommand: cd backend && ./main
    envVars:
      - key: PORT
        value: 10000
      - key: DEVICE_1_ADDRESS
        value: https://your-ngrok-url.ngrok-free.app
```

### .github/workflows/keep-alive.yml (Already Created)
```yaml
name: Keep Render Backend Awake
on:
  schedule:
    - cron: '*/10 * * * *'  # Every 10 minutes
  workflow_dispatch

jobs:
  keep-alive:
    runs-on: ubuntu-latest
    steps:
      - name: Ping Health Endpoint
        run: curl ${{ secrets.RENDER_BACKEND_URL }}/health
```

---

## 🧪 Testing

### Test Health Endpoint Locally:
```powershell
cd voice-cli-system
powershell -ExecutionPolicy Bypass -File test_health.ps1
```

### Test Render Health Endpoint:
```bash
curl https://your-backend.onrender.com/health
```

### Test GitHub Actions:
1. Go to GitHub repository → Actions tab
2. Click "Keep Render Backend Awake" workflow
3. Click "Run workflow" to test manually
4. Check logs for successful pings

---

## 📊 Monitoring

### Check Render Dashboard:
- View logs in Render dashboard
- Monitor CPU/memory usage
- Check uptime metrics

### Check GitHub Actions:
- Actions tab in GitHub repository
- View workflow run history
- Check for failed pings

### Backend Status Endpoint:
```bash
curl https://your-backend.onrender.com/status
```

---

## 🔒 Security

### ngrok Authentication (Recommended):
```bash
ngrok http 8088 --authtoken YOUR_AUTH_TOKEN
```

### Render Environment Variables:
- Never commit secrets to Git
- Use Render environment variables for sensitive data
- Rotate ngrok tokens regularly

---

## 🐛 Troubleshooting

### Backend Sleeps Despite Pings:
- Check GitHub Actions logs
- Verify cron schedule is working
- Try shorter interval (8 minutes)
- Check Render logs for errors

### WebSocket Connection Issues:
- Verify Render backend URL is correct
- Check ngrok is running
- Test with local backend first
- Check mobile app connection settings

### GitHub Actions Not Running:
- Verify workflow file is in `.github/workflows/`
- Check cron syntax is correct
- Ensure repository is public (or has Actions enabled)
- Check GitHub Actions usage limits

---

## 💰 Cost Breakdown

**100% FREE:**
- GitHub: Free (public repository)
- GitHub Actions: Free (2000 minutes/month)
- Render: Free (750 hours/month)
- ngrok: Free (with limitations)
- **Total: $0/month**

---

## 📋 Deployment Checklist

- [ ] Code pushed to GitHub
- [ ] Backend deployed to Render
- [ ] Environment variables configured in Render
- [ ] ngrok running for local agent
- [ ] GitHub Actions workflow active
- [ ] `RENDER_BACKEND_URL` secret added to GitHub
- [ ] Health endpoint tested
- [ ] Mobile app updated with Render URL
- [ ] APK built and tested
- [ ] End-to-end testing completed

---

## 🎯 Summary

**Your system is now configured for 100% free deployment:**

1. **Render**: Hosts backend (free tier)
2. **GitHub Actions**: Keeps Render awake (every 10 minutes)
3. **ngrok**: Tunnels local agent (free)
4. **Mobile App**: Connects to Render backend

**No sleep, no cost, full functionality!**
