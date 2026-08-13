import re

with open('main.go', 'r', encoding='utf-8') as f:
    backend_code = f.read()

backend_code = backend_code.replace('return "TASK_QUEUED", nil', 'return {"type":"queued","message":"Task queued"}, nil')

with open('main.go', 'w', encoding='utf-8') as f:
    f.write(backend_code)
