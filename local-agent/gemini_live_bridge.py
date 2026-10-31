"""gemini_live_bridge.py - Real-Time Bidirectional Voice & Agent Bridge for Voila AI.

Implements the official Gemini Live API (gemini-3.8-live / gemini-3.8-live-extended-thinking)
over bidirectional WebSockets with:
- Low-latency real-time voice streaming (16kHz PCM audio upstream, 24kHz PCM downstream).
- Real-time barge-in interruption detection (interrupted: true).
- Non-blocking asynchronous tool execution while streaming conversational speech.
- Desktop UI control (desktop_automation via desktop_tools.py) & plasma-free screenshot capture.
- Streaming live user & AI transcription.
- Desktop UI synchronization (notifies plasma border on UDP 19885).
- WebSocket bridge server for the Voila mobile app on ws://127.0.0.1:19890.
"""

import sys
import os
import json
import asyncio
import base64
import time
import socket
import traceback
import subprocess
from typing import Optional

try:
    import websockets
except ImportError:
    websockets = None

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

DEFAULT_PORT = 19890
PLASMA_PORT = 19885
LIVE_MODEL = "gemini-3.8-live"

LIVE_SYSTEM_INSTRUCTION = """You are Voila Live, a real-time voice AI assistant operating on the user's Windows desktop.
Tone & Personality: Raw, direct, conversational, and highly competent. Address the user as 'boss'.
You are having a continuous live spoken conversation with the user. Keep your spoken answers brief, natural, and direct.
When executing actions on the user's computer, speak natural conversational fillers (e.g., 'Checking the server status now...', 'Opening that file for you...', 'Clicking that button on your screen...').
If the user interrupts you while you are speaking, stop immediately and listen to their new instruction."""

