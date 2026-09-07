"""Original Swordsman axe pixels on native Assassin action timelines.

Full and cut-edge landmarks are explicit; no texture resampling. This also
packages the existing dagger/Shadow-name corrections in the registered GRF.
"""
import json,math,struct,zlib,hashlib
from pathlib import Path
import numpy as np
from female_weapon_assets import FemaleCorpus,CLIENT,OUT,ASSETS,ROOT
from male_weapon_assets import layers_with_offsets,native_point,rotation
from dual_weapon_formats.act_reader import parse_act
from dual_weapon_formats.spr_reader import Spr
from dual_weapon_formats.grf_reader import GrfFile

ITEMS={58:'1354',59:'1357',60:'1363',61:'1366'}
POINTS={
'여':{
58:{0:((3,22),(15,3)),1:((24,24),(13,3)),4:((26,4),(10,15)),6:((26,4),(10,15)),7:((1,17),(17,1))},
59:{0:((4,18),(16,3)),1:((26,18),(16,3)),4:((32,4),(15,15)),6:((32,5),(10,9)),7:((25,24),(10,8))},
60:{0:((5,26),(20,7)),1:((27,22),(15,7)),4:((37,4),(24,17)),6:((40,6),(14,6)),7:((3,12),(17,1))},
61:{0:((4,31),(23,8)),1:((32,31),(14,8)),4:((34,3),(17,22)),6:((3,10),(17,10)),7:((33,23),(15,6))}},
'남':{
58:{0:((3,22),(15,3)),1:((24,24),(13,3)),4:((25,2),(9,18)),6:((2,2),(15,18))},
59:{0:((4,18),(16,3)),1:((28,19),(16,3)),2:((26,3),(9,20)),3:((3,3),(20,19))},
60:{0:((5,26),(20,7)),1:((27,22),(15,7)),2:((27,3),(12,23)),3:((4,4),(20,24))},
61:{0:((4,31),(22,8)),1:((31,31),(13,8)),2:((31,3),(10,23)),3:((2,3),(13,27))}}}

def image_map(sex,view):
    if sex=='여':return {0:0,1:1,2:6,3:4,4:4,5:1,6:7,7:7}
    return {0:1,1:0,2:1,3:6 if view==58 else 3,4:0,5:4 if view==58 else 2}

def build():
    c=FemaleCorpus(CLIENT);files={};rows=[];checks=[]
    for sex in ('여','남'):
        prefix=f'data/sprite/인간족/어세신/어세신_{sex}_';ab=c.read(prefix+'도끼.act');ga=parse_act(ab);gs=Spr(c.read(prefix+'도끼.spr'))
        an=json.loads((ROOT/'Inputs/DualWeaponAuthored/grips'/('female-assassin-pixel-landmarks.json' if sex=='여' else 'male-assassin-landmarks.json')).read_text(encoding='utf8'))
        generic={int(k):v for k,v in an['weapon_pixels']['6'].items()}
        if sex=='여':generic.update({2:((4,4),(1,1)),4:((20,3),(1,24)),6:((5,2),(1,10)),7:((5,2),(1,10))})
        for view,item in ITEMS.items():
            stem=f'data/sprite/인간족/검사/검사_{sex}_{item}';sb=c.read(stem+'.spr');assert sb
            spr=Spr(sb);data=bytearray(ab);mapping=image_map(sex,view)
            for index,pts in POINTS[sex][view].items():
                raw,w,h=spr.get_rgba(index,0);a=np.frombuffer(raw,dtype=np.uint8).reshape(h,w,4)[:,:,3];yy,xx=np.where(a>0);pixels=np.stack([xx,yy],axis=1)
                for label,pt in zip(('grip_or_cut','tip_or_head_axis'),pts):
                    assert 0<=pt[0]<w and 0<=pt[1]<h,(sex,view,index,label,pt,w,h)
                    distance=int(np.max(np.abs(pixels-np.array(pt)),axis=1).min());assert distance<=2,(sex,view,index,label,pt,distance)
                checks.append(dict(gender=sex,view=view,index=index,dimensions=[w,h],points=pts))
            for action,frame,li,pos in layers_with_offsets(ab):
                l=ga['actions'][action].frames[frame].layers[li]
                if l.sprite_index<0:continue
                index=mapping[l.sprite_index];im=spr.images[index];gi=gs.images[l.sprite_index];grip,tip=POINTS[sex][view][index];gp,gt=generic[l.sprite_index]
                target=native_point(l,(gi.width,gi.height),gp);axis=native_point(l,(gi.width,gi.height),gt)-target
                scale=np.diag([(-im.width+1 if l.mirror else im.width+1)/im.width,(im.height+1)/im.height]);sa=scale@(np.array(tip)-grip)
                angle=int(round(math.degrees(math.atan2(axis[1],axis[0])-math.atan2(sa[1],sa[0]))))%360
                center=target-rotation(angle)@scale@(np.array(grip)+.5-np.array([im.width,im.height])/2)
                x=int(round(center[0]-(0 if im.width%2 else .5)));y=int(round(center[1]-(0 if im.height%2 else .5)))
                struct.pack_into('<iii',data,pos,x,y,index);struct.pack_into('<i',data,pos+28,angle)
                if ab[2]>=5:struct.pack_into('<ii',data,pos+36,im.width,im.height)
                rows.append(dict(gender=sex,view=view,action=action,frame=frame,index=index,x=x,y=y,angle=angle,generic_image=l.sprite_index))
            for job in ('어세신','shadow_cross'):
                for ext,raw in [('act',bytes(data)),('spr',sb)]:
                    name=f'data/sprite/인간족/{job}/{job}_{sex}_{item}.{ext}';p=ASSETS/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw);files[name]=raw
    base=GrfFile(OUT/'dual_weapon_male_assets.grf')
    for k in base.entries:
        if not any(k.endswith('_'+i+'.'+e) for i in ITEMS.values() for e in ('act','spr')):files[k]=base.read(k)
    base.close();assert len(files)==60
    body=bytearray();table=bytearray()
    for k,b in sorted(files.items()):
        z=zlib.compress(b);offset=len(body);body.extend(z);table.extend(k.replace('/','\\').encode('cp949')+b'\0'+struct.pack('<IIIBI',len(z),len(z),len(b),1,offset))
    z=zlib.compress(table);grf=OUT/'dual_weapon_male_assets.grf';grf.write_bytes(b'Master of Magic\0'+bytes(14)+struct.pack('<IIII',len(body),0,len(files)+7,0x200)+body+struct.pack('<II',len(z),len(table))+z)
    g=GrfFile(grf);assert len(g.entries)==60 and all(g.read(k)==v for k,v in files.items());g.close()
    report=dict(schema='assassin_weapon_assets/v1',files={k:{'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)} for k,b in files.items()},sources=c.sources,rows=rows,landmarks=checks,grf_sha256=hashlib.sha256(grf.read_bytes()).hexdigest(),live_acceptance=False)
    (ROOT/'docs/evidence/assassin-weapon-assets-20260907.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8');print(json.dumps(dict(files=len(files),rows=len(rows),sha256=report['grf_sha256'])))

if __name__=='__main__':build()
