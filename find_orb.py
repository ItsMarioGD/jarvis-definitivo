with open('ultron_interface/index.html','r',encoding='utf-8') as f:
    txt=f.read()
idx=txt.find('class="core-orb"')
if idx>=0:
    print('found at', idx, 'context:', txt[max(0,idx-80):idx+80])
else:
    print('NOT FOUND')