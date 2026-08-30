import requests
r = requests.get('http://127.0.0.1:8766/', timeout=8)
src = r.text
print('class core-orb count:', src.count('class="core-orb"'))
print('id coreOrb count:', src.count('id="coreOrb"'))