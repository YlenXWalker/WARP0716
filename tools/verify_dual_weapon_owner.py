"""Execute the actual QJS-emitted x86 equipment owner with adversarial native ABI stubs."""
from pathlib import Path
from collections import Counter
import argparse,hashlib,json,struct,subprocess,sys
from unicorn import Uc, UC_ARCH_X86, UC_MODE_32, UC_HOOK_CODE
from unicorn.x86_const import *
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"Outputs/dual_weapon_resource_build"
OUT.mkdir(exist_ok=True,parents=True)
EMITTER="""const fs=require('fs'),vm=require('vm'); const c=vm.createContext({RagexeClientProfile:{Id:20250716}});vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),c);console.log(vm.runInContext('DualWeaponStatic.selectProfile(); DualWeaponStatic.buildEquipHook(0x111000,0x300000,0x300000,0x5000,0x112000,0x301000,0x300400).finish(0x200000)',c));"""
(OUT/"emit_equipment.cjs").write_text(EMITTER,encoding="utf-8")
code=bytes.fromhex(subprocess.check_output(["node",str(OUT/"emit_equipment.cjs"),str(ROOT/"Scripts/Patches/AllowDualCustomWeaponSprites.qjs")],text=True))
(OUT/"equipment.bin").write_bytes(code)
u=Uc(UC_ARCH_X86,UC_MODE_32);u.mem_map(0x100000,0x2000000);u.mem_write(0x200000,code)
STOP=0x110100;EQUIP=0x111000;ADD=0xa8e800;RELEASE=0xa8f910;VIEW=0xd8a1d0;PAIR=0xd39130;CLASS=0xd5ddb0;SUFFIX=0xd60de0
for addr,blob in [(STOP,b"\xcc"),(EQUIP,b"\xc2\x08\x00"),(ADD,b"\xc3"),(RELEASE,b"\xc3"),
                  (VIEW,b"\xc2\x04\x00"),(PAIR,b"\xc2\x08\x00"),(CLASS,b"\xc2\x04\x00"),(SUFFIX,b"\xc2\x04\x00")]: u.mem_write(addr,blob)
def w(p,*values):u.mem_write(p,struct.pack("<"+"I"*len(values),*values))
def r(p):return struct.unpack("<I",u.mem_read(p,4))[0]
def native_result(value=0):
    u.reg_write(UC_X86_REG_EAX,value)
    u.reg_write(UC_X86_REG_ECX,0xdead0001);u.reg_write(UC_X86_REG_EDX,0xdead0002)
def row(actor):return 0x301000+((actor>>4)&255)*60
def views(actor):return 0x300400+((actor>>4)&255)*8
# This harness isolates resource lifetime and adversarial native ABI behavior.
# Cold initialization/real trampoline permissions are covered separately by
# verify_dual_weapon_page_protection.py against archived and rebuilt PE files.
w(0x300000,1)
counts=Counter(); resources={}; active={}; events=[]; class_calls=[]; pair_calls=[]; suffix_calls=[]; case_count=0
SUPPORTED_TYPES={1,2,6}
item_views={1001:45,1002:34,2001:0xffffffff,2002:999,2003:998,2004:997,2005:996,2006:995,2007:994}
view_classes={45:2,34:1,999:0,998:24,997:25,996:30,995:31,994:0xffffffff}
# Expanded views use ItemIds outside every hard-coded D39130 range.
item_views.update({1000000+k:500+k for k in range(1,24)})
view_classes.update({500+k:k for k in range(1,24)})
scenario={"missing":False,"no_trail":False,"names":"correct"}
suffixes={1001:"_트윈엣지_B".encode('cp949'),1002:"_제니나이프".encode('cp949')}
suffixes.update({1000000+k:('_Weapon_%d'%k).encode() for k in range(1,24)})
suffixes[1000008]="_클럽".encode('cp949')
suffix_pool={}
NAME_PREFIX="sprite\\인간족\\어세신\\어세신_여".encode('cp949')

def expected_suffix(item):
    mode=scenario['names']
    if mode=='empty_suffix':return b''
    if mode=='long_suffix':return b'_' + b'x'*239
    if mode=='unterminated_suffix':return b'y'*256
    if mode in ('cp949_trail_exact','cp949_trail_case_mismatch'):return b'_\x81\x41'
    if mode=='unterminated_dbcs':return b'_\x81'
    if mode=='ascii_case':return b'_MiXeD'
    return suffixes.get(item,b'_stock')

