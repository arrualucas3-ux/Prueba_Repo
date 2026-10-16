"""Read selected UE IoStore package metadata. Does not deserialize properties or execute code."""
from pathlib import Path
import zipfile,json,struct,hashlib,ctypes,functools
ROOT=Path('/workspace/scratch/1a6b54b85a4e');BASE=ROOT/'rv_rea';Z=zipfile.ZipFile(ROOT/'rv_mod_build/game_input/RV_Recursos_Jinx_20261009_164644.zip');M=json.loads(Z.read('manifest.json'));TOC=Z.read('Paks/Ride-Windows.utoc')
U32=lambda b,o:struct.unpack_from('<I',b,o)[0]
U64=lambda b,o:struct.unpack_from('<Q',b,o)[0]
HEADER,N,BLOCKS,BSIZE=U32(TOC,20),U32(TOC,24),U32(TOC,28),U32(TOC,44)
CID=TOC[HEADER:HEADER+12*N];OFFSETS=TOC[HEADER+12*N:HEADER+22*N];CPOS=HEADER+22*N+4*U32(TOC,84)+4*U32(TOC,96)
RANGES={r['block']:r for r in M['ranges']};lib=ctypes.CDLL(str(BASE/'tools/liboodle-data-shared.so'));fun=lib.OodleLZ_Decompress;fun.restype=ctypes.c_longlong;fun.argtypes=[ctypes.c_void_p,ctypes.c_longlong,ctypes.c_void_p,ctypes.c_longlong,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_void_p,ctypes.c_longlong,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_longlong,ctypes.c_int]
@functools.lru_cache(maxsize=900)
def block(i):
 record=RANGES[i];raw=Z.read(record['entry']);assert hashlib.sha256(raw).hexdigest()==record['sha256']
 d=TOC[CPOS+i*12:CPOS+(i+1)*12];off=int.from_bytes(d[:5],'little');c=int.from_bytes(d[5:8],'little');u=int.from_bytes(d[8:11],'little');method=d[11];assert off==record['offset'] and c<=len(raw)
 if method==0:out=raw[:u]
 elif method==1:
  src=ctypes.create_string_buffer(raw[:c]);dest=ctypes.create_string_buffer(u);result=fun(src,c,dest,u,1,0,0,None,0,None,None,None,0,3);assert result==u,(i,result,u);out=dest.raw
 else:raise RuntimeError('Unknown compression '+str(method))
 return out

def chunk(i):
 rec=OFFSETS[10*i:10*i+10];off=int.from_bytes(rec[:5],'big');length=int.from_bytes(rec[5:],'big');first=off//BSIZE;last=(off+length-1)//BSIZE
 payload=b''.join(block(n) for n in range(first,last+1));start=off%BSIZE;assert len(payload)>=start+length
 return payload[start:start+length]

def names(b,p):
 n,total=U32(b,p),U32(b,p+4)
 if n==0:return [],p+4
 assert 0<n<50000
 heads=p+16+n*8;start=heads+2*n;result=[];loc=start
 for i in range(n):
  header=int.from_bytes(b[heads+i*2:heads+i*2+2],'big');wide=bool(header&0x8000);size=header&0x7fff;bytesize=size*(2 if wide else 1);raw=b[loc:loc+bytesize];assert len(raw)==bytesize;result.append(raw.decode('utf-16le' if wide else 'utf8'));loc+=bytesize
 assert loc-start==total,(n,total,loc-start)
 return result,loc

selected={int(k):v for k,v in M['assets'].items()};pkgpaths={U64(CID,12*i):path.replace('../../../Ride/Content/','/Game/').removesuffix('.uasset') for i,path in selected.items() if path.endswith('.uasset')}
# The complete directory index is available even though asset bytes are selected.
dirpos=CPOS+BLOCKS*U32(TOC,32)+U32(TOC,36)*U32(TOC,40)
directory=TOC[dirpos:dirpos+U32(TOC,48)]
def fstring(data,p):
 length=struct.unpack_from('<i',data,p)[0];p+=4
 if length<0:
  raw=data[p:p-length*2];return raw.decode('utf-16le').rstrip('\x00'),p-length*2
 raw=data[p:p+length];return raw.decode('utf8').rstrip('\x00'),p+length
