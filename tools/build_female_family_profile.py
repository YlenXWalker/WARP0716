"""Independent female family bodies; preserve the accepted Cross path.

Per-view poses are measured from the frozen compiled female baseline. Body
palms below were inspected on each original unmirrored held SPR image.
"""
import sys,json,math,hashlib
from pathlib import Path
from dual_weapon_data import write_profile
from dual_weapon_corpus import weapon_views
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT/'.venv/Lib/site-packages'));sys.dont_write_bytecode=True
import numpy as np
from female_weapon_assets import FemaleCorpus,CLIENT,OUT,PREFIX,POINTS,ITEMS
from assassin_axe_assets import POINTS as AXE_POINTS, ITEMS as AXE_ITEMS
from build_female_dagger_profile import FemaleResources,BASE,EXE
from dual_weapon_native import GripMachine,INPUT
from dual_weapon_native import invoke_native
from dual_weapon_native import NativeProjector,normalized_layer
from build_dual_weapon_native_basis import build
from dual_weapon_geometry import affine,solve
from dual_weapon_formats.spr_reader import Spr
from dual_weapon_formats.act_reader import parse_act

JOBS=['어세신','어세신_h','어쌔신크로스','길로틴크로스','shadow_cross']
PALMS={
0:[[[6,23],[40,22]],[[6,22],[40,23]],[[5,21],[39,24]],[[6,18],[40,25]],[[7,23],[41,24]],[[6,24],[40,24]],[[9,17],[30,22]],[[9,17],[31,22]],[[9,17],[31,23]],[[8,16],[31,22]],[[9,17],[30,25]],[[9,18],[31,25]]],
3:[[[6,25],[42,24]],[[5,24],[41,25]],[[4,23],[40,26]],[[5,22],[41,26]],[[6,24],[42,25]],[[6,25],[42,25]],[[8,22],[32,27]],[[9,22],[33,27]],[[9,22],[33,28]],[[8,21],[33,27]],[[9,22],[32,30]],[[9,23],[33,30]]],
4:[[[6,23],[40,24]],[[6,22],[40,25]],[[6,21],[40,26]],[[7,20],[41,26]],[[7,22],[41,25]],[[7,23],[41,25]],[[9,20],[36,26]],[[8,20],[35,26]],[[8,20],[35,27]],[[9,19],[36,26]],[[10,20],[36,28]],[[10,21],[36,28]]]}
PALMS[1]=PALMS[0]
SHADOW_SWORD={0:((11,27),(31,1)),1:((17,33),(1,1)),2:((25,9),(1,31)),3:((38,10),(1,26)),4:((27,11),(1,1)),5:((29,15),(1,1))}
REPORT=ROOT/'Inputs/DualWeaponAuthored/profiles/female-family-profile-20260907.json.gz'
HEADER=ROOT/'CustomDLL/DualWeapon/female_family_profile.h'

