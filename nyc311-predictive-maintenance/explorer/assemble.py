"""Build the explorer outputs from build/graph_data.json.

Usage: python explorer/assemble.py build/graph_data.json docs/graph_explorer.html
  - docs/graph_explorer.html : one offline file (data + bundled JS inlined)
  - docs/gx_data.js          : the same data as a script, loaded by the story page (index.html)
"""
import json,sys,os
HERE=os.path.dirname(os.path.abspath(__file__))
d=json.load(open(sys.argv[1]))
t=open(os.path.join(HERE,'template.html')).read()
js=open(os.path.join(HERE,'bundle.js')).read().replace('</script','<\\/script')
out=t.replace('__META__',d['meta']).replace('__DATA__',json.dumps(d['data'],separators=(',',':'))).replace('__JS__',js)
open(sys.argv[2],'w').write(out);print(len(out))
open(os.path.join(os.path.dirname(sys.argv[2]),'gx_data.js'),'w').write('window.GX_DATA='+json.dumps(d['data'],separators=(',',':'))+';')