mount,p=fstring(directory,0);dc=U32(directory,p);p+=4;dirs=[struct.unpack_from('<4I',directory,p+i*16) for i in range(dc)];p+=dc*16;fc=U32(directory,p);p+=4;files=[struct.unpack_from('<3I',directory,p+i*12) for i in range(fc)];p+=fc*12;sc=U32(directory,p);p+=4;strings=[]
for i in range(sc):name,p=fstring(directory,p);strings.append(name)
assert p==len(directory)
inventory=[]
def visit(index,parent):
 name,child,sibling,file=dirs[index];folder=parent+(strings[name]+'/' if name!=0xffffffff else '')
 while file!=0xffffffff:
  fname,nextfile,tocindex=files[file];assert tocindex<N;path=folder+strings[fname];inventory.append({'path':path,'toc_index':tocindex,'chunk_type':CID[12*tocindex+11],'package_id':'0x%016x'%U64(CID,12*tocindex)});file=nextfile
 while child!=0xffffffff:visit(child,folder);child=dirs[child][2]
visit(0,mount)
assert len(inventory)==fc
for item in inventory:
 path=item['path']
 if not path.endswith('.uasset'):continue
 if path.startswith('../../../Ride/Content/'):package=path.replace('../../../Ride/Content/','/Game/',1)
 elif path.startswith('../../../Engine/Content/'):package=path.replace('../../../Engine/Content/','/Engine/',1)
 elif '/Plugins/' in path and '/Content/' in path:
  prefix,suffix=path.split('/Content/',1);package='/'+prefix.rsplit('/',1)[-1]+'/'+suffix
 else:continue
 pkgpaths[int(item['package_id'],16)]=package.removesuffix('.uasset')
(BASE/'evidence/game_asset_inventory.json').write_text(json.dumps({'files':inventory,'limitations':['This is a complete directory index inventory from the supplied utoc. Only selected character asset bytes are available.']},indent=2))

headers=[i for i in range(N) if CID[12*i+11]==6];assert len(headers)==1
container=chunk(headers[0]);assert U32(container,0)==0x496f436e;ver=U32(container,4);assert ver>=3
count=U32(container,16);ids=[U64(container,20+i*8) for i in range(count)];storebase=24+8*count;storesize=U32(container,20+8*count);assert storebase+storesize<=len(container);imports={}
for i,pid in enumerate(ids):
 p=storebase+i*16;num=U32(container,p);rel=struct.unpack_from('<i',container,p+4)[0];assert num<50000;start=p+rel;assert not num or start>=storebase and start+num*8<=storebase+storesize
 imports[pid]=[U64(container,start+j*8) for j in range(num)]