def notify_plasma_border(state: str):
    """Notify the amorphous plasma border overlay of state changes via UDP IPC."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(f"STATE:{state}".encode("utf-8"), ("127.0.0.1", PLASMA_PORT))
        s.close()
    except Exception:
        pass

def load_local_api_key() -> str:
    # 1. Check environment variable
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    # 2. Check local-agent connection data
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "connection_data.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("gemini_api_key", "") or data.get("apiKey", "")
        except Exception:
            pass
    return ""

def get_live_tools():
    """Build official NON_BLOCKING function declarations for Gemini 3.8 Live."""
    if not types:
        return []

    decl_terminal = types.FunctionDeclaration(
        name="run_terminal",
        description="Execute a PowerShell or command line instruction on the Windows host",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING", "description": "PowerShell command to execute"}
            },
            "required": ["command"]
        }
    )

    decl_read_file = types.FunctionDeclaration(
        name="read_file",
        description="Read file contents from the local disk",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Absolute file path to read"}
            },
            "required": ["path"]
        }
    )

    decl_desktop = types.FunctionDeclaration(
        name="desktop_automation",
        description="Control Windows desktop UI (click buttons, type text, find elements, switch windows)",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {"type": "STRING", "description": "list_windows | snapshot | find | invoke | click_ref | focus_window | close_window | set_value | type_keys"},
                "selector": {"type": "STRING", "description": "Accessibility name or title to match"},
                "ref": {"type": "STRING", "description": "Element reference from snapshot (e.g. e1)"},
                "value": {"type": "STRING", "description": "Text value to type or set"},
                "window": {"type": "STRING", "description": "Target window title or null for foreground"}
            },
            "required": ["action"]
        }
    )

    decl_screenshot = types.FunctionDeclaration(
        name="take_screenshot",
        description="Capture the desktop screen (automatically excludes any plasma glow border)",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {}
        }
    )

    decl_sentinel_triage = types.FunctionDeclaration(
        name="sentinel_triage",
        description="Query or manage endpoint cybersecurity defense, incident status, process anomaly triage, network isolation, or quarantine vault",
        behavior="NON_BLOCKING",
        parameters={
            "type": "OBJECT",
            "properties": {
                "action": {
                    "type": "STRING",
                    "description": "The security triage action: 'status' (overall posture), 'scan_processes' (anomaly check), 'scan_ports' (listening sockets), 'scan_lan' (ARP/network recon), 'isolate' (emergency network cut), 'lift_isolation' (restore LAN/WAN), 'quarantine_list' (vault contents)"
                }
            },
            "required": ["action"]
        }
    )

    return [types.Tool(function_declarations=[decl_terminal, decl_read_file, decl_desktop, decl_screenshot, decl_sentinel_triage])]

async def execute_local_tool(name: str, args: dict) -> str:
    """Executes a local tool call on the desktop."""
    try:
        if name == "run_terminal":
            cmd = args.get("command", "")
            try:
                from aegis.aegis_core import StaticRules
                allowed, reason = StaticRules.check_payload("run_terminal", cmd, window_title="Live Voice Bridge")
                if not allowed:
                    return f"[BLOCKED BY AEGIS GUARDRAILS]: Command violates safety policy ({reason})"
            except Exception:
                pass
            try:
                from sentinel.process_watchdog import ProcessWatchdog
                is_anom, sev, reasons = ProcessWatchdog.evaluate_command_line(cmd)
                if is_anom and sev in ("CRITICAL", "HIGH"):
                    return f"[BLOCKED BY SENTINEL EDR]: Command blocked due to high-risk behavioral anomaly: {', '.join(reasons)}"
            except Exception:
                pass
            proc = await asyncio.create_subprocess_shell(
                f'powershell -NoProfile -Command "{cmd}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            res = stdout.decode("utf-8", errors="replace")
            err = stderr.decode("utf-8", errors="replace")
            return res if res else err

        elif name == "read_file":
            path = args.get("path", "")
            clean_path = os.path.abspath(path).lower()
            blocked_keys = [".vault_secret", ".sentinel_key", ".bridge_token", "vault_manifest", "\\system32\\config"]
            if any(k in clean_path for k in blocked_keys):
                return "[ACCESS DENIED BY AEGIS]: Prohibited from reading internal security keys or sensitive system stores."
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    return f.read(4000)
            return f"Error: File not found at {path}"

        elif name == "desktop_automation":
            action = args.get("action", "snapshot")
            ref = args.get("ref", "")
            selector = args.get("selector", "")
            value = args.get("value", "")
            window = args.get("window", "")
            script_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "desktop_tools.py")
            cmd_args = [sys.executable, script_path, "--action", action]
            if ref: cmd_args.extend(["--ref", ref])
            if selector: cmd_args.extend(["--selector", selector])
            if value: cmd_args.extend(["--value", value])
            if window: cmd_args.extend(["--window", window])
            proc = await asyncio.create_subprocess_exec(
                *cmd_args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            return stdout.decode("utf-8", errors="replace").strip()

        elif name == "take_screenshot":
            # Exclude plasma border from screenshot: blank it, wait 90ms, capture, restore
            notify_plasma_border("OFF")
            await asyncio.sleep(0.09)
            psCode = """
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$bounds = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bitmap = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$graphics = [System.Drawing.Graphics]::FromImage($bitmap)
$graphics.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$stream = New-Object System.IO.MemoryStream
$bitmap.Save($stream, [System.Drawing.Imaging.ImageFormat]::Jpeg)
$bytes = $stream.ToArray()
$graphics.Dispose()
$bitmap.Dispose()
$stream.Dispose()
Write-Output "Screenshot captured ($($bytes.Length) bytes, plasma-free)"
"""
            proc = await asyncio.create_subprocess_shell(
                f'powershell -NoProfile -Command "{psCode}"',
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await proc.communicate()
            notify_plasma_border("IDLE")
            return stdout.decode("utf-8", errors="replace").strip()

        elif name == "sentinel_triage":
            action = args.get("action", "status")
            try:
                from sentinel.sentinel_core import SentinelCore
                from sentinel.system_defense import SystemDefense

                if action == "status":
                    sc = SentinelCore()
                    status = sc.evaluate_host_posture()
                    return json.dumps({
                        "posture_score": status.get("posture_score", 100.0),
                        "network_isolated": SystemDefense.is_isolated(),
                        "summary": status.get("executive_summary", "Security posture is healthy."),
                        "findings_count": status.get("findings_count", 0),
                    })
                elif action == "scan_processes":
                    from sentinel.process_watchdog import ProcessWatchdog
                    audit = ProcessWatchdog.scan()
                    anomalies = audit.get("anomalies", [])
                    return json.dumps({
                        "suspicious_count": len(anomalies),
                        "message": f"Process scan complete. Found {len(anomalies)} anomalies.",
                        "anomalies": anomalies
                    })
                elif action == "scan_ports":
                    from sentinel.ports_auditor import PortsAuditor
                    audit = PortsAuditor.audit()
                    return json.dumps({
                        "total_listening": audit.get("total_listening", 0),
                        "exposed_dev_servers": audit.get("exposed_dev_servers", []),
                        "exposed_high_risk": audit.get("exposed_high_risk", []),
                        "risk_level": audit.get("risk_level", "HEALTHY")
                    })
                elif action == "scan_lan":
                    from sentinel.lan_guardian import LANGuardian
                    lg = LANGuardian()
                    gw = lg.audit_gateway()
                    return json.dumps({
                        "gateway_status": gw.get("status", "UNKNOWN"),
                        "is_spoofed": gw.get("is_spoofed", False),
                        "gateway_vendor": gw.get("gateway_vendor", "Unknown"),
                        "message": "Gateway ARP verified clean." if not gw.get("is_spoofed") else "WARNING: Gateway ARP spoofing detected!"
                    })
                elif action == "isolate":
                    res = SystemDefense.isolate_network()
                    from sentinel.alert_dispatcher import notify_plasma_hazard
                    notify_plasma_hazard("ISOLATED")
                    return json.dumps({"action": "isolate", "result": res})
                elif action == "lift_isolation":
                    res = SystemDefense.lift_isolation()
                    from sentinel.alert_dispatcher import notify_plasma_hazard
                    notify_plasma_hazard("NORMAL")
                    return json.dumps({"action": "lift_isolation", "result": res})
                elif action == "quarantine_list":
                    from sentinel.quarantine_vault import QuarantineVault
                    manifest = QuarantineVault.list_vault()
                    return json.dumps({
                        "vault_count": len(manifest),
                        "items": manifest
                    })
                else:
                    return f"Unknown sentinel triage action: {action}"
            except Exception as se:
                return f"Sentinel triage execution error: {str(se)}"

    except Exception as e:
        return f"Tool execution error: {str(e)}"
    return "Unknown tool"

class GeminiLiveSessionManager:
    def __init__(self, ws_client):
        self.ws_client = ws_client
        self.active = False
        self.gemini_session = None
        self.api_key = load_local_api_key()
        self.model = LIVE_MODEL
        self.binary_mode = False

    async def broadcast_to_client(self, payload: dict):
        try:
            await self.ws_client.send(json.dumps(payload))
        except Exception:
            pass

    async def start(self, user_api_key: Optional[str] = None, model: Optional[str] = None, binary_mode: bool = False):
        if user_api_key:
            self.api_key = user_api_key
        if model:
            self.model = model
        if binary_mode:
            self.binary_mode = True

        if not self.api_key:
            await self.broadcast_to_client({
                "type": "error",
                "message": "Gemini API Key not found. Please provide an API key to start Live Mode."
            })
            return

        if not genai or not types:
            await self.broadcast_to_client({
                "type": "error",
                "message": "google-genai SDK not installed."
            })
            return

        self.active = True
        notify_plasma_border("THINKING")
        await self.broadcast_to_client({"type": "live_state", "state": "CONNECTING"})

        try:
            client = genai.Client(api_key=self.api_key)
            tools = get_live_tools()

            config_args = {
                "response_modalities": [types.Modality.AUDIO],
                "system_instruction": types.Content(
                    parts=[types.Part(text=LIVE_SYSTEM_INSTRUCTION)]
                ),
                "input_audio_transcription": types.AudioTranscriptionConfig(),
                "output_audio_transcription": types.AudioTranscriptionConfig(),
                "tools": tools,
            }

            # Extended thinking configuration for high-reasoning live model
            if self.model == "gemini-3.8-live-extended-thinking":
                config_args["thinking_config"] = types.ThinkingConfig(thinking_level="low")

            config = types.LiveConnectConfig(**config_args)

            async with client.aio.live.connect(model=self.model, config=config) as session:
                self.gemini_session = session
                await self.broadcast_to_client({"type": "live_state", "state": "LISTENING"})
                notify_plasma_border("IDLE")

                # Receive loop from Gemini Live
                async for response in session.receive():
                    if not self.active:
                        break

                    # Monitor interaction status (Gemini 3.8 async reasoning)
                    interaction_status = getattr(response, "interaction_status", None)
                    if interaction_status == "IDLE":
                        notify_plasma_border("IDLE")
                        await self.broadcast_to_client({"type": "live_state", "state": "LISTENING"})

                    content = response.server_content
                    if content:
                        # 1. Handle Barge-In Interruption
                        if getattr(content, "interrupted", False):
                            notify_plasma_border("IDLE")
                            await self.broadcast_to_client({
                                "type": "interrupted",
                                "message": "User interrupted AI speech."
                            })

                        # 2. User live transcript
                        if getattr(content, "input_transcription", None):
                            txt = content.input_transcription.text
                            if txt:
                                await self.broadcast_to_client({
                                    "type": "user_transcript",
                                    "text": txt,
                                    "is_final": True
                                })

                        # 3. Model live transcript
                        if getattr(content, "output_transcription", None):
                            txt = content.output_transcription.text
                            if txt:
                                await self.broadcast_to_client({
                                    "type": "ai_transcript",
                                    "text": txt,
                                    "is_final": True
                                })

                        # 4. Model audio stream parts (24kHz PCM)
                        if getattr(content, "model_turn", None):
                            notify_plasma_border("RUNNING")
                            await self.broadcast_to_client({"type": "live_state", "state": "SPEAKING"})
                            for part in content.model_turn.parts:
                                if getattr(part, "inline_data", None):
                                    raw_pcm = part.inline_data.data
                                    if self.binary_mode:
                                        # Fast binary transmission: 0x01 prefix + raw PCM bytes (33.3% bandwidth saved)
                                        try:
                                            await self.ws_client.send(b"\x01" + raw_pcm)
                                        except Exception:
                                            pass
                                    else:
                                        audio_b64 = base64.b64encode(raw_pcm).decode("ascii")
                                        await self.broadcast_to_client({
                                            "type": "ai_audio",
                                            "data": audio_b64
                                        })

                        # 5. Turn completion
                        if getattr(content, "turn_complete", False):
                            notify_plasma_border("IDLE")
                            await self.broadcast_to_client({"type": "live_state", "state": "LISTENING"})

                    # 6. Handle Live Non-Blocking Tool Calls
                    tool_call = getattr(response, "tool_call", None)
                    if tool_call:
                        notify_plasma_border("BASH")
                        await self.broadcast_to_client({"type": "live_state", "state": "TOOL_EXEC"})
                        for call in tool_call.function_calls:
                            fn_name = call.name
                            fn_args = dict(call.args) if call.args else {}
                            await self.broadcast_to_client({
                                "type": "tool_action",
                                "tool": fn_name,
                                "args": fn_args,
                                "status": "started"
                            })
                            res = await execute_local_tool(fn_name, fn_args)
                            await self.broadcast_to_client({
                                "type": "tool_action",
                                "tool": fn_name,
                                "output": res[:300],
                                "status": "finished"
                            })
                            # Send tool response back to Gemini session
                            try:
                                await session.send_tool_response(
                                    function_responses=[
                                        types.FunctionResponse(
                                            name=fn_name,
                                            id=call.id,
                                            response={"output": res}
                                        )
                                    ]
                                )
                            except Exception as te:
                                print(f"Error sending tool response: {te}")

        except Exception as e:
            notify_plasma_border("IDLE")
            traceback.print_exc()
            await self.broadcast_to_client({
                "type": "error",
                "message": f"Gemini Live error: {str(e)}"
            })
        finally:
            self.active = False
            notify_plasma_border("IDLE")
            await self.broadcast_to_client({"type": "live_state", "state": "DISCONNECTED"})

    async def send_audio_chunk(self, pcm_bytes: bytes):
        if self.gemini_session and self.active:
            try:
                await self.gemini_session.send_realtime_input(
                    audio=types.Blob(data=pcm_bytes, mime_type="audio/pcm;rate=16000")
                )
            except Exception as e:
                print(f"Error streaming audio to Gemini: {e}")

    async def send_text_chunk(self, text: str):
        if self.gemini_session and self.active:
            try:
                await self.gemini_session.send_realtime_input(text=text)
            except Exception as e:
                print(f"Error sending text to Gemini: {e}")

    def stop(self):
        self.active = False
        notify_plasma_border("IDLE")

async def handle_client(websocket, path=None):
    session_mgr = GeminiLiveSessionManager(websocket)
    try:
        async for raw_msg in websocket:
            # Direct binary frame handling: 0x01 prefix or raw PCM bytes
            if isinstance(raw_msg, bytes):
                session_mgr.binary_mode = True
                if len(raw_msg) > 1 and raw_msg[0] == 0x01:
                    await session_mgr.send_audio_chunk(raw_msg[1:])
                elif len(raw_msg) > 0:
                    await session_mgr.send_audio_chunk(raw_msg)
                continue

            try:
                data = json.loads(raw_msg)
            except Exception:
                continue

            msg_type = data.get("type", "")
            if msg_type == "start":
                api_key = data.get("apiKey") or load_local_api_key()
                model = data.get("model", LIVE_MODEL)
                binary_mode = data.get("binary_mode", False)
                asyncio.create_task(session_mgr.start(api_key, model, binary_mode=binary_mode))
            elif msg_type == "audio":
                b64_data = data.get("data", "")
                if b64_data:
                    pcm_bytes = base64.b64decode(b64_data)
                    await session_mgr.send_audio_chunk(pcm_bytes)
            elif msg_type == "text":
                text = data.get("text", "")
                if text:
                    await session_mgr.send_text_chunk(text)
            elif msg_type == "interrupt":
                notify_plasma_border("IDLE")
                session_mgr.stop()
                await session_mgr.broadcast_to_client({"type": "interrupted"})
            elif msg_type == "stop":
                session_mgr.stop()
                break
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        session_mgr.stop()

async def main():
    if not websockets:
        print("websockets library not installed.")
        return
    port = int(os.environ.get("VOILA_LIVE_PORT", DEFAULT_PORT))
    print(f"Starting Voila Gemini Live Bridge on ws://127.0.0.1:{port}...")
    # Enforce strict CSWSH defense: only non-browser clients (None) or local web origins permitted
    trusted_origins = [None, "http://127.0.0.1", "http://localhost", f"http://127.0.0.1:{port}", f"http://localhost:{port}"]
    async with websockets.serve(handle_client, "127.0.0.1", port, origins=trusted_origins):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Live bridge stopped.")
