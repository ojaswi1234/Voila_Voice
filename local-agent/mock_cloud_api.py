import json, sys
from http.server import BaseHTTPRequestHandler, HTTPServer

class MockAPI(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers['Content-Length'])
        body = self.rfile.read(content_length)
        data = json.loads(body.decode('utf-8'))
        
        # Append the request to a log file so we can analyze what Voila sends
        with open("mock_requests_log.jsonl", "a") as f:
            f.write(json.dumps(data) + "\n")
            
        print(f"\n--- RECEIVED REQUEST: {data.get('model')} ---")
        msgs = data.get('messages', [])
        print(f"Messages count: {len(msgs)}")
        if msgs:
            print(f"Latest message: {msgs[-1]['content'][:100]}...")
        
        # If this is the FIRST request, send a tool call for snapshot
        if len(msgs) <= 2:
            print("-> Returning 'snapshot' tool call")
            response = {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": 1234567890,
                "model": data.get("model", "mock"),
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_mock1",
                            "type": "function",
                            "function": {
                                "name": "desktop_automation",
                                "arguments": json.dumps({"action": "snapshot"})
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20}
            }
        # If it's the second request (tool result), send a move_cursor
        elif len(msgs) == 4:
            print("-> Returning 'move_cursor' tool call")
            
            # Find a ref from the snapshot
            ref_to_use = "e1"
            try:
                res = json.loads(msgs[-1]["content"])
                if res.get("elements"):
                    ref_to_use = res["elements"][-1]["ref"]
            except:
                pass
                
            response = {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": 1234567890,
                "model": data.get("model", "mock"),
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [{
                            "id": "call_mock2",
                            "type": "function",
                            "function": {
                                "name": "desktop_automation",
                                "arguments": json.dumps({"action": "move_cursor", "ref": ref_to_use})
                            }
                        }]
                    },
                    "finish_reason": "tool_calls"
                }],
                "usage": {"prompt_tokens": 20, "completion_tokens": 10, "total_tokens": 30}
            }
        else:
            print("-> Returning final answer")
            response = {
                "id": "chatcmpl-mock",
                "object": "chat.completion",
                "created": 1234567890,
                "model": data.get("model", "mock"),
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "I have successfully analyzed the desktop and moved the cursor as requested."
                    },
                    "finish_reason": "stop"
                }],
                "usage": {"prompt_tokens": 30, "completion_tokens": 15, "total_tokens": 45}
            }
            
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(response).encode('utf-8'))

def run():
    print("Starting Mock Cloud API on http://127.0.0.1:8080")
    server = HTTPServer(('127.0.0.1', 8080), MockAPI)
    server.serve_forever()

if __name__ == '__main__':
    run()
