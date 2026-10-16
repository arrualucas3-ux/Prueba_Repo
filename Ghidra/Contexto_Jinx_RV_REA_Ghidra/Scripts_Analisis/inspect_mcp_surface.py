import json,subprocess,os,selectors,time
from pathlib import Path
ROOT=Path('/workspace/scratch/1a6b54b85a4e/rv_rea');config=json.load(open(ROOT/'tools/installed_tools.json'));env=os.environ.copy();env['GHIDRA_INSTALL_DIR']=config['ghidra']['ghidra_root'];env['JAVA_HOME']=config['jdk']['jdk_root']
log=(ROOT/'evidence/mcp_connection.log').open('wb');p=subprocess.Popen(['node',str(ROOT/'tools/rea/node_modules/rea-agents/scripts/rea.mjs'),'mcp'],env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=log,bufsize=0);selector=selectors.DefaultSelector();selector.register(p.stdout,selectors.EVENT_READ);buffer=b''
def write(obj):p.stdin.write((json.dumps(obj)+'\n').encode());p.stdin.flush()
def reply(id):
 global buffer
 until=time.monotonic()+25
 while time.monotonic()<until:
  while b'\n' in buffer:
   line,buffer=buffer.split(b'\n',1)
   if not line.strip():continue
   value=json.loads(line)
   if value.get('id')==id:return value
  if not selector.select(max(0,until-time.monotonic())):break
  data=os.read(p.stdout.fileno(),65536)
  if not data:break
  buffer+=data
 raise RuntimeError('MCP timeout')
try:
 write({'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','capabilities':{},'clientInfo':{'name':'rv-character-analysis','version':'1.0'}}});init=reply(1);print('INIT',init.get('result',{}).get('serverInfo'),flush=True);write({'jsonrpc':'2.0','method':'notifications/initialized'});write({'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}});res=reply(2);tools=res.get('result',{}).get('tools',[]);selected=[t for t in tools if t['name'] in ['open_binary','binary_session','binary_overview','search_strings','search_functions','get_pseudocode','get_xrefs','close_binary','list_symbols','analyze_function','inspect_pe_resources']];(ROOT/'evidence/rea_native_tool_schemas.json').write_text(json.dumps({'initialize':init,'tools':selected},indent=2));print('SCHEMAS',[(t['name'],t['inputSchema']) for t in selected],flush=True)
finally:
 p.stdin.close();p.terminate()
 try:p.wait(timeout=5)
 except subprocess.TimeoutExpired:p.kill();p.wait()
 log.close()
