import json, urllib.request

req = urllib.request.Request("http://127.0.0.1:19882/command", 
    data=json.dumps({"command": "echo 'hello'"}).encode('utf-8'),
    headers={"Content-Type": "application/json"})
try:
    res = urllib.request.urlopen(req)
    print(res.read().decode('utf-8'))
except Exception as e:
    print(e)
