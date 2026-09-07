"""Compile male generic-dual reference poses and per-original image contacts.

Landmark seeds below are explicit annotations of the original sprite atlases,
not inferred ACT origins. Generated records retain source identities and raw
native guide data. Negative native partial images are explicit hidden records.
"""
from __future__ import annotations
import hashlib,json,math,sys
from pathlib import Path
from dual_weapon_data import write_profile
from dual_weapon_corpus import weapon_views
ROOT=Path(__file__).resolve().parents[1]
sys.path.append(str(ROOT/'.venv/Lib/site-packages'));sys.dont_write_bytecode=True
import numpy as np
from PIL import Image,ImageDraw,ImageFont
from male_weapon_assets import MaleCorpus as Corpus, NEW_POINTS
from male_weapon_seams import endpoint_contact,authored_held_contact,HELD_FISTS,HELD_TERMINALS
from dual_weapon_formats.act_reader import parse_act
from dual_weapon_formats.spr_reader import Spr
from dual_weapon_native import NativeProjector,normalized_layer
from dual_weapon_geometry import affine,solve
from dual_weapon_geometry import penetration
from dual_weapon_paths import BODIES,FAMILIES,CLIENT,EXE

OUT=ROOT/'Outputs/dual_weapon_male_hand_reference'
INPUT=ROOT/'Inputs/DualWeaponAuthored/grips/male-assassin-landmarks.json'
HEADER=ROOT/'CustomDLL/DualWeapon/male_profile.h'
REPORT=ROOT/'Inputs/DualWeaponAuthored/profiles/dual-weapon-male-hand-profile-20260907.json.gz'
# Texel centers: grip then blade tip. Only complete, hilt-bearing source images.
WEAPON={
 1:{0:((8,18),(1,1)),2:((8,5),(1,1)),3:((4,5),(23,16)),5:((11,4),(1,21))},
 2:{0:((15,26),(1,1)),2:((4,3),(16,38)),3:((28,4),(1,14))},
 6:{0:((23,25),(2,2)),1:((3,22),(25,1)),2:((18,16),(9,3)),3:((3,3),(20,19)),4:((3,14),(11,3)),5:((18,3),(7,17))},
 34:{0:((13,23),(3,1)),1:((3,7),(21,3)),2:((20,3),(1,22))},
 35:{0:((17,18),(7,2)),1:((3,6),(18,6)),2:((18,4),(2,14))},
 36:{0:((8,21),(2,1)),2:((5,8),(23,2)),3:((18,4),(2,18))},
 37:{0:((3,34),(3,1)),1:((3,3),(36,2)),2:((30,3),(2,18))},
 38:{0:((9,17),(2,1)),2:((3,6),(19,2)),3:((12,4),(2,18)),6:((10,5),(2,18))},
 39:{0:((5,48),(8,1)),1:((2,5),(48,1)),2:((41,3),(2,25))},
 40:{0:((6,29),(11,1)),1:((3,7),(30,1)),2:((27,6),(2,15))},
 41:{0:((5,38),(5,1)),1:((2,5),(39,4)),2:((31,3),(2,20))},
 42:{0:((4,41),(5,1)),1:((5,7),(46,5)),2:((4,4),(13,35)),4:((42,8),(2,5))},
 43:{0:((5,42),(5,1)),1:((2,4),(43,4)),2:((28,5),(2,25))},
 44:{0:((5,43),(10,1)),2:((7,4),(50,1)),3:((5,7),(20,44))},
 45:{0:((6,46),(10,1)),2:((18,37),(3,2)),3:((5,7),(19,54)),5:((53,7),(2,2))},
 46:{0:((6,46),(10,1)),2:((18,37),(3,2)),3:((5,7),(19,54)),5:((53,7),(2,2))},
 47:{0:((5,43),(5,1)),1:((5,5),(46,5)),2:((32,6),(2,23)),5:((32,6),(2,23))}
}
WEAPON.update(NEW_POINTS)
# Partial artwork has no hilt: register its visible cut edge and blade tip.
# These are separate semantic landmarks, never treated as palm contacts.
PARTIAL={
 1:{1:((3,18),(9,1)),4:((2,9),(5,1))},2:{1:((3,16),(11,1))},
 34:{3:((7,13),(5,1))},35:{3:((6,13),(1,1))},36:{1:((3,21),(9,1))},
 37:{3:((2,11),(12,1))},38:{1:((3,18),(9,1)),4:((4,10),(4,1)),5:((4,9),(3,1))},
 39:{3:((2,19),(18,1))},40:{3:((3,18),(7,1))},41:{3:((2,14),(13,1))},
 42:{3:((2,13),(12,1))},43:{3:((2,11),(12,1))},44:{1:((1,16),(1,1))},
 45:{1:((2,27),(10,1)),4:((3,20),(27,1))},
 46:{1:((2,27),(10,1)),4:((3,20),(27,1))},
 47:{3:((2,3),(20,4)),4:((2,3),(24,4))}
}
# Male pair28 source bitmap annotations: reference role0 long blade, role1 short.
# None is genuinely absent in the combined bitmap; p denotes partial artwork.
GUIDES={
 0:[((14,36),(12,1),False),((8,40),(1,23),False)],
 1:[None,((3,16),(7,1),True)],
 2:[((15,25),(1,1),False),((20,35),(36,30),False)],
 3:[((15,25),(1,1),False),((22,35),(39,30),False)],
 4:[((21,16),(37,50),False),((2,5),(20,2),False)],
 5:[((27,16),(39,49),False),((2,5),(19,2),False)],
 6:[((26,12),(36,46),False),((2,5),(19,2),False)],
 7:[((22,41),(35,73),False),((5,9),(10,1),False)],
 8:[((22,36),(35,72),False),((5,9),(10,1),False)],
 9:[((26,14),(33,1),True),((2,25),(6,25),True)],
 10:[((26,14),(33,1),True),((2,25),(6,25),True)],
 11:[((27,10),(1,18),False),((46,2),(51,6),False)],
 12:[((28,12),(1,20),False),((44,3),(49,7),False)],
 13:[((28,5),(1,15),False),None],
 14:[((26,17),(1,26),False),((73,3),(82,4),False)],
 15:[((27,18),(1,25),False),((74,4),(83,8),False)]}

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    c=Corpus(CLIENT);assert not c.unreadable
    p=NativeProjector(EXE)
    def project(n,im,unit=1.):
        q=p.project(n,(im.width,im.height,0,0),unit,origin=(400,300))
        return [q[0]-300,q[1]-400,q[2]-300,q[3]-400,q[7]]
    coverage=weapon_views(c)
    decl={r['view']:r for r in coverage['views'] if r['view'] in WEAPON}
    cache={}
    def load(stem):
        if stem not in cache:
            ab,sb=c.read(stem+'.act'),c.read(stem+'.spr');assert ab and sb,stem
            act,spr=parse_act(ab),Spr(sb);ims={}
            for i in range(spr.n_indexed8):
                raw,w,h=spr.get_rgba(i,0);a=np.frombuffer(raw,dtype=np.uint8).reshape(h,w,4)
                ys,xs=np.where(a[:,:,3]>0);ims[i]=(spr.images[i],np.stack([xs,ys],axis=1).astype(float),Image.frombytes('RGBA',(w,h),raw))
            cache[stem]=(act,spr,ims)
        return cache[stem]
    def cell(stem,action,frame):
        a,s,ims=load(stem);ls=a['actions'][action].frames[frame].layers;assert len(ls)==1
        l=ls[0]
        if l.sprite_index<0:return l,None,None
        im,points,picture=ims[l.sprite_index];assert l.sprite_type==0 and l.scale_x==l.scale_y==1
        n=normalized_layer(l,im);return l,im,n
    # Every annotation is bounded and visibly associated with its handle/blade.
    annotation_checks=[]
    for view in WEAPON:
        points={**WEAPON[view],**PARTIAL.get(view,{})}
        stem=FAMILIES['assassin']+decl[view]['resource_stem'];a,s,ims=load(stem)
        for i,(grip,tip) in points.items():
            im,pixels,pic=ims[i]
            for label,pt in [('grip',grip),('tip',tip)]:
                assert 0<=pt[0]<im.width and 0<=pt[1]<im.height,(view,i,label,pt)
                distance=float(np.max(np.abs(pixels-np.array(pt)),axis=1).min())
                assert distance<=2,(view,i,label,pt,distance)
            annotation_checks.append(dict(view=view,index=i,dimensions=[im.width,im.height],grip=grip,tip=tip,partial=i in PARTIAL.get(view,{})))
    guide_stem=FAMILIES['assassin']+'단검_검';load(guide_stem)
    rows=[];body_rows=[];contacts=[];body_projection={}
    # Body fingerprints cover held and dual attack; aliases have independent pixels.
    for bi,(name,family) in enumerate(BODIES.values()):
        stem='data/sprite/인간족/몸통/남/'+name;load(stem)
        br=[]
        for phase,base,count in [(0,32,6),(1,88,8)]:
            for d in range(8):
                for f in range(count):
                    l,im,n=cell(stem,base+d,f)
                    br.append(dict(phase=phase,direction=d,frame=f,layer=n,dimensions=[im.width,im.height]))
        body_rows.append(dict(name=name,stem=stem,family=family,cells=br))
    for phase,base,count in [(0,32,6),(1,88,8)]:
        for d in range(8):
            for f in range(count):
                gl,gi,gn=cell(guide_stem,base+d,f)
                gg=project(gn,gi)
                go,gm=affine(gg,(gi.width,gi.height))
                for role,g in enumerate(GUIDES[gl.sprite_index]):
                    for view in WEAPON:
                        stem=FAMILIES['assassin']+decl[view]['resource_stem']
                        row=dict(phase=phase,direction=d,frame=f,role=role,view=view,guide_layer=gn,guide_dimensions=[gi.width,gi.height],visible=False)
                        if g is None:
                            row['reason']='generic_role_absent';rows.append(row);continue
                        anchor,tip,partial=g
                        source_action=(32+d) if phase==0 or f==0 else 80+d
                        source_frame=0 if phase==0 or f==0 else (2 if f in (1,2) or (role==1 and d in (0,1,6,7) and f<6) else 4)
                        sl,si,sn=cell(stem,source_action,source_frame)
                        if si is None and partial:
                            # Native single-held blanks do not mean the dual pose
                            # hides this blade. Use the actual same-direction rear
                            # attack fragment, with explicit cut-edge registration.
                            source_action,source_frame=80+d,2
                            sl,si,sn=cell(stem,source_action,source_frame)
                        if si is None:
                            row.update(reason='native_partial_source_hidden',source_action=source_action,source_frame=source_frame)
                            rows.append(row);continue
                        target=go+gm@(np.array(anchor)+.5)
                        axis=gm@(np.array(tip)-anchor);angle=math.degrees(math.atan2(axis[1],axis[0]))
                        source_points=WEAPON[view].get(sl.sprite_index)
                        grip,st=source_points or PARTIAL[view][sl.sprite_index]
                        sa=np.array(st)-grip
                        if gl.mirror:sa[0]*=-1
                        rotation=(angle-math.degrees(math.atan2(sa[1],sa[0]))+180)%360-180
                        mode='annotated_hilt_on_generic_trajectory' if source_points else 'partial_cut_edge_on_generic_trajectory'
                        mirror=gl.mirror
                        # Store the guide-relative contact, not a fixed screen XY.
                        uv=np.linalg.solve(gm,target-go)
                        row.update(visible=True,source_action=source_action,source_frame=source_frame,source_layer=sn,
                                   dimensions=[si.width,si.height],grip=grip,angle=rotation,mirror=mirror,
                                   guide_contact=uv.tolist(),mode=mode,partial=partial)
                        rows.append(row)
                        if phase or source_points is None:continue
                        for bi,body in enumerate(body_rows):
                            bl,bim,bn=cell(body['stem'],base+d,f)
                            def body_at(unit):
                                key=bi,d,f,unit
                                if key not in body_projection:body_projection[key]=affine(project(bn,bim,unit),(bim.width,bim.height))
                                return body_projection[key]
                            bo,bm=body_at(1.)
                            pixels=load(body['stem'])[2][bl.sprite_index][1]
                            desired=np.linalg.solve(bm,target-bo)-.5
                            w,h=si.width,si.height;a=math.radians(rotation)
                            wm=np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])@np.diag([-1. if mirror else 1.,1.])
                            wp=load(stem)[2][sl.sprite_index][1]
                            if d in (0,1,6,7):
                                bc,wc,detail=authored_held_contact(pixels,bm,wp,wm,bi,bl.sprite_index,role,view,sl.sprite_index)
                            else:
                                # Rear partial-body cases are retained verbatim;
                                # this revision corrects the two visible fists.
                                bc,wc,detail=endpoint_contact(pixels,desired,bm,wp,grip,st,wm)
                            contacts.append(dict(body=bi,view=view,direction=d,frame=f,role=role,
                                body_contact=bc.tolist(),weapon_contact=wc.tolist(),
                                generic_body_seed=desired.tolist(),clearance=[0.,0.],**detail))
    # Per-cell source/grip/trajectory data is shared by verified equal male weapon bytes.
    INPUT.parent.mkdir(parents=True,exist_ok=True)
    authored=dict(schema='male_assassin_landmarks/v1',method='Explicit full-hilt and partial-cut-edge atlas annotations; unchanged native generic pair28 attack trajectories. Front held directions 0/1/6/7 use authored top edges of each visible fist in body images 54-59 and explicit complete handle terminal texels. Rear held contacts and native attack fragments are retained from the previous profile. Anatomical annotations require live acceptance; opaque contact alone is not visual proof.',
                  weapon_pixels=WEAPON,partial_pixels=PARTIAL,generic_pair28=GUIDES,
                  held_fist_top_edges=HELD_FISTS,held_handle_terminals=HELD_TERMINALS,
                  resource_sha256={k:v['sha256'] for k,v in c.sources.items()},live_acceptance=False)
    INPUT.write_text(json.dumps(authored,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    report=dict(schema='male_dual_profile/v1',source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        annotations_sha256=hashlib.sha256(INPUT.read_bytes()).hexdigest(),native_exe_sha256=p.sha256,resources=c.sources,
        rows=rows,bodies=body_rows,contacts=contacts,annotation_checks=annotation_checks,live_acceptance=False)
    write_profile(REPORT, json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    def floats(v):return ','.join(f'{float(x):.9f}f' for x in v)
    def ints(v):return ','.join(map(str,v))
    h=['/* Generated male source/pose/body records; build_male_dual_weapon_profile.py. */','#ifndef DW_MALE_PROFILE_H','#define DW_MALE_PROFILE_H',
       'typedef struct { short x,y,index,mirror,width,height; } DWMFingerprint;',
       'typedef struct { unsigned short sa,sf,index,width,height; unsigned char visible,mirror,mode; short x,y,sourceMirror,sourceAngle; float angle,gx,gy,wx,wy; } DWMPose;',
       'typedef struct { float bx,by,wx,wy,dx,dy; } DWMContact;',
       f'#define DWM_VIEW_COUNT {len(WEAPON)}',
       'static const unsigned short DWM_VIEWS[DWM_VIEW_COUNT] = {'+ints(WEAPON)+'};',
       'static const char *const DWM_BODY_NAMES[5] = {']
    for b in body_rows:
        name=b['stem'].removeprefix('data/').replace('/','\\').encode('cp949')
        h.append('\t"'+''.join('\\x%02x'%v for v in name)+'",')
    h+=['};','static const DWMFingerprint DWM_BODIES[5][2][8][8] = {']
    for body in body_rows:
        lookup={(r['phase'],r['direction'],r['frame']):r for r in body['cells']};h.append('{')
        for ph in range(2):
            h.append('{')
            for d in range(8):
                h.append('{')
                for f in range(8):
                    r=lookup.get((ph,d,f));v=[*r['layer'][:4],*r['dimensions']] if r else [0,0,-1,0,0,0]
                    h.append('{'+ints(v)+'},')
                h.append('},')
            h.append('},')
        h.append('},')
    h+=['};','static const DWMFingerprint DWM_GUIDES[2][8][8] = {']
    lookup={(r['phase'],r['direction'],r['frame'],r['role'],r['view']):r for r in rows}
    for ph in range(2):
        h.append('{')
        for d in range(8):
            h.append('{')
            for f in range(8):
                r=lookup.get((ph,d,f,0,1));v=[*r['guide_layer'][:4],*r['guide_dimensions']] if r else [0,0,-1,0,0,0]
                h.append('{'+ints(v)+'},')
            h.append('},')
        h.append('},')
    h+=['};','static const DWMPose DWM_POSES[DWM_VIEW_COUNT][2][8][8][2] = {']
    for view in WEAPON:
        h.append('{')
        for ph in range(2):
            h.append('{')
            for d in range(8):
                h.append('{')
                for f in range(8):
                    h.append('{')
                    for role in (0,1):
                        r=lookup.get((ph,d,f,role,view))
                        if not r or not r['visible']:
                            if r and r.get('reason')=='native_partial_source_hidden':
                                h.append('{'+ints([r['source_action'],r['source_frame'],65535,0,0,0,0,2])+',0,0,0,0,0,0,0,0,0},')
                            else:h.append('{0},')
                            continue
                        n=r['source_layer'];im=r['dimensions'];v=[r['source_action'],r['source_frame'],n[2],*im,1,r['mirror'],int(r['mode'].startswith('partial_')),n[0],n[1],n[3],n[7]]
                        h.append('{'+ints(v)+','+floats([r['angle'],*r['guide_contact'],*(np.array(r['grip'])+.5)])+'},')
                    h.append('},')
                h.append('},')
            h.append('},')
        h.append('},')
    h+=['};','static const DWMContact DWM_CONTACTS[5][DWM_VIEW_COUNT][8][6][2] = {']
    cc={(r['body'],r['view'],r['direction'],r['frame'],r['role']):r for r in contacts}
    for bi in range(5):
        h.append('{')
        for view in WEAPON:
            h.append('{')
            for d in range(8):
                h.append('{')
                for f in range(6):
                    h.append('{')
                    for role in (0,1):
                        r=cc.get((bi,view,d,f,role));v=r['body_contact']+r['weapon_contact']+r['clearance'] if r else [0,0,0,0,0,0]
                        h.append('{'+floats(v)+'},')
                    h.append('},')
                h.append('},')
            h.append('},')
        h.append('},')
    h+=['};','#endif',''];HEADER.write_text('\n'.join(h),encoding='utf-8',newline='\n')
    c.close();print(json.dumps(dict(rows=len(rows),contacts=len(contacts),visible=sum(r['visible'] for r in rows),header_sha256=hashlib.sha256(HEADER.read_bytes()).hexdigest())))
if __name__=='__main__':main()
