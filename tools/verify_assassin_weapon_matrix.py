"""Execute every ordered weapon pair on ten bodies using native input packets."""
import sys,json,hashlib,argparse,functools
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT/'.venv/Lib/site-packages'));sys.dont_write_bytecode=True
from dual_weapon_data import load_profile,NAMES
from female_weapon_assets import FemaleCorpus,CLIENT,OUT
from dual_weapon_native import MaleMachine
from dual_weapon_native import invoke_native
from dual_weapon_native import NativeProjector
from build_dual_weapon_native_basis import build
PAYLOAD=ROOT/'Inputs/DualWeaponRuntime/compositor.dwcp'
EXE=CLIENT/'2025-07-16_Ragexe_175220998_clientinfo_patched.exe'
class Resources:
    def __init__(self,corpus,body):
        self.corpus=corpus;self.body=body['stem'];self.gender=int(body['gender']=='남')
        job='shadow_cross' if body['job']=='shadow_cross' else '어세신'
        self.prefix=f'data/sprite/인간족/{job}/{job}_{body["gender"]}_'
    def read(self,name):
        key=self.body+name[len('@body'):] if name.startswith('@body') else self.prefix+name
        b=self.corpus.read(key)
        if b is None:raise FileNotFoundError(key)
        return b
class Fixture(MaleMachine):
    def equip(self,*args,**kwargs):
        result=super().equip(*args,**kwargs);self.w(self.row+56,self.resources.gender);return result
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--body',type=int,choices=range(10));ap.add_argument('--quick',action='store_true');args=ap.parse_args()
    def read(name):return load_profile(name) if name in NAMES else json.loads((ROOT/'docs/evidence'/name).read_text(encoding='utf8'))
    manifest=read('assassin-weapon-manifest-20260907.json')
    decl={v['view']:v for v in manifest['views'] if not v['excluded_drake']};assert set(decl)=={1,2,6,*range(31,48),58,59,60,61}
    female=read('female-family-profile-20260907.json');daggers=read('female-dagger-profile-20260907.json')
    male=read('dual-weapon-male-hand-profile-20260907.json');axes=read('male-axe-profile-20260907.json')
    fr={(r['key'],r['phase'],r['direction'],r['frame'],r['role']):r for r in female['rows']}
    dr={(r['view'],r['phase'],r['direction'],r['frame'],r['role']):r for r in daggers['rows']}
    mr={(r['view'],r['phase'],r['direction'],r['frame'],r['role']):r for r in male['rows']+axes['rows']}
    _,br=build(CLIENT);basis={(r['phase'],r['direction'],r['frame']):r for r in br['records']}
    corpus=FemaleCorpus(CLIENT);p=NativeProjector(EXE);p.project=functools.lru_cache(maxsize=8192)(p.project)
    cases=draws=offcases=0;matrix=[];guards=[]
    for bi,body in enumerate(manifest['bodies']):
        if args.body is not None and args.body!=bi:continue
        res=Resources(corpus,body);m=Fixture(res,PAYLOAD);weapons={v:m.load(r['suffix'].lstrip('_')) for v,r in decl.items()};count=0
        def expected(mv,ov,ph,d,f,off=False):
            bl=m.native_layer(m.body,(32 if ph==0 else 88)+d,f)
            main=(1-bl[3]) if res.gender else (1 if d in (2,3,6,7) else 0);out=[]
            for logical,v in enumerate((mv,ov)):
                if off and logical==0:continue
                role=1-main if logical else main
                if res.gender:r=mr[v,ph,d,f,role]
                elif bi==2 and v in (31,32,33):r=dr[v,ph,d,f,role]
                elif bi==2 and v<58:
                    b=basis[ph,d,f]['hands'][role]
                    if b['hidden']:continue
                    sa=(80 if b['sourceAttack'] else 32)+d;sf=b['sourceFrame']
                    r=dict(visible=True,source_layer=m.native_layer(weapons[v],sa,sf),order=b['order'])
                else:r=fr[10002 if bi==4 and v==2 else v,ph,d,f,role]
                if not r['visible']:continue
                out.append((role if res.gender else r['order'],logical,weapons[v]['name'],(0,r['source_layer'][2])))
            out.sort();return [(n,im) for order,logical,n,im in out]
        def check(mv,ov,ph,d,f,stock,trail,off=False):
            nonlocal count,cases,draws,offcases
            actual=[]
            for channel,current in ((5,stock),(6,trail)):
                r=invoke_native(m,p,current,(32 if ph==0 else 88)+d,f,1.,channel)
                if r:
                    if res.gender and channel==6:
                        assert r['handled']==0 and not r['draws'];continue
                    assert r['handled']==1,('unexpected_generic_fallback',bi,mv,ov,ph,d,f,channel,r)
                    actual.extend((x['resource'],tuple(x['image'])) for x in r['draws'])
            wanted=expected(mv,ov,ph,d,f,off)
            assert actual==wanted,('wrong_original_image_or_slot',bi,mv,ov,ph,d,f,actual,wanted)
            cases+=1;count+=1;draws+=len(actual);offcases+=off
        for mv in decl:
            for ov in decl:
                stock,trail=m.equip(weapons[mv],weapons[ov],mv,ov,decl[mv]['type'],decl[ov]['type'])
                for ph,n in ((0,6),(1,8)):
                    for d in range(8):
                        for f in ([0] if args.quick else range(n)):check(mv,ov,ph,d,f,stock,trail)
            carrier={1:'단검',2:'검',6:'도끼'}[decl[mv]['type']]
            stock,trail=m.equip(weapons[34],weapons[mv],34,mv,1,decl[mv]['type'],carrier,True)
            for d in range(8):
                for f in range(6):check(34,mv,0,d,f,stock,trail,True)
        pairs={(1,1):'단검_단검',(2,2):'검_검',(6,6):'도끼_도끼',(1,2):'단검_검',(1,6):'단검_도끼',(2,6):'검_도끼'}
        for v in decl:
            for partner in (1,2,6):
                for mv,ov in ((v,partner),(partner,v)):
                    carrier=pairs[tuple(sorted((decl[mv]['type'],decl[ov]['type'])))]
                    stock,trail=m.equip(weapons[mv],weapons[ov],mv,ov,decl[mv]['type'],decl[ov]['type'],carrier)
                    for d in range(8):check(mv,ov,0,d,0,stock,trail)
        stock,_=m.equip(weapons[33],weapons[45],33,45,1,2)
        for view in (200,600,500,10002):
            m.w(m.viewrow,view);r=invoke_native(m,p,stock,32,0,1.,5)
            assert r['handled']==0 and not r['draws'];guards.append([bi,'unprofiled_view',view])
        matrix.append(dict(body=bi,job=body['job'],gender=body['gender'],views=list(decl),cases=count,all_available_originals_handled=True))
        print(json.dumps({'body':bi,'cases':count,'total_draws':draws}),flush=True)
    report=dict(schema='assassin_weapon_execution_matrix/v1',quick=args.quick,payload_sha256=hashlib.sha256(PAYLOAD.read_bytes()).hexdigest(),cases=cases,draws=draws,off_only_cases=offcases,matrix=matrix,guards=guards,live_acceptance=False)
    suffix='all' if args.body is None else str(args.body)
    path=ROOT/f'docs/evidence/assassin-weapon-matrix-{suffix}-20260907.json'
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(dict(cases=cases,draws=draws,report=str(path))))
if __name__=='__main__':main()
