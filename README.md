<div align="center">
  <h1>🎙️ Voila: Your Floating AI CLI Assistant</h1>
  <p><i>A Zero-Trust, Voice-Controlled Remote Execution System that brings an interactive AI companion to your desktop.</i></p>
</div>

---

## 🌟 Meet Voila

Say goodbye to boring, static terminal windows. **Voila** is an interactive, animated AI agent that floats elegantly on your desktop. She listens to your voice via your mobile device, instantly parses your natural language into powerful CLI commands (powered by Antigravity), and executes them securely on your machine from anywhere in the world. 

Whenever Voila is thinking, executing commands, or waiting for instructions, her facial expressions and dynamic thought-bubble react in real-time, giving you an unparalleled interactive experience.

## 🚀 How It Works

This system is built on a highly secure, distributed architecture ensuring your laptop can be controlled remotely with **Zero Trust**.

1. **📱 Mobile Agent (Flutter)**: A beautiful mobile app that captures your voice commands, displays execution results, and allows you to switch between multiple connected desktop devices.
2. **☁️ Cloud Relay (Go)**: A lightweight Go server deployed to the cloud (e.g., Render) that proxies WebSocket connections and maintains device registries and live presence—without ever knowing your security credentials.
3. **💻 Local Agent (Go + Python UI)**: The brains of the operation. Running directly on your Windows/Mac/Linux machine, it uses `ngrok` for secure tunneling. It features the **Voila Floating Widget** (built in Python/Tkinter) wrapped around the robust `antigravity` Go binary.

## ✨ Features

### 🎭 The Voila Desktop Widget
- **Interactive Personality**: Dynamic, vector-based facial expressions based on real-time execution states (Idle, Thinking, Executing, Offline).
- **Live Thought Cloud**: Watch exactly what Voila is doing or executing directly in her floating thought bubble.
- **Pixel-Perfect UI**: Carefully designed so she looks right at home on a modern desktop.
- **Zero-Zombie Guarantee**: Robust process management ensures no orphaned background tasks remain when she goes to sleep.

### 🔒 Zero-Trust Security
- **No Shared Secrets**: Your security phrase never leaves your devices. The cloud relay only routes traffic and verifies cryptographic hashes.
- **Device Locking**: (1 Laptop = 1 Mobile Device). Prevents conflicting commands if multiple people try to access a shared machine.
- **End-to-End Tunneling**: Free automated HTTPS `ngrok` tunneling ensures completely secure execution pipelines.

### ⚡ AI-Powered Execution
- Select between multiple LLMs (Gemini Flash/Pro, Claude Sonnet, etc.) on the fly from the mobile app.
- "Start the local development server" seamlessly becomes `npm run dev` or `go run main.go`.
- Chat history, conversational memory, and task summaries are built right in.

---

## 🛠️ Quick Start Guide

### 1. Configure Environment
Create a `.env` file in the project root:
```env
NGROK_AUTHTOKEN=your_ngrok_authtoken_here
AGENT_REGISTER_SECRET=your_registration_secret_here
CLEAR_DATA_SECRET=your_clear_data_secret_here
```

*(Windows users: You can permanently set these via `setx NGROK_AUTHTOKEN "token"`)*

### 2. Fire Up The Relay Server (Cloud/Local)
To run the Go cloud relay locally for testing:
```bash
NGROK_AUTO_DETECT=true go run main.go
```
*(For production, deploy this root directory to Render.com and set your `AGENT_REGISTER_SECRET` in their dashboard.)*

### 3. Awaken Voila (Local Agent)
```bash
cd local-agent
start_agent.bat
```
Watch Voila spring to life on your desktop! She will automatically manage the ngrok tunneling and connect to your cloud relay.

### 4. Connect the Mobile App
```bash
cd mobile-agent
flutter build apk --dart-define=BACKEND_URL=wss://your-backend.onrender.com/ws
```
Install the APK on your phone, enter your backend URL and secure phrase, and start talking to your desktop!

---

## 📂 Project Structure

- `/backend` - *(Deprecated)* Merged into the root `main.go`.
- `/local-agent` - The secure Go CLI combined with the Python-based Voila floating widget.
- `/mobile-agent` - The Flutter application for voice control and remote system monitoring.
- `/scripts` - Utilities for auto-provisioning `ngrok` environments.

## 🤝 Contributing
Built with ❤️ for modern developers. Pull requests are welcome!

## 📜 License
MIT License - Free to use and modify.
