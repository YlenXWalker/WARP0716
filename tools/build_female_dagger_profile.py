"""Measure only views31-33; freeze the seventeen-view female baseline.

Execute the accepted generic dagger compositor to obtain attack hilt paths,
image selection, mirroring, ordering and blade axes. Held contacts use the
existing reviewed female fist masks and opaque pixel separation. No new body
coordinates or attack-frame heuristics are introduced.
"""
import sys,json,math,hashlib
from pathlib import Path
from dual_weapon_data import write_profile
ROOT=Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT/'.venv/Lib/site-packages'));sys.dont_write_bytecode=True
import numpy as np
from female_weapon_assets import FemaleCorpus,CLIENT,OUT,PREFIX,POINTS,ITEMS,IMAGE_MAP
from dual_weapon_native import GripResources,GripMachine,INPUT,BODY
from dual_weapon_native import invoke_native
from dual_weapon_native import NativeProjector
from build_dual_weapon_native_basis import build
from dual_weapon_geometry import affine,solve
from dual_weapon_formats.spr_reader import Spr

HEADER=ROOT/'CustomDLL/DualWeapon/female_dagger_profile.h'
REPORT=ROOT/'Inputs/DualWeaponAuthored/profiles/female-dagger-profile-20260907.json.gz'
BASE=ROOT/'Inputs/DualWeaponAuthored/reference/accepted-20260907.dwcp'
EXE=CLIENT/'2025-07-16_Ragexe_175220998_clientinfo_patched.exe'

class FemaleResources(GripResources):
    def __init__(self,client=CLIENT):
        self.client=client;self.corpus=FemaleCorpus(client)
    def read(self,name):
        stem=BODY+name[len('@body'):] if name.startswith('@body') else PREFIX+name
        b=self.corpus.read(stem)
        if b is None:raise FileNotFoundError(stem)
        return b