global_toc=Z.read('Paks/global.utoc');global_data=Z.read('Paks/global.ucas');gN=U32(global_toc,24);gH=U32(global_toc,20);gids=global_toc[gH:gH+12*gN];goffs=global_toc[gH+12*gN:gH+22*gN];gcp=gH+22*gN+4*U32(global_toc,84)+4*U32(global_toc,96);gblocksize=U32(global_toc,44)
def global_chunk(i):
 rec=goffs[10*i:10*i+10];off=int.from_bytes(rec[:5],'big');length=int.from_bytes(rec[5:],'big');out=[]
 for n in range(off//gblocksize,(off+length-1)//gblocksize+1):
  d=global_toc[gcp+n*12:gcp+(n+1)*12];o=int.from_bytes(d[:5],'little');c=int.from_bytes(d[5:8],'little');u=int.from_bytes(d[8:11],'little');raw=global_data[o:o+c]
  if d[11]==0:out.append(raw[:u])
  else:
   src=ctypes.create_string_buffer(raw);dest=ctypes.create_string_buffer(u);assert fun(src,c,dest,u,1,0,0,None,0,None,None,None,0,3)==u;out.append(dest.raw)
 return b''.join(out)[off%gblocksize:off%gblocksize+length]
script_candidates=[i for i in range(gN) if gids[12*i+11]==5];script_objects={}
for i in script_candidates:
 b=global_chunk(i);ns,p=names(b,0);cnt=U32(b,p);p+=4;assert p+cnt*32<=len(b)
 for j in range(cnt):
  q=p+j*32;idx,num=struct.unpack_from('<II',b,q);global_id,outer,cdo=struct.unpack_from('<QQQ',b,q+8);name=ns[idx&0x3fffffff]+('_'+str(num-1) if num else '')
  script_objects[global_id]={'name':name,'outer':outer,'cdo':cdo}

def script_name(index,seen=None):
 if index not in script_objects:return 'script:0x%016x'%index
 obj=script_objects[index];parent=obj['outer']
 if parent==0xffffffffffffffff:return obj['name']
 return script_name(parent)+'.'+obj['name']

packages=[]
for index,path in sorted(selected.items()):
 if not path.endswith('.uasset'):continue
 b=chunk(index);hasversion,header,nameidx,namenum,flags,cooked,hashoff,importoff,exportoff,bundleoff,depheads,depentries,importnames=struct.unpack_from('<13I',b)
 assert hasversion==0 and header<=len(b)
 ns,end=names(b,60);package_id=U64(CID,12*index);deps=imports.get(package_id,[])
 imps=[U64(b,i) for i in range(importoff,exportoff,8)]
 def mapped_name(i,num=0):return ns[i&0x3fffffff]+('_'+str(num-1) if num else '')
 def object_ref(value):
  if value==0xffffffffffffffff:return None
  t=value>>62;v=value&((1<<62)-1)
  if t==0:return {'kind':'export','index':v}
  if t==1:return {'kind':'script','name':script_name(value),'index':'0x%016x'%value}
  if t==2:
   pi=v>>32;hi=v&0xffffffff;pid=deps[pi] if pi<len(deps) else None;hash=U64(b,hashoff+hi*8) if hashoff+hi*8<importoff else None
   return {'kind':'package','package_id':'0x%016x'%pid if pid is not None else None,'package':pkgpaths.get(pid),'public_export_hash':'0x%016x'%hash if hash is not None else None}
  return {'kind':'unknown','value':str(value)}
 exports=[]
 assert (bundleoff-exportoff)%72==0
 for p in range(exportoff,bundleoff,72):
  serialoff,serialsize,ni,nn,outer,cl,superidx,template,hsh,objectflags,filter=struct.unpack_from('<QQIIQQQQQIB',b,p)
  exports.append({'name':mapped_name(ni,nn),'class':object_ref(cl),'outer':object_ref(outer),'super':object_ref(superidx),'template':object_ref(template),'public_export_hash':'0x%016x'%hsh,'serial_size':serialsize})
 record={'path':pkgpaths[package_id],'package_id':'0x%016x'%package_id,'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b),'unversioned_properties':bool(flags&0x2000),'imports':[object_ref(i) for i in imps],'imported_packages':[{'id':'0x%016x'%pid,'path':pkgpaths.get(pid)} for pid in deps],'exports':exports,'name_count':len(ns)}
 if '/Blueprints/' in path or '/Customization/' in path:record['names']=ns
 packages.append(record)
by_id={r['package_id']:r for r in packages}
for package in packages:
 for ref in package['imports']+[e[key] for e in package['exports'] for key in ['class','super','template']]:
  if ref and ref['kind']=='package' and ref.get('package_id') in by_id:
   match=next((e for e in by_id[ref['package_id']]['exports'] if e['public_export_hash']==ref['public_export_hash']),None)
   if match:ref['export_name']=match['name']
result={'format':'UE5 Zen metadata and IoStore container package dependencies','source_manifest_sha256':hashlib.sha256(Z.read('manifest.json')).hexdigest(),'packages':packages,'coverage':{'asset_metadata_packages':len(packages),'selected_files':len(selected),'complete_directory_index_files':len(inventory),'decompressed_selected_blocks':block.cache_info().currsize,'script_objects':len(script_objects),'native_executable_available':False,'properties_deserialized':False,'blueprint_bytecode_decompiled':False,'runtime_observed':False},'limitations':['Imported package identities are resolved only inside the supplied character resource subset.','Serialized unversioned property values and Blueprint bytecode are not decoded.','Names and declared references do not establish selected runtime assets or executed behavior.']}
(BASE/'evidence/zen_character_metadata.json').write_text(json.dumps(result,indent=2,ensure_ascii=False),encoding='utf8')
print('COVERAGE',result['coverage'],flush=True)
for r in packages:
 if '/Blueprints/' in r['path']:
  print('\nPACKAGE',r['path'],'EXPORTS',len(r['exports']),'DEPS',[d['path'] or d['id'] for d in r['imported_packages']],flush=True)
  for e in r['exports']:
   if e['name'] in ['BP_FirstPersonCharacter_C','Default__BP_FirstPersonCharacter_C'] or e['class'] and 'Function' in e['class'].get('name','') or any(t in e['name'].lower() for t in ['mesh','camera','head','body','rep_','onrep','cosmet','skin','material']):print('EXPORT',e['name'],e['class'], 'SUPER',e['super'],flush=True)
  print('NAME_CANDIDATES',[n for n in r.get('names',[]) if any(t in n.lower() for t in ['mesh','skin','cosmet','material','onrep','custom','playerbody','hat','glasses'])][:70],flush=True)
