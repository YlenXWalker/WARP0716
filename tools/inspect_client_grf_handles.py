"""Read only the target client's open GRF/INI file handles; no process writes."""
import argparse,ctypes as C,json
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--pid',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
k=C.WinDLL('kernel32',use_last_error=True);n=C.WinDLL('ntdll');P=C.c_void_p;U=C.c_ulong;Z=C.c_size_t
class Entry(C.Structure):
 _fields_=[('Object',P),('Pid',Z),('Value',Z),('Access',U),('Backtrace',C.c_ushort),('Type',C.c_ushort),('Attributes',U),('Reserved',U)]
k.OpenProcess.argtypes=[U,C.c_int,U];k.OpenProcess.restype=P
k.GetCurrentProcess.restype=P;k.CloseHandle.argtypes=[P]
k.DuplicateHandle.argtypes=[P,P,P,C.POINTER(P),U,C.c_int,U]
k.GetFileType.argtypes=[P];k.GetFinalPathNameByHandleW.argtypes=[P,C.c_wchar_p,U,U]
result={'pid':a.pid,'read_only':True,'files':[]}
h=k.OpenProcess(0x40,0,a.pid)
try:
 if not h:raise C.WinError(C.get_last_error())
 size=1<<20
 while True:
  buf=C.create_string_buffer(size);length=U();status=n.NtQuerySystemInformation(64,buf,size,C.byref(length))
  if status==0:break
  assert status&0xffffffff==0xc0000004 and size<1<<28,hex(status&0xffffffff)
  size=max(size*2,length.value+4096)
 count=Z.from_buffer(buf).value
 for i in range(count):
  e=Entry.from_buffer(buf,2*C.sizeof(Z)+i*C.sizeof(Entry))
  if e.Pid!=a.pid:continue
  dup=P()
  if not k.DuplicateHandle(h,P(e.Value),k.GetCurrentProcess(),C.byref(dup),0,0,2):continue
  try:
   if k.GetFileType(dup)!=1:continue
   name=C.create_unicode_buffer(32768);length=k.GetFinalPathNameByHandleW(dup,name,len(name),0)
   if length and name.value.lower().endswith(('.grf','.ini')):result['files'].append({'handle':int(e.Value),'path':name.value})
  finally:k.CloseHandle(dup)
except Exception as e:result['error']=str(e)
finally:
 if h:k.CloseHandle(h)
 a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf8')