def main():
    res=FemaleResources();m=GripMachine(res,BASE);p=NativeProjector(EXE);ann=json.loads(INPUT.read_text(encoding='utf8'))
    PALMS[2]=[ann['body_pixels'][str(i)] for i in range(54,66)]
    _,br=build(CLIENT);basis={(r['phase'],r['direction'],r['frame']):r for r in br['records']}
    cov=weapon_views(res.corpus)
    decl={r['view']:r for r in cov['views'] if r['view'] in [1,2,6,*range(31,48),*AXE_ITEMS]}
    keys=list(decl)+[10002];bodyrows=[];rows=[];contacts=[];cache={}
    def load(stem):
        if stem not in cache:
            ab,sb=res.corpus.read(stem+'.act'),res.corpus.read(stem+'.spr');assert ab and sb,stem
            act,spr=parse_act(ab),Spr(sb);ims={}
            for i in range(spr.n_indexed8):
                raw,w,h=spr.get_rgba(i,0);a=np.frombuffer(raw,dtype=np.uint8).reshape(h,w,4)[:,:,3];ys,xs=np.where(a>0);ims[i]=(spr.images[i],np.stack([xs,ys],axis=1).astype(float))
            cache[stem]=(act,spr,ims)
        return cache[stem]
    def cell(stem,action,frame):
        act,spr,ims=load(stem);ls=act['actions'][action].frames[frame].layers;assert len(ls)==1
        l=ls[0];im,px=ims[l.sprite_index];return l,im,normalized_layer(l,im),px
    def project(n,im):
        q=p.project(n,(im.width,im.height,0,0),origin=(960,495));return affine([*q[:4],q[7]],(im.width,im.height))
    for bi,job in enumerate(JOBS):
        stem=f'data/sprite/인간족/몸통/여/{job}_여';cells=[]
        for ph,base,count in [(0,32,6),(1,88,8)]:
            for d in range(8):
                for f in range(count):
                    l,im,n,px=cell(stem,base+d,f);cells.append(dict(phase=ph,direction=d,frame=f,layer=n,dimensions=[im.width,im.height]))
        bodyrows.append(dict(stem=stem,job=job,cells=cells))
    # Assassin and high Assassin have identical pose geometry; verify the
    # reviewed local palm masks against both bodies independently below.
    for key in keys:
        v=2 if key==10002 else key;refv=1 if v in ITEMS else 6 if v in AXE_ITEMS else v
        weapon=m.load(decl[refv]['resource_stem']);stock,trail=m.equip_views(weapon,weapon,decl[refv]['base_type'],decl[refv]['base_type'],refv,refv)
        stem=('data/sprite/인간족/shadow_cross/shadow_cross_여_검' if key==10002 else PREFIX+decl[v]['resource_stem'])
        for ph,base,count in [(0,32,6),(1,88,8)]:
            for d in range(8):
                for f in range(count):
                    action=base+d;b=basis[ph,d,f];result=[]
                    for ch,current in [(5,stock),(6,trail)]:
                        z=invoke_native(m,p,current,action,f,1.,ch)
                        if z:assert z['handled']==1;result+=z['draws']
                    roles=sorted([role for role in (0,1) if not b['hands'][role]['hidden']],key=lambda role:(b['hands'][role]['order'],role if d not in (2,3,6,7) else 1-role));assert len(roles)==len(result)
                    draws=dict(zip(roles,result));gl,gi,gn,_=cell(PREFIX+'단검_검',action,f);go,gm=project(gn,gi)
                    for role in (0,1):
                        ref=b['hands'][role];r=dict(key=key,view=v,phase=ph,direction=d,frame=f,role=role,visible=role in draws,order=ref['order'],guide_layer=gn,guide_dimensions=[gi.width,gi.height])
                        if not r['visible']:rows.append(r);continue
                        draw=draws[role];idx=draw['image'][1];ri=weapon['images'][0,idx][1];ro,rm=affine(draw['geometry'],(ri.width,ri.height));gp,gt=ann['weapon_pixels'][str(refv)][str(idx)]
                        target=ro+rm@(np.array(gp)+.5);axis=rm@(np.array(gt)-gp)
                        sa=(80 if ref['sourceAttack'] else 32)+d;sf=ref['sourceFrame'];sl,si,sn,wp=cell(stem,sa,sf)
                        points=SHADOW_SWORD if key==10002 else POINTS[v] if v in ITEMS else AXE_POINTS['여'][v] if v in AXE_ITEMS else {int(k):vv for k,vv in ann['weapon_pixels'][str(v)].items()}
                        grip,tip=points[sl.sprite_index];mirror=int(draw['geometry'][3]<draw['geometry'][1]);angle=draw['geometry'][4]
                        if key==10002 or v in ITEMS or v in AXE_ITEMS:
                            local=np.array(tip)-grip
                            if mirror:local[0]*=-1
                            angle=(math.degrees(math.atan2(axis[1],axis[0])-math.atan2(local[1],local[0]))+180)%360-180
                        r.update(source_action=sa,source_frame=sf,source_layer=sn,dimensions=[si.width,si.height],grip=grip,tip=tip,angle=angle,mirror=mirror,guide_contact=np.linalg.solve(gm,target-go).tolist(),reference_geometry=draw['geometry'])
                        rows.append(r)
                        if ph:continue
                        for bi,body in enumerate(bodyrows):
                            if (key==10002 and bi!=4) or (key==2 and bi==4):continue
                            bl,bim,bn,bp=cell(body['stem'],action,f);bo,bm=project(bn,bim);palm=np.array(PALMS[bi][bl.sprite_index-54][role])
                            local=bp[np.max(np.abs(bp-palm),axis=1)<=3];assert len(local)>3,(bi,bl.sprite_index,role,palm)
                            rad=math.radians(angle);wm=np.array([[math.cos(rad),-math.sin(rad)],[math.sin(rad),math.cos(rad)]])@np.diag([-1 if mirror else 1,1]);seed=bo+bm@(palm+.5);wo=seed-wm@(np.array(grip)+.5)
                            direction=wm@(wp.mean(axis=0)-grip);direction/=np.linalg.norm(direction)
                            contact,distance,detail=solve(bo+(local+.5)@bm.T,bm,wo+(wp+.5)@wm.T,wm,direction)
                            assert distance<40,(bi,v,d,f,role,distance)
                            contacts.append(dict(body=bi,key=key,view=v,direction=d,frame=f,role=role,body_contact=np.linalg.solve(bm,contact-bo).tolist(),weapon_contact=np.linalg.solve(wm,contact-direction*distance-wo).tolist(),hand_mask=local.tolist(),shift=distance,**detail))
        print(json.dumps(dict(profiled_key=key)),flush=True)
    data=dict(schema='female_family_profile/v1',keys=keys,bodies=bodyrows,rows=rows,contacts=contacts,palms=PALMS,shadow_sword_points=SHADOW_SWORD,sources=res.corpus.sources,baseline_sha256=hashlib.sha256(BASE.read_bytes()).hexdigest(),live_acceptance=False)
    write_profile(REPORT, json.dumps(data,indent=2,ensure_ascii=False)+'\n',encoding='utf8');emit(data)
    print(json.dumps(dict(rows=len(rows),contacts=len(contacts),header_bytes=HEADER.stat().st_size)))

