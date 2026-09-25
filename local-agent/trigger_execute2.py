import urllib.request, json, hashlib

def hash_phrase(phrase, device_id):
    salt = f"{device_id}_voila_salt_v2".encode()
    return hashlib.pbkdf2_hmac('sha256', phrase.encode(), salt, 10000, 32).hex()

secret = hash_phrase("fuckoff", "desktop-ac4a09e8")

prompt = """I want to check if you can control my computer screen like a person using the mouse.

Please do this step by step, slowly so I can watch the mouse move:

1. Open Notepad for me if it is not already open.
2. Move the mouse smoothly to the writing area in Notepad.
3. Type this message: Hello, this is a test.
4. Then move the mouse to the File menu at the top and click it.
5. After that, open Calculator and click the number 7, then the number 8, so I can see the mouse move between buttons.

now execute the task using desktop tools"""

req = urllib.request.Request(
    'http://127.0.0.1:8088/execute',
    data=json.dumps({"command": prompt}).encode(),
    headers={'X-Exec-Secret': secret, 'Content-Type': 'application/json'}
)
print("Sending long prompt request to Voila Backend...")
try:
    res = urllib.request.urlopen(req)
    print(res.read().decode())
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'read'):
        print(e.read().decode())
