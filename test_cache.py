import sys
sys.path.append('local-agent')
from document_tools import get_image_for_slide
import document_tools

document_tools.auto_images = True

slide = {"title": "Cache Test", "content": "Docker landscape"}
url1 = get_image_for_slide(slide)
print(f'Call 1: {url1}')
url2 = get_image_for_slide(slide)
print(f'Call 2: {url2}')