def resource_name(item,extension):
    mode=scenario['names'];suffix=expected_suffix(item)
    if mode=='gladius_fallback' and item==1219:suffix=b'_dagger'
    if mode=='mace_fallback' and item==1000008:suffix="_검".encode('cp949')
    if mode=='act_mismatch' and extension==b'.act':suffix=b'_wrong_act'
    if mode=='spr_mismatch' and extension==b'.spr':suffix=b'_wrong_spr'
    if mode=='wrong_extension':extension=b'.bad'
    if mode=='suffix_not_at_end':suffix+=b'_extra'
    if mode=='short_name':return b'.act\0'
    if mode=='unterminated_name':return b'z'*256
    if mode=='long_name':return b'z'*240+suffix+extension+b'\0'
    if mode=='cp949_trail_case_mismatch':suffix=b'_\x81\x61'
    if mode=='ascii_case':suffix=b'_mIxEd';extension=extension.upper()
    return NAME_PREFIX+suffix+extension+b'\0'
def resource_set(key):
    k=(key,scenario["missing"],scenario["no_trail"],scenario['names'])
    if k not in resources:
        start=0x600000+len(resources)*0x800
        resources[k]=[start,start+0x200,start+0x400,start+0x600]
        if scenario["no_trail"]:resources[k][2:]=[0,0]
        if scenario["missing"] and key=="solo1002": resources[k][1]=0
        item=int(key[4:]) if key.startswith('solo') else 0
        for pointer,extension in zip(resources[k],[b'.spr',b'.act',b'.spr',b'.act']):
            if pointer:
                # Real live CResource names begin at decimal 20, not 0x20.
                u.mem_write(pointer+20,resource_name(item,extension))
    return resources[k]
def hook(uc,addr,size,_):
    if addr==STOP:uc.emu_stop();return
    esp=uc.reg_read(UC_X86_REG_ESP);ecx=uc.reg_read(UC_X86_REG_ECX)
    if addr==EQUIP:
        main,off=r(esp+4),r(esp+8);events.append((main,off))
        for ptr in active.get(ecx,[]): counts[ptr]-=1
        if main and off: key="dual"
        elif main:key="solo"+str(main)
        elif off:key="offonly"
        else:key="empty"
        res=resource_set(key) if main or off else [0]*4
        active[ecx]=[p for p in res if p]
        counts.update(active[ecx])
        sp=0x500000+((ecx>>12)&255)*0x100;ac=sp+0x40
        w(ecx+0x440,main,off);w(ecx+0x4ac,sp,sp+28);w(ecx+0x4b8,ac,ac+28)
        w(sp+20,res[0],res[2]);w(ac+20,res[1],res[3])
        # Retained rows must not be published until the restore call has returned.
        if len(events)>1: assert r(row(ecx))==0 or r(row(ecx))!=ecx
        native_result()
    elif addr==VIEW:
        native_result(item_views.get(r(esp+4),0))
    elif addr==CLASS:
        view=r(esp+4);class_calls.append(view)
        native_result(view_classes.get(view,view))
    elif addr==PAIR:
        a,b=r(esp+4),r(esp+8);pair_calls.append((a,b))
        native_result(28 if {a,b}=={1001,1002} else 0)
    elif addr==SUFFIX:
        item=r(esp+4);suffix_calls.append(item)
        # Incoming ECX is not an item-table receiver; the native suffix resolves globally.
        if scenario['names']=='null_suffix':native_result(0)
        else:
            suffix=expected_suffix(item)
            if suffix not in suffix_pool:
                pointer=0x1700000+len(suffix_pool)*0x200
                suffix_pool[suffix]=pointer
                u.mem_write(pointer,suffix+(b'' if scenario['names']=='unterminated_suffix' else b'\0'))
            native_result(suffix_pool[suffix])
    elif addr==ADD:
        assert ecx and counts[ecx]>0,"AddRef after native resource died"
        counts[ecx]+=1;native_result()
    elif addr==RELEASE:
        assert ecx and counts[ecx]>0,"invalid/double Release"
        counts[ecx]-=1;native_result()
