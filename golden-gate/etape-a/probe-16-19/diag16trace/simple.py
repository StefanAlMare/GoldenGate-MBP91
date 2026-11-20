from parse import *
out=[]
for f in root.glob('*/*.tracev3'):
 for t,b in chunks(f.read_bytes()):
  if t!=0x600d: continue
  for st,v in chunks(expand(b)):
   if st!=0x6004:continue
   timestamp=u('Q',v,16)[0]/1e9
   n,ns,nm=u('III',v,72)
   p=v[84:84+ns].rstrip(b'\0').decode(errors='replace')
   m=v[84+ns:84+ns+nm].rstrip(b'\0').decode(errors='replace')
   out.append((timestamp,p,m))
with (root/'simple.tsv').open('w') as o:
 for a,b,c in sorted(out):print(f'{a:.6f}',b,c,sep='\t',file=o)