def main():
    res=FemaleResources();m=GripMachine(res,BASE);p=NativeProjector(EXE)
    ann=json.loads(INPUT.read_text(encoding='utf8'));_,br=build(CLIENT)
    basis={(r['phase'],r['direction'],r['frame']):r for r in br['records']}
    generic=m.load('단검');pair=m.load('단검_검');weapons={v:m.load(n) for v,n in ITEMS.items()}
    stock,trail=m.equip_views(generic,generic,1,1,1,1)
    cache={};rows=[];contacts=[];guides=[]
    def pixels(resource,index):
        key=resource['name'],index
        if key not in cache:
            raw,w,h=Spr(res.read(resource['name']+'.spr')).get_rgba(index,0)
            alpha=np.frombuffer(raw,dtype=np.uint8).reshape(h,w,4)[:,:,3];ys,xs=np.where(alpha>0)
            cache[key]=(np.stack([xs,ys],axis=1).astype(float),(w,h))
        return cache[key]
    for ph,base,count in [(0,32,6),(1,88,8)]:
        for d in range(8):
            for f in range(count):
                action=base+d;b=basis[ph,d,f]
                result=[]
                for ch,current in [(5,stock),(6,trail)]:
                    r=invoke_native(m,p,current,action,f,1.,ch)
                    if r:
                        assert r['handled']==1;result+=r['draws']
                roles=sorted([role for role in (0,1) if not b['hands'][role]['hidden']],key=lambda role:(b['hands'][role]['order'],role if d not in (2,3,6,7) else 1-role))
                assert len(roles)==len(result)
                draws=dict(zip(roles,result))
                gl=m.native_layer(pair,action,f);_,gd=pixels(pair,gl[2]);q=p.project(gl,(*gd,0,0),origin=(960,495))
                go,gm=affine([*q[:4],q[7]],gd)
                guides.append(dict(phase=ph,direction=d,frame=f,layer=gl,dimensions=gd))
                bl=m.native_layer(m.body,action,f);bp,bd=pixels(m.body,bl[2]);q=p.project(bl,(*bd,0,0),origin=(960,495))
                bo,bm=affine([*q[:4],q[7]],bd)
                for view,weapon in weapons.items():
                    for role in (0,1):
                        ref=b['hands'][role];r=dict(view=view,phase=ph,direction=d,frame=f,role=role,visible=role in draws,order=ref['order'])
                        if not r['visible']:rows.append(r);continue
                        draw=draws[role];idx=draw['image'][1];_,dim=pixels(generic,idx)
                        ro,rm=affine(draw['geometry'],dim);gp,gt=ann['weapon_pixels']['1'][str(idx)]
                        target=ro+rm@(np.array(gp)+.5);axis=rm@(np.array(gt)-gp)
                        sa=(80 if ref['sourceAttack'] else 32)+d;sf=ref['sourceFrame']
                        sl=m.native_layer(weapon,sa,sf);wp,wd=pixels(weapon,sl[2]);assert sl[2]==IMAGE_MAP[idx]
                        grip,tip=POINTS[view][sl[2]];mirror=draw['geometry'][3]<draw['geometry'][1]
                        localaxis=np.array(tip)-grip
                        if mirror:localaxis[0]*=-1
                        angle=(math.degrees(math.atan2(axis[1],axis[0])-math.atan2(localaxis[1],localaxis[0]))+180)%360-180
                        uv=np.linalg.solve(gm,target-go)
                        r.update(source_action=sa,source_frame=sf,source_layer=sl,dimensions=wd,grip=grip,tip=tip,angle=angle,mirror=int(mirror),guide_contact=uv.tolist(),reference_geometry=draw['geometry'],reference_image=idx,reference_grip=gp,reference_tip=gt)
                        rows.append(r)
                        if ph:continue
                        palm=np.array(ann['body_pixels'][str(bl[2])][role]);local=bp[np.max(np.abs(bp-palm),axis=1)<=3];assert len(local)>3
                        a=math.radians(angle);wm=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])@np.diag([-1 if mirror else 1,1])
                        seed=bo+bm@(palm+.5);wo=seed-wm@(np.array(grip)+.5)
                        direction=wm@(wp.mean(axis=0)-grip);direction/=np.linalg.norm(direction)
                        contact,distance,detail=solve(bo+(local+.5)@bm.T,bm,wo+(wp+.5)@wm.T,wm,direction)
                        bc=np.linalg.solve(bm,contact-bo);wc=np.linalg.solve(wm,contact-direction*distance-wo)
                        assert distance<32
                        contacts.append(dict(view=view,direction=d,frame=f,role=role,body_contact=bc.tolist(),weapon_contact=wc.tolist(),hand_mask=local.tolist(),shift=distance,**detail))
    report=dict(schema='female_dagger_profile/v1',baseline_sha256=hashlib.sha256(BASE.read_bytes()).hexdigest(),native_exe_sha256=p.sha256,source_resources=res.corpus.sources,points=POINTS,rows=rows,contacts=contacts,guides=guides,live_acceptance=False)
    write_profile(REPORT, json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    ints=lambda v:','.join(str(int(x)) for x in v)
    floats=lambda v:','.join(f'{float(x):.9f}f' for x in v)
    h=['/* Generated by build_female_dagger_profile.py; views31-33 only. */','#ifndef DW_FEMALE_DAGGER_PROFILE_H','#define DW_FEMALE_DAGGER_PROFILE_H','static const DWMFingerprint DWF_GUIDES[2][8][8] = {']
    lookup={(r['phase'],r['direction'],r['frame']):r for r in guides}
    for ph in range(2):
        h.append('{')
        for d in range(8):
            h.append('{')
            for f in range(8):
                r=lookup.get((ph,d,f));h.append('{'+ints([*r['layer'][:4],*r['dimensions']] if r else [0,0,-1,0,0,0])+'},')
            h.append('},')
        h.append('},')
    h+=['};','static const DWMPose DWF_POSES[3][2][8][8][2] = {']
    lookup={(r['view'],r['phase'],r['direction'],r['frame'],r['role']):r for r in rows}
    for v in ITEMS:
        h.append('{')
        for ph in range(2):
            h.append('{')
            for d in range(8):
                h.append('{')
                for f in range(8):
                    h.append('{')
                    for role in (0,1):
                        r=lookup.get((v,ph,d,f,role))
                        if not r or not r['visible']:h.append('{0},');continue
                        n=r['source_layer'];values=[r['source_action'],r['source_frame'],n[2],*r['dimensions'],1,r['mirror'],0,n[0],n[1],n[3],n[7]]
                        h.append('{'+ints(values)+','+floats([r['angle'],*r['guide_contact'],*(np.array(r['grip'])+.5)])+'},')
                    h.append('},')
                h.append('},')
            h.append('},')
        h.append('},')
    h+=['};','static const DWMContact DWF_CONTACTS[3][8][6][2] = {']
    lookup={(r['view'],r['direction'],r['frame'],r['role']):r for r in contacts}
    for v in ITEMS:
        h.append('{')
        for d in range(8):
            h.append('{')
            for f in range(6):
                h.append('{')
                for role in (0,1):
                    r=lookup.get((v,d,f,role));h.append('{'+floats(r['body_contact']+r['weapon_contact']+[0,0] if r else [0]*6)+'},')
                h.append('},')
            h.append('},')
        h.append('},')
    h+=['};','#endif',''];HEADER.write_text('\n'.join(h),encoding='utf8')
    print(json.dumps(dict(rows=len(rows),visible=sum(r['visible'] for r in rows),contacts=len(contacts),max_shift=max(r['shift'] for r in contacts))))

if __name__=='__main__':main()
