"""Direct Ghidra CLI with REA's unmodified authenticated read-only bridge.

Uses scoped explicit seeds, not the default whole-program analysis profile.
The application being inspected is never launched.
"""
from pathlib import Path
import hashlib, json, os, secrets, socket, subprocess, time, traceback, uuid

ROOT=Path(__file__).resolve().parent
SESSION=ROOT/'direct_native_session'
REQ=SESSION/'requests'; RES=SESSION/'responses'
for name in ('requests','responses','home','tmp','project'):(SESSION/name).mkdir(parents=True,exist_ok=True)
config=json.loads((ROOT/'tools/installed_tools.json').read_text())
ghidra=Path(config['ghidra']['ghidra_root']);jdk=Path(config['jdk']['jdk_root'])
java=str(jdk/'bin/java');package=ROOT/'tools/rea/node_modules/rea-agents'
bridge=package/'bridge/ghidra';target=ROOT/'native_input/Ride-Win64-Shipping.exe'
token=secrets.token_hex(32);run_id=str(uuid.uuid4())
profile={'provider':'Ghidra 12.1.4','bridge':'REA 6.4.0 packaged Java bridge',
         'mode':'PE import, explicit function seeds, no default whole-program auto-analysis',
         'seeds_sha256':hashlib.sha256((SESSION/'seeds.tsv').read_bytes()).hexdigest(),
         'target_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
profile_digest=hashlib.sha256(json.dumps(profile,sort_keys=True).encode()).hexdigest()
(ROOT/'evidence/native_analysis_profile.json').write_text(json.dumps(profile,indent=2))
descriptor=SESSION/'session_private.json'
descriptor.write_text(json.dumps({'transport':'authenticated-loopback-tcp','endpoint_path':str(SESSION/'endpoint.json'),
    'token':token,'run_id':run_id,'target_sha256':profile['target_sha256'],'provider_version':'12.1.4','profile_digest':profile_digest}))
descriptor.chmod(0o600)
props=['-Duser.home='+str(SESSION/'home'),'-Djava.io.tmpdir='+str(SESSION/'tmp')]
vmargs=subprocess.check_output([java,*props,'-cp',str(ghidra/'support/LaunchSupport.jar'),'LaunchSupport',str(ghidra),'-vmargs'],text=True).splitlines()
args=[java,*vmargs,'-Xmx5G','-XX:ParallelGCThreads=2','-XX:CICompilerCount=2','-Djava.awt.headless=true',*props,
      '-cp',str(ghidra/'Ghidra/Framework/Utility/lib/Utility.jar'),'ghidra.Ghidra','ghidra.app.util.headless.AnalyzeHeadless',
      str(SESSION/'project'),'RV-character-scope','-import',str(target),'-noanalysis','-readOnly','-deleteProject',
      '-log',str(SESSION/'ghidra.log'),'-scriptlog',str(SESSION/'scripts.log'),'-scriptPath',str(ROOT)+';'+str(bridge),
      '-postScript',str(bridge/'ReaGhidraApplySeeds.java'),str(SESSION/'seeds.tsv'),
      '-postScript',str(ROOT/'RVPrepareFunctions.java'),str(ROOT/'evidence/native_seed_inventory.json'),
      '-postScript',str(bridge/'ReaGhidraBridge.java'),str(descriptor)]
(SESSION/'launch_arguments.json').write_text(json.dumps(args,indent=2))
log=(SESSION/'process.log').open('wb')
proc=subprocess.Popen(args,stdout=log,stderr=subprocess.STDOUT)
connection=None;stream=None
try:
 print('DIRECT_GHIDRA_STARTED',proc.pid,flush=True)
 deadline=time.monotonic()+600;last=0
 while not (SESSION/'endpoint.json').exists():
  if proc.poll() is not None:raise RuntimeError('Ghidra exited '+str(proc.returncode))
  if time.monotonic()>deadline:raise TimeoutError('Ghidra import deadline')
  if time.monotonic()-last>25:print('DIRECT_GHIDRA_IMPORTING',flush=True);last=time.monotonic()
  time.sleep(.5)
 endpoint=json.loads((SESSION/'endpoint.json').read_text());connection=socket.create_connection((endpoint['host'],endpoint['port']),timeout=300);stream=connection.makefile('rwb')
 print('DIRECT_REA_BRIDGE_READY',flush=True)
 counter=0
 while True:
  files=sorted(REQ.glob('*.json'))
  if not files:
   if proc.poll() is not None:raise RuntimeError('Ghidra exited')
   time.sleep(.5);continue
  source=files[0];request=json.loads(source.read_text());source.rename(source.with_suffix('.running'));counter+=1
  method=request['name'];print('DIRECT_REQUEST',source.name,method,flush=True)
  stream.write((json.dumps({'id':counter,'token':token,'method':method,'params':request.get('arguments',{})})+'\n').encode());stream.flush()
  response=json.loads(stream.readline())
  (RES/source.name).write_text(json.dumps({'analysis_profile':profile,'bridge_result':response},indent=2))
  source.with_suffix('.running').rename(source.with_suffix('.done'))
  print('DIRECT_RESULT',source.name,'bytes',(RES/source.name).stat().st_size,flush=True)
  if method=='shutdown':break
except Exception:
 traceback.print_exc()
finally:
 if stream:stream.close()
 if connection:connection.close()
 try:proc.wait(timeout=15)
 except subprocess.TimeoutExpired:proc.terminate();proc.wait(timeout=10)
 log.close();descriptor.unlink(missing_ok=True)
