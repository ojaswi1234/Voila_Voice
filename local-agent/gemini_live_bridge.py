"""gemini_live_bridge.py - Real-Time Bidirectional Voice & Agent Bridge for Voila AI.

Implements the official Gemini Live API (gemini-3.8-live / gemini-3.8-live-extended-thinking)
over bidirectional WebSockets with:
- Low-latency real-time voice streaming (16kHz PCM audio upstream, 24kHz PCM downstream).
- Real-time barge-in interruption detection (interrupted: true).
- Non-blocking asynchronous tool execution while streaming conversational speech.
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
When executing actions on the user's computer, speak natural conversational fillers (e.g., 'Checking the server status now...', 'Opening that file for you...').
If the user interrupts you while you are speaking, stop immediately and listen to their new instruction."""

def notify_plasma_border(state: str):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.sendto(f"STATE:{state}".encode("utf-8"), ("127.0.0.1", PLASMA_PORT))
        s.close()
    except Exception:
        pass

def load_local_api_key() -> str:
    # Check env var
    key = os.environ.get("GEMINI_API_KEY", "")
    if key:
        return key
    # Check local-agent connection data
    cfg_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "connection_data.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("gemini_api_key", "") or data.get("apiKey", "")
        except Exception:
            pass
    return ""

# Tool definitions with behavior="NON_BLOCKING"
LIVE_TOOL_DECLARATIONS = [
    {
        "name": "run_terminal",
        "description": "Execute a PowerShell or command line instruction on the Windows host",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "command": {"type": "STRING", "description": "PowerShell command to execute"}
            },
            "required": ["command"]
        },
        "behavior": "NON_BLOCKING"
    },
    {
        "name": "read_file",
        "description": "Read file contents from the local disk",
        "parameters": {
            "type": "OBJECT",
            "properties": {
                "path": {"type": "STRING", "description": "Absolute file path to read"}
            },
            "required": ["path"]
        },
        "behavior": "NON_BLOCKING"
    }
]

async def execute_local_tool(name: str, args: dict) -> str:
    """Executes a local tool call on the desktop."""
    try:
        if name == "run_terminal":
            cmd = args.get("command", "")
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
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8", errors="replace") as f:
                    return f.read(4000)
            return f"Error: File not found at {path}"
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

    async def broadcast_to_client(self, payload: dict):
        try:
            await self.ws_client.send(json.dumps(payload))
        except Exception:
            pass

    async def start(self, user_api_key: Optional[str] = None, model: Optional[str] = None):
        if user_api_key:
            self.api_key = user_api_key
        if model:
            self.model = model

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
            config = types.LiveConnectConfig(
                response_modalities=[types.Modality.AUDIO],
                system_instruction=types.Content(
                    parts=[types.Part(text=LIVE_SYSTEM_INSTRUCTION)]
                ),
                input_audio_transcription=types.AudioTranscriptionConfig(),
                output_audio_transcription=types.AudioTranscriptionConfig(),
            )

            async with client.aio.live.connect(model=self.model, config=config) as session:
                self.gemini_session = session
                await self.broadcast_to_client({"type": "live_state", "state": "LISTENING"})
                notify_plasma_border("IDLE")

                # Receive loop from Gemini Live
                async for response in session.receive():
                    if not self.active:
                        break

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
                                    audio_b64 = base64.b64encode(part.inline_data.data).decode("ascii")
                                    await self.broadcast_to_client({
                                        "type": "ai_audio",
                                        "data": audio_b64
                                    })

                    # 5. Handle Live Tool Calls
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

async def handle_client(websocket, path):
    session_mgr = GeminiLiveSessionManager(websocket)
    try:
        async for raw_msg in websocket:
            try:
                data = json.loads(raw_msg)
            except Exception:
                continue

            msg_type = data.get("type", "")
            if msg_type == "start":
                api_key = data.get("apiKey") or load_local_api_key()
                model = data.get("model", LIVE_MODEL)
                asyncio.create_task(session_mgr.start(api_key, model))
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
    async with websockets.serve(handle_client, "127.0.0.1", port):
        await asyncio.Future()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Live bridge stopped.")
