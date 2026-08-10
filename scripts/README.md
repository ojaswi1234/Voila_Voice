# Ngrok Setup Scripts

Automatic ngrok download and setup for the Voila Voice local agent.

## Environment Variables

- `NGROK_AUTHTOKEN` (required): Your ngrok authtoken from https://dashboard.ngrok.com/get-started/your-authtoken
  - Modern ngrok requires authentication for tunnels to work
  - Get your free authtoken from the ngrok dashboard

## Usage

### Python Script
```bash
cd scripts
export NGROK_AUTHTOKEN=your_token_here
python setup_ngrok.py
```

### Node.js Script
```bash
cd scripts
npm install
export NGROK_AUTHTOKEN=your_token_here
npm start
```

## Start Order

1. Start local agent (listens on `localhost:8088`)
2. Start ngrok tunnel (forwards public HTTPS → `localhost:8088`)
3. Agent registration loop picks up public URL from `http://127.0.0.1:4040/api/tunnels`

## How It Works

1. **Download**: Scripts download the latest ngrok v3 binary for your platform
2. **Configure**: Configures authtoken from `NGROK_AUTHTOKEN` environment variable
3. **Start**: Starts ngrok tunnel on port 8088 (local agent port)
4. **API**: Exposes ngrok inspector API on `http://127.0.0.1:4040/api/tunnels`
5. **URL**: Saves public HTTPS URL to `ngrok_url.txt` (optional convenience file)
6. **Integration**: Local agent Go code reads public URL from API for backend registration

## Port Configuration

- **Local agent**: `localhost:8088` (hardcoded in Go code)
- **Ngrok tunnel**: `http 8088` (forwards to local agent)
- **Ngrok API**: `http://127.0.0.1:4040/api/tunnels` (inspector API)
- **Public URL**: HTTPS tunnel (preferred by Go code)

## Platform Support

- Windows (amd64, 386)
- macOS (amd64, arm64)
- Linux (amd64, arm64)

## Troubleshooting

### "NGROK_AUTHTOKEN not set"
```bash
export NGROK_AUTHTOKEN=your_token_here
```

### "Failed to download ngrok"
- Check internet connection
- Try manual download from https://ngrok.com/download

### "No ngrok tunnels found"
- Ensure ngrok started successfully
- Check `http://127.0.0.1:4040/api/tunnels` in browser
- Verify local agent is running on port 8088

### "Backend unreachable"
- Check backend is running on Render
- Verify ngrok tunnel is active
- Check logs for registration errors