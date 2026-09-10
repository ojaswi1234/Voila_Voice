import sys
sys.path.append('local-agent')
import document_tools
import os
import shutil

cache_dir = os.path.join('local-agent', 'image_cache')
if os.path.exists(cache_dir): shutil.rmtree(cache_dir)
os.makedirs(cache_dir)

kwargs = {
    'path': 'test_pres.pptx',
    'title': 'Test Presentation',
    'slides': [{'title': 'Docker Test', 'content': 'Test Cache', 'type': 'image'}],
    'auto_images': True
}

print('=== First Call ===')
print(document_tools.create_ppt(kwargs))

print('\n=== Second Call ===')
print(document_tools.create_ppt(kwargs))

print('\n=== Cache Contents ===')
print(os.listdir(cache_dir))
