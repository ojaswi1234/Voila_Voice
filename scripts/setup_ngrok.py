#!/usr/bin/env python3
"""
Automatic Ngrok Download and Setup Script
Downloads ngrok and starts tunnel for local agent
"""

import os
import sys
import platform
import urllib.request
import zipfile
import subprocess
import json
import time
from pathlib import Path

def get_ngrok_download_url():
    """Get the appropriate ngrok download URL for the current platform"""
    system = platform.system().lower()
    machine = platform.machine().lower()
    
    # Use official ngrok download URLs (2025-2026 compatible)
    base_url = "https://dl.ngrok.com/ngrok-v3-stable-"
    
    if system == "windows":
        if machine == "amd64":
            return base_url + "windows-amd64.zip"
        else:
            return base_url + "windows-386.zip"
    elif system == "darwin":
        if machine == "arm64":
            return base_url + "darwin-arm64.zip"
        else:
            return base_url + "darwin-amd64.zip"
    elif system == "linux":
        if machine == "arm64":
            return base_url + "linux-arm64.zip"
        else:
            return base_url + "linux-amd64.zip"
    else:
        raise Exception(f"Unsupported platform: {system}")

def configure_authtoken(ngrok_path):
    """Configure ngrok authtoken from environment"""
    authtoken = os.environ.get("NGROK_AUTHTOKEN")
    if not authtoken:
        print("WARNING: NGROK_AUTHTOKEN not set. ngrok may not work without authentication.")
        print("Get your free authtoken from https://dashboard.ngrok.com/get-started/your-authtoken")
        return False
    
    try:
        print("Configuring ngrok authtoken...")
        subprocess.run([ngrok_path, "config", "add-authtoken", authtoken], 
                      check=True, capture_output=True, text=True)
        print("Authtoken configured successfully.")
        return True
    except subprocess.CalledProcessError as e:
        print(f"ERROR: Failed to configure authtoken: {e.stderr}")
        return False

def download_ngrok():
    """Download ngrok for the current platform"""
    print("Downloading ngrok...")
    
    url = get_ngrok_download_url()
    filename = url.split("/")[-1]
    
    # Create scripts directory
    scripts_dir = Path(__file__).parent
    ngrok_path = scripts_dir / filename
    
    # Download file
    try:
        urllib.request.urlretrieve(url, ngrok_path)
        print(f"Downloaded: {filename}")
    except Exception as e:
        raise Exception(f"Failed to download ngrok: {e}")
    
    # Extract zip file
    print("Extracting ngrok...")
    with zipfile.ZipFile(ngrok_path, 'r') as zip_ref:
        zip_ref.extractall(scripts_dir)
    
    # Remove zip file
    ngrok_path.unlink()
    
    # Find ngrok executable
    if platform.system().lower() == "windows":
        ngrok_exe = scripts_dir / "ngrok.exe"
    else:
        ngrok_exe = scripts_dir / "ngrok"
    
    if ngrok_exe.exists():
        # Make executable on Unix-like systems
        if platform.system().lower() != "windows":
            ngrok_exe.chmod(0o755)
        print(f"Ngrok installed at: {ngrok_exe}")
        return str(ngrok_exe)
    else:
        raise Exception("Ngrok executable not found after extraction")

def start_ngrok(ngrok_path, port=8088):
    """Start ngrok tunnel for the specified port"""
    print(f"Starting ngrok tunnel for port {port}...")
    
    # Start ngrok
    if platform.system().lower() == "windows":
        process = subprocess.Popen(
            [ngrok_path, "http", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP
        )
    else:
        process = subprocess.Popen(
            [ngrok_path, "http", str(port)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
    
    # Wait for ngrok to start
    time.sleep(3)
    
    # Get ngrok URL from API - prefer HTTPS
    try:
        response = urllib.request.urlopen("http://127.0.0.1:4040/api/tunnels")
        data = json.loads(response.read().decode())
        
        if data.get("tunnels") and len(data["tunnels"]) > 0:
            # Prefer HTTPS tunnel
            ngrok_url = None
            for tunnel in data["tunnels"]:
                if tunnel.get("public_url", "").startswith("https://"):
                    ngrok_url = tunnel["public_url"]
                    break
            
            # Fallback to first tunnel if no HTTPS found
            if not ngrok_url:
                ngrok_url = data["tunnels"][0]["public_url"]
            
            print(f"Ngrok tunnel started: {ngrok_url}")
            print(f"Local: http://localhost:{port} -> Remote: {ngrok_url}")
            return ngrok_url, process
        else:
            raise Exception("No ngrok tunnels found")
    except Exception as e:
        process.terminate()
        raise Exception(f"Failed to get ngrok URL: {e}")

def save_ngrok_url(ngrok_url):
    """Save ngrok URL to a file for other processes to read"""
    url_file = Path(__file__).parent / "ngrok_url.txt"
    url_file.write_text(ngrok_url)
    print(f"Ngrok URL saved to: {url_file}")

def get_ngrok_url():
    """Get ngrok URL from file if available"""
    url_file = Path(__file__).parent / "ngrok_url.txt"
    if url_file.exists():
        return url_file.read_text().strip()
    return None

def main():
    try:
        # Check if ngrok is already installed
        scripts_dir = Path(__file__).parent
        if platform.system().lower() == "windows":
            ngrok_exe = scripts_dir / "ngrok.exe"
        else:
            ngrok_exe = scripts_dir / "ngrok"
        
        if not ngrok_exe.exists():
            ngrok_path = download_ngrok()
        else:
            ngrok_path = str(ngrok_exe)
            print(f"Ngrok already installed at: {ngrok_path}")
        
        # Configure authtoken
        configure_authtoken(ngrok_path)
        
        # Start ngrok
        ngrok_url, process = start_ngrok(ngrok_path, 8088)
        
        # Save URL
        save_ngrok_url(ngrok_url)
        
        print("\nNgrok is running. Press Ctrl+C to stop.")
        print(f"Use this URL in Render: {ngrok_url}")
        
        # Keep script running
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\nStopping ngrok...")
            process.terminate()
            print("Ngrok stopped.")
            
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
