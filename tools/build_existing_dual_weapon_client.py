"""Build only the dual-weapon patch onto a copy with stock dual hook sites.
Keeps the existing mapped sections, including all unrelated patches, intact.
WARP's header-growth file-offset bug is repaired and verified before success.
"""
from __future__ import annotations
import argparse,hashlib,json,re,struct,subprocess
from pathlib import Path
import pefile
from capstone import Cs,CS_ARCH_X86,CS_MODE_32
from capstone.x86_const import X86_OP_IMM
ROOT=Path(__file__).resolve().parents[1]
HOOKS={0xd403a0:"55 8B EC 6A FF",
       0xc4a0d0:"55 8B EC 83 EC 50",0xc4a647:"A1 F8 15 25 01"}
def sha(d):return hashlib.sha256(d).hexdigest()
def build(source,output,evidence=None,payload_path=None):
    original=source.read_bytes(); old=pefile.PE(data=original,fast_load=True)
    assert old.FILE_HEADER.Machine==0x14c and old.OPTIONAL_HEADER.ImageBase==0x400000
    for va,h in HOOKS.items():
        off=old.get_offset_from_rva(va-0x400000)
        assert original[off:off+len(bytes.fromhex(h))]==bytes.fromhex(h),f"hook {va:X} is already modified; use a stock-hook source"
    work=output.parent;work.mkdir(parents=True,exist_ok=True)
    data=bytearray(original)
    names={s.Name.rstrip(b"\0") for s in old.sections}
    for s in old.sections:
        if s.Name.rstrip(b"\0")==b".xdiff":
            assert b".dwprev" not in names
            data[s.get_file_offset():s.get_file_offset()+8]=b".dwprev\0"
    inp=work/"existing_client_dual_restored.exe";inp.write_bytes(data)
    raw_output=work/"existing-client-warp-raw.exe"
    sess=work/"existing-client-session.yml"
    sess.write_text("from: "+json.dumps(str(inp).replace("\\","/"))+"\nto: "+
                    json.dumps(str(raw_output).replace("\\","/"))+"\ninputs: {}\npatches:\n    - AllowDualCustomWeaponSprites\n",encoding="utf-8")
    settings=(ROOT/"Settings.yml").read_bytes()
    runtime_path=ROOT/"Inputs/DualWeaponRuntime/compositor.dwcp"
    original_runtime=runtime_path.read_bytes()
    selected_runtime=payload_path.read_bytes() if payload_path else original_runtime
    try:
        if selected_runtime!=original_runtime:runtime_path.write_bytes(selected_runtime)
        run=subprocess.run([str(ROOT/"win32/WARP_console.exe"),"-using",str(sess)],cwd=ROOT,
                           stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=180)
        (work/"existing-client-build.log").write_bytes(run.stdout)
        assert run.returncode==0 and b"Patch Error" not in run.stdout and b"-E-" not in run.stdout,run.stdout
    finally:
        (ROOT/"Settings.yml").write_bytes(settings)
        if selected_runtime!=original_runtime:runtime_path.write_bytes(original_runtime)
    data=bytearray(raw_output.read_bytes()); new=pefile.PE(data=bytes(data),fast_load=True)
    extra=[s for s in new.sections if s.VirtualAddress not in {x.VirtualAddress for x in old.sections}]
    assert len(extra)==1 and extra[0].Name.startswith(b".xdiff")
    sec=extra[0];start=len(data)-sec.SizeOfRawData
    # The allocation starts with the two exact native prologue trampolines.
    assert data[start:start+6]==bytes.fromhex("55 8B EC 6A FF E9")
    assert 0x400000+sec.VirtualAddress+10+struct.unpack_from("<i",data,start+6)[0]==0xd403a5
    assert data[start+16:start+23]==bytes.fromhex("55 8B EC 83 EC 50 E9")
    assert 0x400000+sec.VirtualAddress+27+struct.unpack_from("<i",data,start+23)[0]==0xc4a0d6
    repair={"reported_raw_pointer":sec.PointerToRawData,"actual_raw_pointer":start,"restored_section_bytes":{}}
    struct.pack_into("<I",data,sec.get_file_offset()+20,start)
    # WARP also leaves SizeOfHeaders at 0x400 when the tenth section header
    # ends at 0x408. The loader must see the complete section table.
    table_end=max(s.get_file_offset()+40 for s in new.sections)
    alignment=new.OPTIONAL_HEADER.FileAlignment
    header_size=((max(table_end,new.OPTIONAL_HEADER.SizeOfHeaders)+alignment-1)//alignment)*alignment
    first_raw=min(s.PointerToRawData for s in new.sections if s.SizeOfRawData and s!=sec)
    assert header_size<=first_raw,"section table cannot fit before mapped raw data"
    repair.update(reported_header_size=new.OPTIONAL_HEADER.SizeOfHeaders,
                  actual_header_size=header_size,section_table_end=table_end)
    struct.pack_into("<I",data,new.OPTIONAL_HEADER.get_field_absolute_offset("SizeOfHeaders"),header_size)
    # Preserve WARP's three new hooks, then restore every old mapped byte.
    replacements={}
    for va,h in HOOKS.items():
        off=new.get_offset_from_rva(va-0x400000)
        replacements[va]=bytes(data[off:off+len(bytes.fromhex(h))])
    for prior in old.sections:
        current=next(s for s in new.sections if s.VirtualAddress==prior.VirtualAddress)
        assert current.Misc_VirtualSize==prior.Misc_VirtualSize
        assert current.SizeOfRawData==prior.SizeOfRawData and current.Characteristics==prior.Characteristics
        before=prior.get_data();a=current.PointerToRawData
        diff=sum(x!=y for x,y in zip(before,data[a:a+len(before)]))
        repair["restored_section_bytes"][prior.Name.rstrip(b"\0").decode()]=diff
        data[a:a+len(before)]=before
    for va,blob in replacements.items():
        off=new.get_offset_from_rva(va-0x400000);data[off:off+len(blob)]=blob
    # Preserve the original overlay; security directory uses a file offset.
    overlay=old.get_overlay() or b""
    if overlay:
        oldstart=old.get_overlay_data_start_offset();newstart=len(data)
        cert=old.OPTIONAL_HEADER.DATA_DIRECTORY[4]
        if cert.Size and cert.VirtualAddress>=oldstart:
            struct.pack_into("<I",data,new.OPTIONAL_HEADER.DATA_DIRECTORY[4].get_file_offset(),
                             newstart+cert.VirtualAddress-oldstart)
        data.extend(overlay)
    new=pefile.PE(data=bytes(data),fast_load=True)
    def read(va,n):
        off=new.get_offset_from_rva(va-0x400000)
        return bytes(data[off:off+n])
    def branch(va):
        b=read(va,5);assert b[0] in [0xe8,0xe9]
        return va+5+struct.unpack_from("<i",b,1)[0]
    checks=[]
    for prior in old.sections:
        current=next(s for s in new.sections if s.VirtualAddress==prior.VirtualAddress)
        got=bytearray(current.get_data());expected=bytearray(prior.get_data())
        changed=sum(x!=y for x,y in zip(got,expected))
        for va,h in HOOKS.items():
            rel=va-0x400000-prior.VirtualAddress
            if 0<=rel<len(got):
                got[rel:rel+len(bytes.fromhex(h))]=bytes.fromhex(h)
        assert got==expected,prior.Name
        checks.append({"name":prior.Name.rstrip(b"\0").decode(),"rva":prior.VirtualAddress,
                       "changed_bytes":changed,"old_sha256":sha(expected),"new_sha256":sha(current.get_data())})
    cs=Cs(CS_ARCH_X86,CS_MODE_32);cs.detail=True
    wrapper=branch(0xc4a0d0)
    instructions=list(cs.disasm(read(wrapper,120),wrapper))
    pushes=[i.operands[0].imm for i in instructions if i.mnemonic=="push" and i.operands[0].type==X86_OP_IMM]
    calls=[i.operands[0].imm for i in instructions if i.mnemonic=="call"]
    context=pushes[1];ctx=struct.unpack("<21I",read(context,84))
    payload=selected_runtime
    _,_,codesize,entry,n,rigsize,gripsize,_=struct.unpack_from("<8I",payload)
    base=calls[0]-entry;flat=bytearray(payload[32+4*n:])
    for off in struct.unpack_from("<"+"I"*n,payload,32):
        v=struct.unpack_from("<I",flat,off)[0];struct.pack_into("<I",flat,off,base+v)
    assert read(base,len(flat))==flat,"relocated compositor/rig/grip mismatch"
    assert ctx[17]==base+codesize and ctx[20]==base+codesize+rigsize
    assert ctx[18]+256*8 <= ctx[0],"view rows overrun actor registry"
    qjs=(ROOT/"Scripts/Patches/AllowDualCustomWeaponSprites.qjs").read_text(encoding="utf-8")
    def verify_legacy(name,base):
        from dual_weapon_legacy_assets import read as read_bundle
        part=read_bundle()[name];raw=bytearray(part['data'])
        for off,target in part['relocs']:struct.pack_into('<I',raw,off,base+target)
        assert read(base,len(raw))==raw
        return {'bytes':len(raw),'relocations':len(part['relocs'])}
    equip_vir=branch(branch(0xd403a0))
    new.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
    vp_imports=[imp.address for lib in new.DIRECTORY_ENTRY_IMPORT
                if lib.dll.lower()==b'kernel32.dll' for imp in lib.imports if imp.name==b'VirtualProtect']
    assert len(vp_imports)==1, 'ambiguous or absent VirtualProtect IAT'
    vp_iat=vp_imports[0]
    emitter=work/"verify-emitted-equipment.cjs"
    expression="DualWeaponStatic.selectProfile(); DualWeaponStatic.buildEquipHook(%d,%d,%d,0x5000,%d,%d,%d).finish(%d)" % (
        0x400000+sec.VirtualAddress,ctx[0]-0x1000,ctx[0]-0x1000,vp_iat,ctx[0],ctx[18],equip_vir)
    emitter.write_text("const fs=require('fs'),vm=require('vm'); const c=vm.createContext({RagexeClientProfile:{Id:20250716}});"
        "vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),c); console.log(vm.runInContext("+json.dumps(expression)+",c));",encoding="utf-8")
    emitted=bytes.fromhex(subprocess.check_output(["node",str(emitter),str(ROOT/"Scripts/Patches/AllowDualCustomWeaponSprites.qjs")],text=True))
    assert read(equip_vir,len(emitted))==emitted,"equipment owner differs from tested QJS emitter"
    assert emitted, 'empty equipment owner'
    assert all(ctx[i]==0 for i in (1,2,3,4,8,9,10,13,14,15,16,19)), "retired legacy state is not zero"
    assert read(0x605d41,9)==bytes.fromhex("89 45 94 8B 45 0C 89 45 C8")
    depthbridge=branch(0xc4a647)
    depthcall=next(i.operands[0].imm for i in cs.disasm(read(depthbridge,40),depthbridge) if i.mnemonic=="call")
    depth=verify_legacy("DualWeaponCharacterEnvelopeCore",depthcall)
    state=ctx[0]-0x1000
    assert state%0x1000==0,"VirtualProtect state base must be VA-page aligned"
    state_end=state+0x5000
    assert read(state,0x5000)==b"\0"*0x5000,"state pages contain nonzero/code bytes"
    code_ranges=[(0x400000+sec.VirtualAddress,27), (equip_vir,len(emitted)),
                 (depthcall,depth["bytes"]),
                 (base,codesize), (wrapper,120), (depthbridge,40)]
    code_ranges += [(branch(va),5) for va in HOOKS]
    for code_va,code_size in code_ranges:
        assert code_va>=state_end or code_va+code_size<=state,"state protection removes code EXECUTE"
    assert read(0xd36ee4,5)==bytes.fromhex("E8 C7 85 9D FF"),"stock ACT frame call changed"
    ranges=sorted((s.PointerToRawData,s.PointerToRawData+s.SizeOfRawData) for s in new.sections if s.SizeOfRawData)
    assert all(b<=c for (a,b),(c,d) in zip(ranges,ranges[1:])),"raw section overlap"
    assert table_end<=new.OPTIONAL_HEADER.SizeOfHeaders<=ranges[0][0],"headers do not cover section table"
    assert max(e for _,e in ranges)<=len(data)
    for va in [wrapper,base,context,depthcall,branch(branch(0xd403a0))]:
        assert new.get_section_by_rva(va-0x400000)==new.sections[-1]
    report={"source":str(source),"source_sha256":sha(original),"output":str(output),"output_sha256":sha(data),
            "payload_sha256":sha(payload),"hook_hex":{hex(va):read(va,len(bytes.fromhex(h))).hex(" ") for va,h in HOOKS.items()},
            "hook_targets":{hex(va):hex(branch(va)) for va in HOOKS},
            "context_va":hex(context),"compositor_va":hex(base),"compositor_entry_va":hex(calls[0]),
            "legacy_core_injected":False,"depth_helper_va":hex(depthcall),"depth_helper":depth,
            "equipment_owner_va":hex(equip_vir),"equipment_owner_bytes":len(emitted),
            "equipment_owner_sha256":sha(emitted),"trampoline_va":hex(0x400000+sec.VirtualAddress),
            "state_va":hex(state),"state_end_exclusive":hex(state_end),
            "code_ranges_outside_state_pages":[[hex(a),hex(a+n)] for a,n in code_ranges],
            "existing_sections":checks,"warp_header_repair":repair,"overlay_preserved_bytes":len(overlay),
            "verified":["only three mapped hook regions changed","all other mapped bytes unchanged",
                        "full compositor and data relocation match","full equipment owner emission match","legacy capture/debug state removed","depth core unchanged",
                        "stock ACT frame call unchanged","raw section bounds and non-overlap","all hook targets mapped",
                        "SizeOfHeaders covers complete section table","state VA pages isolated from all emitted code"]}
    output.write_bytes(data)
    evidence=evidence or ROOT/"docs/evidence/dual-weapon-warp-build-20260907.json"
    evidence.parent.mkdir(parents=True,exist_ok=True)
    evidence.write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ["output_sha256","compositor_entry_va","hook_targets","verified"]},indent=2))
if __name__=="__main__":
    a=argparse.ArgumentParser(description=__doc__);a.add_argument("--source",type=Path,required=True);a.add_argument("--output",type=Path,required=True)
    a.add_argument('--evidence',type=Path,help='Separate candidate evidence from accepted deployment records')
    a.add_argument('--payload',type=Path,help='Isolated candidate DWCP; default runtime is restored after WARP exits')
    args=a.parse_args();build(args.source,args.output,args.evidence,args.payload)
