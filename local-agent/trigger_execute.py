import urllib.request, json, hashlib

def hash_phrase(phrase, device_id):
    salt = f"{device_id}_voila_salt_v2".encode()
    return hashlib.pbkdf2_hmac('sha256', phrase.encode(), salt, 10000, 32).hex()

secret = hash_phrase("fuckoff", "desktop-ac4a09e8")

req = urllib.request.Request(
    'http://127.0.0.1:8088/execute',
    data=json.dumps({"command": "Test the desktop automation"}).encode(),
    headers={'X-Exec-Secret': secret, 'Content-Type': 'application/json'}
)
print("Sending request to Voila Backend...")
try:
    res = urllib.request.urlopen(req)
    print(res.read().decode())
except Exception as e:
    print(f"Error: {e}")
    if hasattr(e, 'read'):
        print(e.read().decode())
