import ctypes,ctypes.util,json,hashlib,struct
from pathlib import Path
ROOT=Path('/workspace/scratch/1a6b54b85a4e/rv_rea');source=ROOT.parent/'upload/Win64(1).rar';dest=ROOT/'native_input';dest.mkdir(parents=True,exist_ok=True)
a=ctypes.CDLL(ctypes.util.find_library('archive'));a.archive_read_new.restype=ctypes.c_void_p
for n in ['archive_read_support_format_all','archive_read_support_filter_all','archive_read_data_skip','archive_read_free']:getattr(a,n).argtypes=[ctypes.c_void_p]
a.archive_read_open_filename.argtypes=[ctypes.c_void_p,ctypes.c_char_p,ctypes.c_size_t];a.archive_read_next_header.argtypes=[ctypes.c_void_p,ctypes.POINTER(ctypes.c_void_p)];a.archive_entry_pathname.argtypes=[ctypes.c_void_p];a.archive_entry_pathname.restype=ctypes.c_char_p;a.archive_entry_size.argtypes=[ctypes.c_void_p];a.archive_entry_size.restype=ctypes.c_longlong;a.archive_entry_filetype.argtypes=[ctypes.c_void_p];a.archive_read_data.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_size_t];a.archive_read_data.restype=ctypes.c_longlong;a.archive_error_string.argtypes=[ctypes.c_void_p];a.archive_error_string.restype=ctypes.c_char_p
r=a.archive_read_new();a.archive_read_support_format_all(r);a.archive_read_support_filter_all(r);assert a.archive_read_open_filename(r,str(source).encode(),10240)==0,a.archive_error_string(r);found=[]
while True:
 e=ctypes.c_void_p();code=a.archive_read_next_header(r,ctypes.byref(e))
 if code==1:break
 if code<0:raise RuntimeError(a.archive_error_string(r))
 name=a.archive_entry_pathname(e).decode();size=a.archive_entry_size(e)
 if name.replace('\\','/').endswith('/Ride-Win64-Shipping.exe'):
  assert a.archive_entry_filetype(e)==0o100000
  output=dest/'Ride-Win64-Shipping.exe';hasher=hashlib.sha256();buffer=ctypes.create_string_buffer(1024*1024);total=0
  with output.open('wb') as f:
   while True:
    got=a.archive_read_data(r,buffer,len(buffer))
    if got<0:raise RuntimeError(a.archive_error_string(r))
    if got==0:break
    data=buffer.raw[:got];f.write(data);hasher.update(data);total+=got
  assert total==size
  with output.open('rb') as f:
   header=f.read(4096);assert header[:2]==b'MZ';pe=struct.unpack_from('<I',header,60)[0];assert header[pe:pe+4]==b'PE\0\0';machine,sections,time=struct.unpack_from('<HHI',header,pe+4);magic=struct.unpack_from('<H',header,pe+24)[0]
  found.append({'path':str(output),'bytes':total,'sha256':hasher.hexdigest(),'machine':hex(machine),'optional_header_magic':hex(magic),'sections':sections,'coff_timestamp':time})
 else:a.archive_read_data_skip(r)
a.archive_read_free(r);assert len(found)==1;assert found[0]['machine']=='0x8664' and found[0]['optional_header_magic']=='0x20b';(ROOT/'evidence/game_binary_identity.json').write_text(json.dumps(found[0],indent=2));print('GAME_BINARY',json.dumps(found[0]),flush=True)
