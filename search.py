import urllib.request, urllib.parse
from bs4 import BeautifulSoup
import sys

q = urllib.parse.quote('AI prompt marketplace for presentations design')
url = f'https://html.duckduckgo.com/html/?q={q}'
req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
html = urllib.request.urlopen(req).read().decode('utf-8')
soup = BeautifulSoup(html, 'html.parser')
for a in soup.find_all('a', class_='result__snippet'):
    print(a.text)
