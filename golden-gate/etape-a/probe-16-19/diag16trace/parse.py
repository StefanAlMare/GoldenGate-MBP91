from pathlib import Path
import ctypes,struct,collections,zlib,sys,re
root=Path(__file__).parent
lib=ctypes.CDLL('/usr/lib/libcompression.dylib')
decompress=lib.compression_decode_buffer
decompress.argtypes=(ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_size_t,ctypes.c_void_p,ctypes.c_int)
decompress.restype=ctypes.c_size_t
u=lambda fmt,b,pos=0:struct.unpack_from('<'+fmt,b,pos)
def chunks(data):
    o=0
    while o+16<=len(data):
        t,sub,size=u('IIQ',data,o)
        if not size or o+16+size>len(data):break
        yield t,data[o+16:o+16+size]
        o+=(size+16+7)&~7
def parsecatalog(b):
    start,end,n,*_=u('8H',b)
    uuids=[b[i:i+16].hex().upper() for i in range(24,24+start,16)]
    o=24+end
    out={}
    for _ in range(n):
        idx,un,mid,dsc,k,k2,pid,euid,pers,nu,un3=u('4HQ6I',b,o)
        out[(k,k2)]=(pid,uuids[mid],uuids[dsc] if dsc<len(uuids) else '')
        o+=40+16*nu
        ns,_=u('II',b,o)
        o+=8+((6*ns+7)&~7)
    return out
def expand(b):
    if b[:4]==b'bv4-':
        return b[8:8+u('I',b,4)[0]]
    alg=0x101 if b[:4]==b'bv41' else 0x702
    comp=b[12:12+u('I',b,8)[0]] if alg==0x101 else b
    out=ctypes.create_string_buffer(4<<20)
    n=decompress(out, len(out), comp,len(comp),None,alg)
    if not n:raise Exception(f'decompression failed {b[:12].hex()}')
    return out.raw[:n]
def run():
    result=[]; mapping={}; hist=collections.Counter()
    for f in root.glob('*/*.tracev3'):
        data=f.read_bytes(); print(f,len(data),hex(zlib.crc32(data)))
        for t,b in chunks(data):
            if t==0x600b:
                mp=parsecatalog(b)
                for row in mp.values():mapping[row[0]]=row[1:]
            if t!=0x600d:continue
            inner=expand(b)
            for subt,body in chunks(inner):
                hist[subt]+=1
                if subt!=0x6001:continue
                key=u('QI',body);pid,uu,dsc=mp.get(key,(-1,'',''))
                pub=u('H',body,16)[0];bt=u('Q',body,24)[0]; pos=32;end=16+pub
                while pos+24<=end:
                    typ,lvl,flags,fmt,tid,dl,du,size=u('BBHIQIHH',body,pos)
                    if not typ or pos+24+size>end:break
                    block=body[pos+24:pos+24+size]
                    ss=[s.decode('ascii') for s in re.findall(rb'[ -~]{4,}',block)]
                    ts=(bt+dl+(du<<32))/1e9
                    result.append((ts,pid,typ,lvl,flags,fmt,ss,block.hex()))
                    pos+=24+size; pad=(-size)%8
                    for j in range(pad):
                        if pos<len(body) and not body[pos]:pos+=1
                        else:break
    print('total',len(result),'pids',len(mapping),'hist',hist)
    with (root/'decoded.tsv').open('w') as o:
        for ts,pid,typ,lvl,flags,fmt,ss,b in sorted(result):
            print(f'{ts:.6f}',pid,typ,lvl,f'{flags:x}',f'{fmt:x}',' | '.join(ss),b,sep='\t',file=o)
    with (root/'pid.tsv').open('w') as o:
        for pid,item in sorted(mapping.items()):print(pid,*item,sep='\t',file=o)
if __name__=='__main__':run()
