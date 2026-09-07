"""Regression against the accepted payload and independent native pixel contacts."""
import sys,json,hashlib,math,functools
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT/'.venv/Lib/site-packages'));sys.dont_write_bytecode=True
import numpy as np
from verify_assassin_weapon_matrix import Resources,Fixture,PAYLOAD,EXE
from dual_weapon_data import load_profile,NAMES
from female_weapon_assets import FemaleCorpus,CLIENT,OUT
from dual_weapon_native import invoke_native
from dual_weapon_native import NativeProjector
from dual_weapon_geometry import affine
from dual_weapon_geometry import penetration
from dual_weapon_formats.spr_reader import Spr
BASE=ROOT/'Inputs/DualWeaponAuthored/reference/accepted-20260907.dwcp'
def main():
    def read(name):return load_profile(name) if name in NAMES else json.loads((ROOT/'docs/evidence'/name).read_text(encoding='utf8'))
    manifest=read('assassin-weapon-manifest-20260907.json');decl={v['view']:v for v in manifest['views'] if not v['excluded_drake']}
    female=read('female-family-profile-20260907.json');daggers=read('female-dagger-profile-20260907.json');male=read('male-axe-profile-20260907.json')
    fr={(r['key'],r['phase'],r['direction'],r['frame'],r['role']):r for r in female['rows']}
    fc={(r['body'],r['key'],r['direction'],r['frame'],r['role']):r for r in female['contacts']}
    dr={(r['view'],r['phase'],r['direction'],r['frame'],r['role']):r for r in daggers['rows']}
    dc={(r['view'],r['direction'],r['frame'],r['role']):r for r in daggers['contacts']}
    mr={(r['view'],r['phase'],r['direction'],r['frame'],r['role']):r for r in male['rows']}
    mc={(r['body'],r['view'],r['direction'],r['frame'],r['role']):r for r in male['contacts']}
    corpus=FemaleCorpus(CLIENT);p=NativeProjector(EXE);p.project=functools.lru_cache(maxsize=8192)(p.project)
    oldcases=newcases=0;maxold=maxcontact=maxpen=0.;summaries=[];cache={}
    for bi,b in enumerate(manifest['bodies']):
        res=Resources(corpus,b);m=Fixture(res,PAYLOAD);old=Fixture(res,BASE) if bi==2 or bi>=5 else None
        weapons={v:m.load(r['suffix'].lstrip('_')) for v,r in decl.items()}
        oldweapons={v:old.load(r['suffix'].lstrip('_')) for v,r in decl.items()} if old else {}
        def pictures(name,index):
            key=res.prefix if name!='@body' else res.body,name,index
            if key not in cache:
                raw,w,h=Spr(res.read(name+'.spr')).get_rgba(index,0);a=np.frombuffer(raw,dtype=np.uint8).reshape(h,w,4)[:,:,3];ys,xs=np.where(a>0);cache[key]=(np.stack([xs,ys],axis=1),(w,h))
            return cache[key]
        beforeold=oldcases;beforenew=newcases
        for v in decl:
            inherited=old is not None and v not in (58,59,60,61) and not(bi==2 and v in (31,32,33)) and not(bi==9 and v==47)
            added=not inherited and not(bi==9 and v==47)
            if not inherited and not added:continue
            partner=45 if v!=45 else 34
            for logical in (0,1):
                mv,ov=(v,partner) if logical==0 else (partner,v)
                stock,trail=m.equip(weapons[mv],weapons[ov],mv,ov,decl[mv]['type'],decl[ov]['type'])
                if inherited:os,ot=old.equip(oldweapons[mv],oldweapons[ov],mv,ov,decl[mv]['type'],decl[ov]['type'])
                for ph,n in ((0,6),(1,8)):
                    for d in range(8):
                        for f in range(n):
                            for unit,extra in ((1.,0),(2.3423,15),(2.3423,-90)):
                                actual=[];reference=[]
                                for channel,current in ((5,stock),(6,trail)):
                                    rr=invoke_native(m,p,current,(32 if ph==0 else 88)+d,f,unit,channel,extra)
                                    if rr:actual+=rr['draws']
                                    if inherited:
                                        rr=invoke_native(old,p,os if channel==5 else ot,(32 if ph==0 else 88)+d,f,unit,channel,extra)
                                        if rr:reference+=rr['draws']
                                if inherited:
                                    assert len(actual)==len(reference),(bi,v,ph,d,f)
                                    for a,e in zip(actual,reference):
                                        assert (a['resource'],a['image'])==(e['resource'],e['image'])
                                        error=max(abs(x-y) for x,y in zip(a['geometry'],e['geometry']));assert error<.001,(bi,v,ph,d,f,error);maxold=max(maxold,error)
                                    oldcases+=1;continue
                                main=(1 if d in (2,3,6,7) else 0) if bi<5 else 1-m.native_layer(m.body,(32 if ph==0 else 88)+d,f)[3]
                                role=1-main if logical else main
                                if bi>=5:r=mr[v,ph,d,f,role];c=mc.get((bi-5,v,d,f,role))
                                elif bi==2 and v in (31,32,33):r=dr[v,ph,d,f,role];c=dc.get((v,d,f,role))
                                else:
                                    key=10002 if bi==4 and v==2 else v;r=fr[key,ph,d,f,role];c=fc.get((bi,key,d,f,role))
                                selected=[a for a in actual if a['resource']==weapons[v]['name']]
                                if not r['visible']:assert not selected;continue
                                assert len(selected)==1
                                a=selected[0];wp,wd=pictures(a['resource'],a['image'][1]);wo,wm=affine(a['geometry'],wd)
                                assert abs((a['geometry'][4]-r['angle']-extra+180)%360-180)<.001
                                if ph==0:
                                    bl=m.native_layer(m.body,32+d,f);_,bd=pictures('@body',bl[2]);q=p.project(bl,(*bd,0,0),unit,origin=(960,495),actor_angle=extra);bo,bm=affine([*q[:4],q[7]],bd)
                                    error=float(np.linalg.norm(bo+bm@c['body_contact']-wo-wm@c['weapon_contact']))
                                    bp=np.array(c['hand_mask']);target_wp=np.array([c['weapon_pixel']]) if bi>=5 else wp
                                    overlap=penetration(bo+(bp+.5)@bm.T,bm,wo+(target_wp+.5)@wm.T,wm);maxpen=max(maxpen,overlap)
                                else:
                                    guide=m.load('단검_검');gl=m.native_layer(guide,88+d,f);_,gd=pictures(guide['name'],gl[2]);q=p.project(gl,(*gd,0,0),unit,origin=(960,495),actor_angle=extra);go,gm=affine([*q[:4],q[7]],gd)
                                    error=float(np.linalg.norm(go+gm@r['guide_contact']-wo-wm@(np.array(r['grip'])+.5)))
                                assert error<.001,(bi,v,ph,d,f,error);maxcontact=max(maxcontact,error);newcases+=1
        summaries.append(dict(body=bi,unchanged_cases=oldcases-beforeold,new_geometry_draws=newcases-beforenew));print(json.dumps(summaries[-1]),flush=True)
    assert maxpen<.001,maxpen
    result=dict(schema='assassin_weapon_geometry_regression/v1',payload_sha256=hashlib.sha256(PAYLOAD.read_bytes()).hexdigest(),baseline_sha256=hashlib.sha256(BASE.read_bytes()).hexdigest(),unchanged_cases=oldcases,new_geometry_draws=newcases,max_baseline_geometry_error=maxold,max_contact_or_trajectory_error=maxcontact,max_local_pixel_penetration=maxpen,bodies=summaries,live_acceptance=False,limits=['Female fist masks are local authored regions. Male axe contacts verify the explicit handle/fist terminal pixels.','CPU/native projection does not establish GPU occlusion or user visual acceptance.'])
    (ROOT/'docs/evidence/assassin-weapon-geometry-20260907.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf8');print(json.dumps(result))
if __name__=='__main__':main()
