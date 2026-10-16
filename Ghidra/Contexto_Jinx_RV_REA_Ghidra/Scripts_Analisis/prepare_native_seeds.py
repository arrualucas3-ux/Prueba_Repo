"""Locate immutable PE seeds; candidate names remain analyst inferences."""
from pathlib import Path
import bisect, hashlib, json, re, struct

ROOT = Path(__file__).resolve().parent
meta = json.loads((ROOT/'evidence/native_string_seeds.json').read_text())
binary = (ROOT/'native_input/Ride-Win64-Shipping.exe').read_bytes()
base = int(meta['image_base'], 16)
sections = meta['sections']
text = next(s for s in sections if s['name'] == '.text')
pdata = next(s for s in sections if s['name'] == '.pdata')
rdata = next(s for s in sections if s['name'] == '.rdata')

def offset(address):
    for section in sections:
        delta = address-base-section['rva']
        if 0 <= delta < section['raw_size']:
            return section['raw_offset']+delta
    return None

def name_at(address):
    pos = offset(address)
    if pos is None: return None
    raw = binary[pos:pos+160]
    end = raw.find(b'\0')
    if end < 1: return None
    try: value = raw[:end].decode('ascii')
    except UnicodeDecodeError: return None
    return value if re.fullmatch(r'[A-Za-z_][A-Za-z_0-9]{0,110}', value) else None

rows = [(base+a, base+end) for a,end,_ in struct.iter_unpack('<III',binary[pdata['raw_offset']:pdata['raw_offset']+pdata['virtual_size']]) if a and end>a]
starts = [r[0] for r in rows]
functions = {}

def add_function(address, reason, name=None):
    index = bisect.bisect_right(starts,address)-1
    if index < 0 or not (rows[index][0] <= address < rows[index][1]): return
    start,end = rows[index]
    entry = functions.setdefault(start, {'address':hex(start),'unwind_end':hex(end),'reasons':[]})
    entry['reasons'].append(reason)
    if name: entry['candidate_name']=name

# Native-function name/pointer pairs in the reflection region around the character.
pairs=[]
for address in range(0x148f1b000,0x148f202d0,8):
    pos=offset(address)
    string_ptr,function_ptr=struct.unpack_from('<QQ',binary,pos)
    if base+text['rva'] <= function_ptr < base+text['rva']+text['virtual_size']:
        name=name_at(string_ptr)
        if name:
            item={'table_address':hex(address),'name_pointer':hex(string_ptr),'name':name,'function_address':hex(function_ptr)}
            pairs.append(item)
            add_function(function_ptr,{'kind':'candidate_native_registration_pair',**item}, 'Candidate_exec_'+name)

targets={int(h['address'],16) for h in meta['hits'] if h['term'] in ('RGFirstPersonCharacter','ReceiveIsRagdolling','ReceiveSetRagdolled')}
targets.add(0x148f202d0-2)
targets.update(int(p['table_address'],16) for p in pairs)
code=binary[text['raw_offset']:text['raw_offset']+text['virtual_size']]
for match in re.finditer(b'[\x48\x4c][\x8d\x8b][\x05\x0d\x15\x1d\x25\x2d\x35\x3d]',code):
    pos=match.start()
    if pos+7 > len(code):continue
    address=base+text['rva']+pos
    destination=address+7+struct.unpack_from('<i',code,pos+3)[0]
    if destination in targets:
        add_function(address,{'kind':'candidate_rip_reference','source':hex(address),'target':hex(destination)})

seeds=sorted(functions.values(),key=lambda v:int(v['address'],16))
session=ROOT/'direct_native_session';session.mkdir(exist_ok=True)
(session/'seeds.tsv').write_text(''.join(s['address']+'\tfunction\t'+s.get('candidate_name','Candidate_character_seed_'+s['address'][2:])+'\n' for s in seeds))
report={'scope':'Targeted PE reflection and native character functions; no default whole-program auto-analysis',
        'target_sha256':hashlib.sha256(binary).hexdigest(),'runtime_function_records':len(rows),'candidate_registration_pairs':pairs,'function_seeds':seeds,
        'limitations':['Name/pointer adjacency and raw RIP-pattern matches are candidates until confirmed by decoded instructions and registration code.', 'No game execution or Blueprint bytecode interpretation.']}
(ROOT/'evidence/native_seed_inventory.json').write_text(json.dumps(report,indent=2))
print('Scoped native functions:',len(seeds),'registration candidates:',len(pairs))
for p in pairs:print(p['name'],p['function_address'])