u.hook_add(UC_HOOK_CODE,hook)
def invoke(actor,main,off):
    global case_count
    case_count+=1
    events.clear();class_calls.clear();pair_calls.clear();suffix_calls.clear();esp=0x1f00000;w(esp,STOP,main,off)
    saved=[UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
    for i,reg in enumerate(saved):u.reg_write(reg,0x999000+i*16)
    u.reg_write(UC_X86_REG_ECX,actor);u.reg_write(UC_X86_REG_ESP,esp)
    u.emu_start(0x200000,STOP,count=100000)
    assert u.reg_read(UC_X86_REG_EIP)==STOP
    assert u.reg_read(UC_X86_REG_ESP)==esp+12
    for i,reg in enumerate(saved):assert u.reg_read(reg)==0x999000+i*16
    assert (r(actor+0x440),r(actor+0x444))==(main,off),"temporary actor state leaked"
def balanced():
    expected=Counter(ptr for live in active.values() for ptr in live)
    for actor in active:
        if r(row(actor))==actor:
            expected.update(r(row(actor)+i) for i in range(4,44,4) if r(row(actor)+i))
    assert {k:v for k,v in counts.items() if v}==dict(expected),"reference imbalance"
a=0x400080
# The observed male Gladius failure: Lua requests _1219 while native missing
# Assassin artwork resolves a generic _dagger name. Exact names must still gate.
item_views.update({1219:33,13412:45});view_classes[33]=1
suffixes.update({1219:b'_1219',13412:b'_13412'})
w(a+0x260,1)
for mode in ['correct','gladius_fallback']:
    scenario['names']=mode
    for main,off in [(1219,13412),(13412,1219),(0,1219)]:
        invoke(a,main,off)
        assert (r(row(a))==a)==(mode=='correct')
        if mode=='correct':assert r(row(a)+56)==1
        balanced()
scenario['names']='correct';w(a+0x260,0)
invoke(a,1001,1002);assert events==[(1001,1002),(1002,0),(1001,0),(1001,1002)]
assert r(row(a))==a and (r(views(a)),r(views(a)+4))==(45,34)
assert (r(row(a)+44),r(row(a)+48),r(row(a)+52))==(28,2,1)
assert class_calls==[34,45] and pair_calls==[(1001,1002)];balanced()
assert suffix_calls==[1002,1001]
invoke(a,0,1002);assert events==[(0,1002),(1002,0),(0,1002)]
assert r(row(a)+4)==0 and r(row(a)+20) and r(views(a))==0 and r(views(a)+4)==34
assert (r(row(a)+44),r(row(a)+48),r(row(a)+52))==(0,0,1) and not pair_calls;balanced()
invoke(a,1001,0);assert r(row(a))==0;balanced()
scenario["no_trail"]=True
invoke(a,1001,1002);assert r(row(a))==a and r(row(a)+12)==0;balanced()
scenario["missing"]=True
invoke(a,1001,1002);assert r(row(a))==0 and events[-1]==(1001,1002);balanced()
scenario.update(missing=False,no_trail=False)
invoke(a,1001,1002);balanced()
b=a+0x1000;old=bytes(u.mem_read(row(a),60))
invoke(b,1001,1002);assert events==[(1001,1002)] and bytes(u.mem_read(row(a),60))==old;balanced()
invoke(a,1001,404);assert r(row(a))==0 and events==[(1001,404)];balanced()
# Exercise every single class, including explicit stock fallback for all
# combinations outside the user-requested dagger/sword/axe set.
for main_type in range(0,24):
    for off_type in range(1,24):
        main=1000000+main_type if main_type else 0;off=1000000+off_type
        invoke(a,main,off)
        supported=off_type in SUPPORTED_TYPES and (not main_type or main_type in SUPPORTED_TYPES)
        if not supported:
            assert r(row(a))==0 and events==[(main,off)]
            assert not suffix_calls and not pair_calls
            assert class_calls==[500+off_type]+([500+main_type] if main_type and off_type in SUPPORTED_TYPES else [])
            balanced()
            continue
        assert r(row(a))==a
        assert (r(row(a)+44),r(row(a)+48),r(row(a)+52))==(0,main_type,off_type)
        assert (r(views(a)),r(views(a)+4))==(500+main_type if main_type else 0,500+off_type)
        assert class_calls==[500+off_type]+([500+main_type] if main_type else [])
        assert pair_calls==([(main,off)] if main_type else [])
        assert suffix_calls==[off]+([main] if main else [])
        assert events==([(main,off),(off,0),(main,0),(main,off)] if main_type else [(0,off),(off,0),(0,off)])
        balanced()
# Mace is now outside scope and must reject before any temporary solo load.
scenario['names']='mace_fallback'
invoke(a,1000008,1002)
assert r(row(a))==0 and events==[(1000008,1002)]
assert not suffix_calls;balanced()
invoke(a,1002,1000008)
assert r(row(a))==0 and events==[(1002,1000008)]
assert not suffix_calls;balanced()
identity_failures=['act_mismatch','spr_mismatch','wrong_extension','suffix_not_at_end',
                   'short_name','unterminated_name','long_name','empty_suffix','null_suffix',
                   'long_suffix','unterminated_suffix','cp949_trail_case_mismatch','unterminated_dbcs']
for mode in identity_failures:
    scenario['names']=mode
    invoke(a,1001,1002)
    assert r(row(a))==0 and events==[(1001,1002),(1002,0),(1001,1002)],mode
    assert suffix_calls==[1002],mode
    balanced()
for mode in ['ascii_case','cp949_trail_exact']:
    scenario['names']=mode
    invoke(a,1001,1002)
    assert r(row(a))==a and suffix_calls==[1002,1001],mode
    balanced()
scenario['names']='correct'
# View<=0, unmapped class0, sentinel24, combined25/30, unknown31, negative
# class: reject both off and main without loading temporary resources.
for invalid_item in [404,2001,2002,2003,2004,2005,2006,2007]:
    for main,off in [(1001,invalid_item),(invalid_item,1002)]:
        invoke(a,main,off)
        assert r(row(a))==0 and events==[(main,off)] and not pair_calls
        balanced()
# Expanded-class collision keeps the older owner/resources untouched.
invoke(a,1000006,1000002);assert r(row(a))==a;balanced()
old=bytes(u.mem_read(row(a),60));old_views=bytes(u.mem_read(views(a),8))
invoke(b,1000001,1000006)
assert events==[(1000001,1000006)] and bytes(u.mem_read(row(a),60))==old
assert bytes(u.mem_read(views(a),8))==old_views;balanced()
invoke(a,0,0);assert r(row(a))==0;balanced()
report={"initialization":"warm state; cold PE protection tested separately","cases":case_count,"ordered_class_pairs":529,"off_only_classes":23,"passed":True,"accepted_pair_count":9,"rejected_pair_count":520,"accepted_off_only_classes":[1,2,6],"machine_code_bytes":len(code),"checks":["stock-first",
        "stock state restored before publication","dual capture order","off-only capture order",
        "actual view IDs retained","optional null trails","partial-load cleanup","unequip releases",
        "only classes1/2/6 admitted from expanded views; other20 rejected before temporary load","legacy pair28 code preserved","unknown/sentinel/combined/negative class rejected","shield/unknown view rejected","only combined pair uses D39130","hash collision preserves other actor","AddRef/Release balanced",
        "callee-save registers under volatile-register clobber","RET 8 stack balance",
        "native decimal20 resource filename offset","one immediate Lua suffix call per temporary item",
        "mace class8 with sword art rejected in either hand","independent ACT/SPR identity mismatch rejected",
        "bounded suffix/name NUL scans","empty/missing Lua suffix rejected","exact filename end and extension",
        "ASCII filename case folding","CP949 ASCII-valued trail bytes remain exact"]}
report['source_sha256']=hashlib.sha256((ROOT/'Scripts/Patches/AllowDualCustomWeaponSprites.qjs').read_bytes()).hexdigest()
report['owner_code_sha256']=hashlib.sha256(code).hexdigest()
report['checks'].append('male Gladius1219/view33 plus Naght13412/view45: exact _1219 accepts both orders/off-only; generic fallback rejects without leaking references')
parser=argparse.ArgumentParser();parser.add_argument('--report',type=Path,default=ROOT/'docs/evidence/assassin-weapon-owner-20260907.json');args=parser.parse_args()
args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
print(json.dumps(report,indent=2))
