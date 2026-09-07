"""Build the freestanding x86 original-resource compositor with MSVC.
No installed DLL is required by the client. The PE is only a relocation container.
"""
from __future__ import annotations
import argparse, hashlib, json, struct, subprocess, zlib
from pathlib import Path
import pefile

ROOT = Path(__file__).resolve().parents[1]
def build(tool_dir: Path, output: Path, measure_contacts=False):
    source = ROOT / "CustomDLL/DualWeapon/compositor.c"
    basis = ROOT / "CustomDLL/DualWeapon/native_basis.h"
    pixel_profile = ROOT / "CustomDLL/DualWeapon/grip_profile.h"
    edge_profile = ROOT / "CustomDLL/DualWeapon/held_edge_contacts.h"
    male_profile = ROOT / "CustomDLL/DualWeapon/male_profile.h"
    male_source = ROOT / "CustomDLL/DualWeapon/male_compositor.h"
    work = ROOT / "Outputs/dual_weapon_resource_build"
    work.mkdir(parents=True, exist_ok=True)
    obj, dll = work/"compositor.obj", work/"compositor.dll"
    compile_args = [str(tool_dir/"cl.exe"), "/nologo", "/c", "/TP", "/GR-", "/O2", "/Oi", "/GS-", "/Zl",
                    "/arch:SSE2", "/fp:precise", "/W4", "/WX", "/Fo"+str(obj), str(source)]
    if measure_contacts:
        compile_args.insert(1,"/DDW_MEASURE_CONTACTS")
    link_args = [str(tool_dir/"link.exe"), "/nologo", "/DLL", "/NOENTRY", "/NODEFAULTLIB",
                 "/MACHINE:X86", "/DYNAMICBASE:NO", "/NXCOMPAT", "/OPT:REF", "/OPT:ICF",
                 "/BREPRO", "/OUT:"+str(dll), str(obj)]
    for args in [compile_args, link_args]:
        subprocess.run(args, check=True, cwd=work)
    pe = pefile.PE(str(dll))
    assert not getattr(pe, "DIRECTORY_ENTRY_IMPORT", None), "runtime imports forbidden"
    sections = [s for s in pe.sections if s.Name.rstrip(b"\0") != b".reloc"]
    first = min(s.VirtualAddress for s in sections)
    end = max(s.VirtualAddress + s.Misc_VirtualSize for s in sections)
    code = bytearray(end-first)
    for sec in sections:
        data = sec.get_data()[:sec.Misc_VirtualSize]
        code[sec.VirtualAddress-first:sec.VirtualAddress-first+len(data)] = data
    relocs=[]
    for block in pe.DIRECTORY_ENTRY_BASERELOC:
        for reloc in block.entries:
            if reloc.type == 0: continue
            assert reloc.type == 3, reloc.type
            off=reloc.rva-first
            value,=struct.unpack_from("<I",code,off)
            target=value-pe.OPTIONAL_HEADER.ImageBase-first
            assert 0 <= target < len(code), hex(value)
            struct.pack_into("<I",code,off,target)
            relocs.append(off)
    export=next(s for s in pe.DIRECTORY_ENTRY_EXPORT.symbols if s.name==b"_DualWeaponCompose@36")
    rig_path=ROOT/"Inputs/DualWeaponAuthored/rigs/female-assassin-canonical.dwr3"
    rig=rig_path.read_bytes()
    grip=(ROOT/"Inputs/DualWeaponAuthored/grips/female-assassin-canonical.dwc2").read_bytes()
    payload=struct.pack("<"+"I"*len(relocs),*relocs)+code+rig+grip
    header=struct.pack("<8I",0x50435744,1,len(code),export.address-first,len(relocs),len(rig),len(grip),zlib.crc32(payload))
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_bytes(header+payload)
    report=dict(schema="dual_weapon_resource_payload/v1", compiler_dir=str(tool_dir),
                source=str(source.relative_to(ROOT)),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                native_basis_source=str(basis.relative_to(ROOT)),native_basis_sha256=hashlib.sha256(basis.read_bytes()).hexdigest(),
                native_basis_builder_sha256=hashlib.sha256((ROOT/'tools/build_dual_weapon_native_basis.py').read_bytes()).hexdigest(),
                pixel_profile_sha256=hashlib.sha256(pixel_profile.read_bytes()).hexdigest(),
                edge_profile_sha256=hashlib.sha256(edge_profile.read_bytes()).hexdigest(),
                male_profile_sha256=hashlib.sha256(male_profile.read_bytes()).hexdigest(),
                male_source_sha256=hashlib.sha256(male_source.read_bytes()).hexdigest(),
                male_builder_sha256=hashlib.sha256((ROOT/'tools/build_male_dual_weapon_profile.py').read_bytes()).hexdigest(),
                male_annotations_sha256=hashlib.sha256((ROOT/'Inputs/DualWeaponAuthored/grips/male-assassin-landmarks.json').read_bytes()).hexdigest(),
                male_seam_builder_sha256=hashlib.sha256((ROOT/'tools/male_weapon_seams.py').read_bytes()).hexdigest(),
                male_asset_builder_sha256=hashlib.sha256((ROOT/'tools/male_weapon_assets.py').read_bytes()).hexdigest(),
                male_asset_report_sha256=hashlib.sha256((ROOT/'docs/evidence/dual-weapon-male-missing-assets-20260907.json').read_bytes()).hexdigest(),
                pixel_annotations_sha256=hashlib.sha256((ROOT/'Inputs/DualWeaponAuthored/grips/female-assassin-pixel-landmarks.json').read_bytes()).hexdigest(),
                contact_measurement_only=measure_contacts,bytes=len(header+payload),sha256=hashlib.sha256(header+payload).hexdigest(),
                code_bytes=len(code),entry=export.address-first,relocations=relocs,
                rig_source=str(rig_path.relative_to(ROOT)),rig_sha256=hashlib.sha256(rig).hexdigest(),grip_sha256=hashlib.sha256(grip).hexdigest(),
                commands=[compile_args,link_args])
    report["extended_source_hashes"] = {
        name: hashlib.sha256((ROOT/name).read_bytes()).hexdigest()
        for name in [
            "CustomDLL/DualWeapon/female_dagger_compositor.h",
            "CustomDLL/DualWeapon/female_dagger_profile.h",
            "CustomDLL/DualWeapon/female_family_compositor.h",
            "CustomDLL/DualWeapon/female_family_profile.h",
            "CustomDLL/DualWeapon/male_axe_profile.h",
            "tools/female_weapon_assets.py", "tools/assassin_axe_assets.py",
            "tools/build_female_dagger_profile.py", "tools/build_female_family_profile.py",
            "tools/build_male_axe_profile.py", "tools/dual_weapon_legacy_assets.py",
            "Inputs/DualWeaponRuntime/legacy-support.dwls",
            "Inputs/DualWeaponRuntime/legacy-support.json",
            "Inputs/DualWeaponAuthored/reference/accepted-20260907.dwcp",
            "tools/dual_weapon_paths.py",
            "tools/dual_weapon_corpus.py",
            "tools/dual_weapon_geometry.py",
            "tools/dual_weapon_native.py",
            "tools/dual_weapon_data.py",
            "Inputs/DualWeaponAuthored/profiles/dual-weapon-male-hand-profile-20260907.json.gz",
            "Inputs/DualWeaponAuthored/profiles/female-dagger-profile-20260907.json.gz",
            "Inputs/DualWeaponAuthored/profiles/female-family-profile-20260907.json.gz",
            "Inputs/DualWeaponAuthored/profiles/male-axe-profile-20260907.json.gz",
            "docs/evidence/assassin-weapon-assets-20260907.json",
        ]
    }
    report["compatibility_grf_sha256"] = json.loads((ROOT/"docs/evidence/assassin-weapon-assets-20260907.json").read_text(encoding="utf8"))["grf_sha256"]
    report["placement_status"] = "2025-07-16 only; 24 mapped non-Drake views (1/2/6,31-47,58-61), five exact male and five exact female Assassin-family bodies. Missing native filenames require the 60-entry compatibility GRF, retained under the legacy dual_weapon_male_assets.grf name. Accepted Cross female17 and male20 poses are preserved. Added female bodies, dagger and axe images use explicit native frame, axis and local pixel-contact profiles; Shadow female generic sword is independent. Other off-only phases transfer native source frames. CPU execution and pixel geometry do not imply live GPU acceptance."
    output.with_suffix(".json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    print(json.dumps({k:report[k] for k in ["bytes","sha256","entry","code_bytes"]}))
if __name__=="__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tool-dir",type=Path,default=Path(r"C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\MSVC\14.51.36231\bin\Hostx64\x86"))
    parser.add_argument("--output",type=Path,default=ROOT/"Inputs/DualWeaponRuntime/compositor.dwcp")
    parser.add_argument('--measure-contacts', action='store_true', help='Offline palm-centered reference for contact generation; never install')
    args=parser.parse_args()
    build(args.tool_dir,args.output,args.measure_contacts)
