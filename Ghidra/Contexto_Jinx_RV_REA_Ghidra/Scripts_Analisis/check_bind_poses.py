from contextlib import redirect_stdout
import io,runpy,json,math,struct
from pathlib import Path
import numpy as np
from scipy.spatial.transform import Rotation
ROOT=Path('/workspace/scratch/1a6b54b85a4e')
with redirect_stdout(io.StringIO()):env=runpy.run_path(str(ROOT/'rv_rea/inspect_zen_metadata.py'))
chunk=env['chunk'];names=env['names'];selected=env['selected'];results=[]
expected=json.load(open(ROOT/'rv_mod_build/deliverables/Preparar_Jinx_RV_Unreal56/Source/import_manifest.json'))['bones'];eby={x['name']:x for x in expected}
for index,path in selected.items():
 if path.rsplit('/',1)[-1] not in ['SK_BoxyRider_01.uasset','SK_BoxyRider_02.uasset','SK_BoxyRider_03.uasset','SK_BoxyRider_FPP_Arms_03.uasset']:continue
 b=chunk(index);ns,_=names(b,60);candidates=[]
 for p in range(len(b)-4):
  count=struct.unpack_from('<I',b,p)[0]
  if count not in (76,78):continue
  end=p+4+count*12
  if end+4+count*80>len(b) or struct.unpack_from('<I',b,end)[0]!=count:continue
  info=[];valid=True
  for i in range(count):
   ni,nn,parent=struct.unpack_from('<IIi',b,p+4+i*12)
   if ni>=len(ns) or nn>1000 or not (-1<=parent<i) or i and parent<0:valid=False;break
   name=ns[ni]+('_'+str(nn-1) if nn else '');info.append({'name':name,'parent':parent})
  if not valid or info[0]['name']!='root':continue
  local=[]
  for i in range(count):
   v=struct.unpack_from('<10d',b,end+4+i*80)
   if abs(sum(q*q for q in v[:4])-1)>.001 or any(abs(s-1)>.001 for s in v[7:]):valid=False;break
   local.append(v)
  if valid:candidates.append((p,info,local))
 assert len(candidates)==1,(path,len(candidates));offset,info,local=candidates[0];errors=[];qerrs=[];matches=0
 for i,(bone,v) in enumerate(zip(info,local)):
  name=bone['name']
  if name not in eby:continue
  exp=eby[name];parent=info[bone['parent']]['name'] if bone['parent']>=0 else None;assert parent==exp['parent'];position=math.sqrt(sum((a-e)**2 for a,e in zip(v[4:7],exp['translation_cm'])));dot=abs(sum(a*e for a,e in zip(v[:4],exp['rotation_xyzw'])));angle=math.degrees(2*math.acos(min(1,dot)));errors.append(position);qerrs.append(angle);matches+=1
 results.append({'path':path,'native_reference_skeleton_offset':offset,'mesh_bones':len(info),'matched_jinx_bones':matches,'extra_native_mesh_bones':[b['name'] for b in info if b['name'] not in eby],'max_translation_error_cm':max(errors),'max_rotation_error_degrees':max(qerrs),'within_tolerance':max(errors)<.05 and max(qerrs)<.2})
report={'results':results,'limitations':['This compares native bind pose data with the prepared Jinx skeleton. It does not test animation, visual proportions or runtime integration.']};(ROOT/'rv_rea/evidence/bind_pose_comparison.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
