"""Read-only snapshot of the profiled 2025 dual-weapon client. Never writes process memory.

Address profiles are restricted to the exact inspected EXE hashes listed below.
Run elevated only when the client is elevated. Output contains render data, not a dump.
"""
import argparse
import ctypes as C
import hashlib
import json
import math
import struct
import time
from pathlib import Path

PROFILES = {
    '6e470532594152e65a8bb2f982c6d14bb630f3a11355e6cc634e8db4f1b5c972':0x1f3c640,
    'eed157256a8b8fbedcf6a1e11ab04c930cb1975401e44c137524f6f92d628357':0x1f3c640,
    'c87d98b5b132186ce2cb4378b7ac308064282ba9f2006fae3f2a29521ed83f82':0x1f3c640,
    '93b65d24eeeaf54b0a77002b30c6b375253e942507685aba6d567f365a495bc0':0x1f3c640,
    'a19f4efb4220a1ebd512b4155000d099bd2ec8897ef5f83b285a2d3012eec14c':0x1f04a40,
    '7568ea2650cfc880d4a3bd2cd982ba2dffd720a6caf2eb11fc1842fc3b44b232':0x1f04a40,
    '1b3dcfbd867185f75ce56c106ba73718270cfeef18416d165b55ca3d9fc7c4fa':0x1f04a40,
    '1041a47eea6ce27176ab08abcb4b91142d877c844885f95f5b66c363864016f8':0x1ef3a40,
    '4e23389333cd873e3f136b48a67aa20f95d648c8a254318b6630b4266858636c':0x1e92a40,
    '95674dbae0b470c7cef7eade9580dea06038f337228d5f10753f1d73ff5d4220':0x1e89a40,
    '34c98e38905dc45ce568617b409b88b8cf551a1d6fecb4670258a183b1c36a21': 0x1e82830,
    '0bb06dbc84d9e0a5df4fb3002b8946388d00158576ef18be74b3fbff754d4509': 0x1e877c0,
    '91b1690045634a07dae3b09c52a5564b8ae7895b16e53b1bb9235b2ed6bedeb8': 0x1e87a30,
    'c2e857e3e9d63b510f8b7f31015f821f951aab5033aeb404806acb1751eeeb02': 0x1e87a40,
}
ROOT = Path(__file__).resolve().parents[1]

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--pid', type=int, required=True)
    p.add_argument('--seconds', type=float, default=8)
    p.add_argument('--output', type=Path, required=True)
    args = p.parse_args()
    assert 0 < args.seconds <= 60
    k = C.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.argtypes = [C.c_uint32, C.c_int, C.c_uint32]
    k.OpenProcess.restype = C.c_void_p
    k.CloseHandle.argtypes = [C.c_void_p]
    k.ReadProcessMemory.argtypes = [C.c_void_p, C.c_void_p, C.c_void_p, C.c_size_t, C.POINTER(C.c_size_t)]
    k.QueryFullProcessImageNameW.argtypes = [C.c_void_p, C.c_uint32, C.c_wchar_p, C.POINTER(C.c_uint32)]
    report = {'schema': 'dual_weapon_read_only_live/v1', 'pid': args.pid, 'atomic_snapshot': False}
    h = k.OpenProcess(0x1010, 0, args.pid)
    try:
        if not h: raise C.WinError(C.get_last_error())
        name = C.create_unicode_buffer(32768); count = C.c_uint32(len(name))
        if not k.QueryFullProcessImageNameW(h, 0, name, C.byref(count)): raise C.WinError(C.get_last_error())
        path = Path(name.value)
        report['exe'] = str(path)
        report['sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
        assert report['sha256'] in PROFILES, 'unprofiled executable; no process memory inspected'
        def read(address, size):
            assert 0x10000 <= address < 0x80000000 and 0 <= size <= 0x20000
            buffer = C.create_string_buffer(size); done = C.c_size_t()
            if not k.ReadProcessMemory(h, address, buffer, size, C.byref(done)): raise C.WinError(C.get_last_error())
            assert done.value == size
            return buffer.raw
        def words(address, n): return list(struct.unpack('<'+'I'*n, read(address, n*4)))
        def frame(act, action, index):
            begin,end = words(act+0x110,2)
            assert begin and 0 <= action < (end-begin)//12 <= 512
            fb,fe = words(begin+12*action,2)
            assert 0 <= index < (fe-fb)//68 <= 256
            ptr = fb+68*index; raw = read(ptr,68); f = struct.unpack('<17I',raw)
            assert 0 <= f[11] <= 128
            layers = [list(struct.unpack('<4iI2f2i',read(f[8]+36*i,36))) for i in range(min(f[11],8))]
            anchors=[]
            if f[13] and f[14]>=f[13] and (f[14]-f[13])%12==0 and (f[14]-f[13])//12<=16:
                anchors=[list(struct.unpack('<3i',read(f[13]+12*i,12))) for i in range((f[14]-f[13])//12)]
            return {'address':ptr,'frame_count':(fe-fb)//68,'layers':layers,'anchors':anchors,'raw':list(f)}
        def resource(addr, kind):
            out={'address':addr,'name':read(addr+20,240).split(b'\0')[0].decode('cp949',errors='replace')}
            if kind=='act':
                out['frames']={}
                for action in [32,33,34,35,36,37,38,39,80,88]:
                    try: out['frames'][str(action)]=frame(addr,action,0)
                    except (OSError,AssertionError): pass
                out['held_frames']={}
                for action in range(32,40):
                    for index in range(6):
                        try:out['held_frames'][f'{action}:{index}']=frame(addr,action,index)
                        except (OSError,AssertionError):pass
            else:
                out['images']={}
                for image_kind in [0,1]:
                    begin,end=words(addr+0x510+image_kind*12,2)
                    assert 0 <= (end-begin)//4 <= 65536
                    for index in range((end-begin)//4):
                        image=words(begin+index*4,1)[0]
                        out['images'][f'{image_kind}:{index}']={'address':image,'dimensions':list(struct.unpack('<2H2h',read(image,8)))}
            return out
        hook=read(0xc4a0d0,5); assert hook[0]==0xe9
        wrapper=0xc4a0d5+struct.unpack('<i',hook[1:])[0]
        assert read(wrapper,8)==bytes.fromhex('55 8b ec 56 8b f1 c7 05'), 'live hook mismatch'
        scope_address=words(wrapper+8,1)[0]
        ctx=words(PROFILES[report['sha256']],21); report['context']=ctx
        report['draw_wrapper']=wrapper; report['scope_address']=scope_address
        report['state']=words(0x1e60000,32)
        report['rows']=[]; resources={}
        for slot in range(256):
            row=words(ctx[0]+slot*60,15)
            if not row[0]:continue
            entry={'slot':slot,'row':row}
            try:
                actor=row[0]; vt=words(actor,1)[0]
                assert 0x400000 <= vt < 0x1e90000, 'stale registry row; actor address no longer has an image vtable'
                entry.update(vtable_address=vt,vtable=words(vt,24),actor_flags_e8=words(actor+0xe8,1)[0],action_frame=words(actor+0x38,2),items=words(actor+0x440,2),views=words(ctx[18]+slot*8,2))
                begin,end=words(actor+0x4ac,2)
                entry['sprite_slots']=words(begin,min((end-begin)//4,16))
                for spr in entry['sprite_slots']:
                    if spr and str(spr) not in resources:resources[str(spr)]=resource(spr,'spr')
                for i in [1,2,3,4,5,6,7,8,9,10]:
                    if row[i] and str(row[i]) not in resources:
                        kind='spr' if i in [1,3,5,7] else 'act'
                        resources[str(row[i])]=resource(row[i],kind)
            except (OSError,AssertionError) as error:entry['error']=str(error)
            report['rows'].append(entry)
        report['resources']=resources
        table=words(0x1602410,1)[0]
        report['hand_prefix_table']=table
        report['hand_prefixes']={}
        for index in [0,6,12,17,4013,4014,4015,4016,4017,4018,23,24,25,26,27,28,29,30,31]:
            try:
                ptr=words(table+index*4,1)[0]
                report['hand_prefixes'][str(index)]={'address':ptr,'text':read(ptr,128).split(b'\0')[0].decode('cp949',errors='replace')}
            except (OSError,AssertionError):pass
        # Existing depth instrumentation retains a packet pointer. It may be stale;
        # preserve that caveat and capture before/after scope values for race checks.
        packets={}; captures={}; deadline=time.monotonic()+args.seconds
        actors={entry['row'][0] for entry in report['rows'] if 'error' not in entry}
        palettes={int(addr)+0x110 for addr,r in resources.items() if 'images' in r}
        images={im['address'] for r in resources.values() for im in r.get('images',{}).values()}
        while time.monotonic()<deadline:
            cap=words(ctx[1],4); captures[tuple(cap)]=cap
            scope=words(scope_address,4)
            if scope[1] in actors and scope[2]:
                try:
                    raw=read(scope[2]-4,60)
                    after=words(scope_address,4)
                    priority=struct.unpack('<I',raw[:4])[0]
                    aux=list(struct.unpack('<2I',raw[52:60]))
                    if scope==after and priority==scope[3]+1 and aux[0] in palettes:
                        packet=list(struct.unpack('<6fIf3II',raw[4:52]))
                        if packet[-1] not in images or not all(math.isfinite(v) and abs(v)<32768 for v in packet[:6]):continue
                        if raw!=read(scope[2]-4,60):continue
                        key=(scope[1],scope[2],raw)
                        if len(packets)<1000:
                            packets[key]={'scope':scope,'priority':priority,'packet':packet,'aux':aux,'actor_action_frame':words(scope[1]+0x38,2),'pointer_may_be_stale':True}
                except (OSError,AssertionError):pass
            time.sleep(.001)
        report['retained_packets']=list(packets.values()); report['image_captures']=list(captures.values())
        report['captured_player_actors']=[]
        for actor in sorted({cap[0] for cap in captures.values()}):
            try:
                if words(actor,1)[0]!=0x1094810:continue
                entry={'actor':actor,'items':words(actor+0x440,2),'action_frame':words(actor+0x38,2),'gender':words(actor+0x260,1)[0]}
                if not any(entry['items']):continue
                for kind,offset in [('spr',0x4ac),('act',0x4b8)]:
                    begin,end=words(actor+offset,2);assert 0<=(end-begin)//4<=16
                    slots=words(begin,(end-begin)//4);entry[kind+'_slots']=slots
                    for ptr in slots:
                        if ptr and str(ptr) not in resources:resources[str(ptr)]=resource(ptr,kind)
                report['captured_player_actors'].append(entry)
            except (OSError,AssertionError):continue
    except Exception as error:
        report['error']=repr(error)
    finally:
        if h:k.CloseHandle(h)
        args.output.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    if 'error' in report:raise RuntimeError(report['error'])

if __name__=='__main__':main()