def emit(data, header=HEADER, prefix='DWFF'):
    ints=lambda v:','.join(str(int(x)) for x in v);floats=lambda v:','.join(f'{float(x):.9f}f' for x in v)
    h=['/* Generated independent female-family profiles. */','#ifndef DW_FEMALE_FAMILY_PROFILE_H','#define DW_FEMALE_FAMILY_PROFILE_H',f'#define DWFF_COUNT {len(data["keys"])}','static const unsigned short DWFF_KEYS[DWFF_COUNT] = {'+ints(data['keys'])+'};','static const char *const DWFF_NAMES[5] = {']
    for b in data['bodies']:h.append('"'+''.join('\\x%02x'%x for x in b['stem'].removeprefix('data/').replace('/','\\').encode('cp949'))+'",')
    h+=['};','static const DWMFingerprint DWFF_BODIES[5][2][8][8] = {']
    for b in data['bodies']:
        look={(r['phase'],r['direction'],r['frame']):r for r in b['cells']};h.append('{')
        for ph in range(2):
            h.append('{')
            for d in range(8):
                h.append('{')
                for f in range(8):
                    r=look.get((ph,d,f));h.append('{'+ints([*r['layer'][:4],*r['dimensions']] if r else [0,0,-1,0,0,0])+'},')
                h.append('},')
            h.append('},')
        h.append('},')
    h+=['};','static const DWMPose DWFF_POSES[DWFF_COUNT][2][8][8][2] = {'];look={(r['key'],r['phase'],r['direction'],r['frame'],r['role']):r for r in data['rows']}
    for key in data['keys']:
        h.append('{')
        for ph in range(2):
            h.append('{')
            for d in range(8):
                h.append('{')
                for f in range(8):
                    h.append('{')
                    for role in (0,1):
                        r=look.get((key,ph,d,f,role))
                        if not r or not r['visible']:h.append('{0},');continue
                        n=r['source_layer'];h.append('{'+ints([r['source_action'],r['source_frame'],n[2],*r['dimensions'],1,r['mirror'],0,n[0],n[1],n[3],n[7]])+','+floats([r['angle'],*r['guide_contact'],*(np.array(r['grip'])+.5)])+'},')
                    h.append('},')
                h.append('},')
            h.append('},')
        h.append('},')
    h+=['};','static const DWMContact DWFF_CONTACTS[5][DWFF_COUNT][8][6][2] = {'];look={(r['body'],r['key'],r['direction'],r['frame'],r['role']):r for r in data['contacts']}
    for bi in range(5):
        h.append('{')
        for key in data['keys']:
            h.append('{')
            for d in range(8):
                h.append('{')
                for f in range(6):
                    h.append('{')
                    for role in (0,1):
                        r=look.get((bi,key,d,f,role));h.append('{'+floats(r['body_contact']+r['weapon_contact']+[0,0] if r else [0]*6)+'},')
                    h.append('},')
                h.append('},')
            h.append('},')
        h.append('},')
    h+=['};','#endif',''];header.write_text('\n'.join(h).replace('DWFF',prefix).replace('DW_FEMALE_FAMILY_PROFILE_H',prefix+'_PROFILE_H'),encoding='utf8')

if __name__=='__main__':main()
