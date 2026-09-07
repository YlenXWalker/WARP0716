"""Verify final PE protection, embedded archive dispatch and packaged resources."""
import sys,json,hashlib,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT/'.venv/Lib/site-packages'));sys.dont_write_bytecode=True
from verify_dual_weapon_page_protection import run
import dual_weapon_archive_loader as loader
from female_weapon_assets import FemaleCorpus,CLIENT
from dual_weapon_formats.grf_reader import GrfFile
from dual_weapon_formats.act_reader import parse_act
from dual_weapon_formats.spr_reader import Spr
from dual_weapon_native import NativeProjector,normalized_layer
from dual_weapon_paths import EXE

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,default=EXE)
    parser.add_argument('--grf',type=Path,default=ROOT/'Inputs/DualWeaponRuntime/dual_weapon_male_assets.grf')
    parser.add_argument('--report',type=Path,default=ROOT/'docs/evidence/assassin-weapon-final-pe-assets-20260907.json')
    args=parser.parse_args();exe=args.exe
    protection=run(exe,False)
    loader.ENTRY=0x181f5f0
    archives=loader.verify(exe.read_bytes(),loader.EXPECTED+['dual_weapon_male_assets.grf'])
    c=FemaleCorpus(CLIENT);g=GrfFile(args.grf)
    manifest=json.loads((ROOT/'docs/evidence/assassin-weapon-manifest-20260907.json').read_text(encoding='utf8'))
    entries=[];cells=0;projection=NativeProjector(exe);seen=set()
    for key in sorted(g.entries):
        data=g.read(key);assert data==c.read(key),key
        entries.append(dict(name=key,sha256=hashlib.sha256(data).hexdigest()))
        if not key.endswith('.act'):continue
        act=parse_act(data);spr=Spr(g.read(key[:-4]+'.spr'));assert len(act['actions'])==104
        for action in act['actions']:
            for frame in action.frames:
                for l in frame.layers:
                    if l.sprite_index<0:continue
                    assert l.sprite_type==0 and 0<=l.sprite_index<len(spr.images)
                    im=spr.images[l.sprite_index];cell=normalized_layer(l,im);fingerprint=tuple(cell)+(im.width,im.height)
                    if fingerprint not in seen:
                        projection.project(cell,(im.width,im.height,0,0));seen.add(fingerprint)
                    cells+=1
    assert len(entries)==60
    available=0
    for row in manifest['resources']:
        if row['excluded_drake']:continue
        for ext in ('.act','.spr'):
            key=row['stem']+ext
            packaged=g.read(key) or super(FemaleCorpus,c).read(key)
            assert packaged==c.read(key) and packaged,key
        available+=1
    assert available==96
    result=dict(schema='assassin_weapon_final_pe_assets/v1',pe_sha256=hashlib.sha256(exe.read_bytes()).hexdigest(),
        grf_sha256=hashlib.sha256(args.grf.read_bytes()).hexdigest(),
        protection=protection,embedded_loader=archives,packaged_entries=entries,
        required_resource_pairs=available,adapted_visible_act_cells=cells,unique_native_cell_projections=len(seen),live_acceptance=False)
    args.report.write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    g.close();c.close()
    print(json.dumps(dict(required_pairs=available,entries=len(entries),adapted_cells=cells,native_projections=len(seen),protection_passed=True,embedded_loader_passed=True)))
if __name__=='__main__':main()
