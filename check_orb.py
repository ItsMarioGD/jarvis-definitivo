import requests
r = requests.get('http://127.0.0.1:8766/', timeout=8)
src = r.text
print('coreOrb:', 'id="coreOrb"' in src)
print('fixed:', 'position: fixed' in src)
print('topbar orb removed:', 'core-orb' not in src)