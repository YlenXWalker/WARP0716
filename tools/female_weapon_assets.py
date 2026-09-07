"""Supply missing female Assassin dagger names without replacing original pixels.

The native Assassin generic dagger owns action/frame/hidden-layer structure.
Thief SPRs are copied verbatim. Explicit hilt/tip landmarks register each
selected image to the native dagger, including the downward attack image.
"""
from pathlib import Path
import hashlib, json, math, struct, zlib
import numpy as np
from dual_weapon_corpus import Corpus
from dual_weapon_formats.act_reader import parse_act
from dual_weapon_formats.spr_reader import Spr
from dual_weapon_formats.grf_reader import GrfFile
from male_weapon_assets import layers_with_offsets, native_point, rotation

ROOT=Path(__file__).resolve().parents[1]
CLIENT=Path(r'D:\Programs\Games\Ragnarok\02_client\Banquet of Heroes')
OUT=ROOT/'Outputs/female_dagger_gap'
ASSETS=ROOT/'Inputs/DualWeaponAuthored/female-compat'
PREFIX='data/sprite/인간족/어세신/어세신_여_'
ITEMS={31:'1207',32:'1216',33:'1219'}
# Reviewed original female Thief images. Image 3 is a detached fragment, not
# the full downward Assassin blade: rotate image 0 for that native cell.
POINTS={31:{0:((9,28),(16,1)),1:((12,28),(5,1)),2:((27,10),(1,12))},
        32:{0:((10,26),(21,1)),1:((12,26),(1,1)),2:((25,12),(1,17))},
        33:{0:((11,25),(19,1)),1:((10,25),(2,1)),2:((26,12),(1,16))}}
IMAGE_MAP={0:0,1:1,2:2,3:0}

class FemaleCorpus(Corpus):
    def read(self,key):
        key=key.replace('\\','/').lower();p=ASSETS/key
        if p.is_file():
            b=p.read_bytes();self.sources[key]={'source':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};return b
        return super().read(key)

def sha(b):return hashlib.sha256(b).hexdigest()

def build():
    OUT.mkdir(parents=True,exist_ok=True);c=Corpus(CLIENT);assert not c.unreadable
    original=c.read(PREFIX+'단검.act');ga=parse_act(original);gs=Spr(c.read(PREFIX+'단검.spr'))
    ann=json.loads((ROOT/'Inputs/DualWeaponAuthored/grips/female-assassin-pixel-landmarks.json').read_text(encoding='utf8'))
    generic={int(k):v for k,v in ann['weapon_pixels']['1'].items()}
    rows=[];files={};resources={}
    for view,item in ITEMS.items():
        donor=f'data/sprite/인간족/도둑/도둑_여_{item}.spr';sb=c.read(donor);assert sb
        spr=Spr(sb);assert spr.n_indexed8==4 and len(spr.images)==4
        resources[view]={'donor':donor,'sha256':sha(sb),'points':POINTS[view]}
        ab=bytearray(original)
        for action,frame,li,pos in layers_with_offsets(original):
            l=ga['actions'][action].frames[frame].layers[li]
            if l.sprite_index<0:continue
            assert l.sprite_type==0 and l.scale_x==l.scale_y==1
            index=IMAGE_MAP[l.sprite_index];im=spr.images[index];gi=gs.images[l.sprite_index]
            grip,tip=POINTS[view][index];gp,gt=generic[l.sprite_index]
            desired=native_point(l,(gi.width,gi.height),gp)
            axis=native_point(l,(gi.width,gi.height),gt)-desired
            sa=np.array(tip)-grip
            # Include native +1 endpoints in the axis before quantizing ACT.
            sa=np.diag([(-im.width+1 if l.mirror else im.width+1)/im.width,(im.height+1)/im.height])@sa
            angle=int(round(math.degrees(math.atan2(axis[1],axis[0])-math.atan2(sa[1],sa[0]))))%360
            matrix=rotation(angle)@np.diag([(-im.width+1 if l.mirror else im.width+1)/im.width,(im.height+1)/im.height])
            center=desired-matrix@(np.array(grip)+.5-np.array([im.width,im.height])/2)
            x=int(round(center[0]-(0 if im.width%2 else .5)));y=int(round(center[1]-(0 if im.height%2 else .5)))
            struct.pack_into('<iii',ab,pos,x,y,index);struct.pack_into('<i',ab,pos+28,angle)
            if original[2]>=5:struct.pack_into('<ii',ab,pos+36,im.width,im.height)
            rows.append(dict(view=view,action=action,frame=frame,layer=li,image=index,x=x,y=y,angle=angle,generic_image=l.sprite_index))
        assert [len(a.frames) for a in parse_act(ab)['actions']]==[len(a.frames) for a in ga['actions']]
        for ext,data in [('spr',sb),('act',bytes(ab))]:
            name=PREFIX+item+'.'+ext;p=ASSETS/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);files[name]=data
    # All populated Shadow Cross originals except its female generic sword have
    # identical bytes to Assassin. Supply only absent names, including view47.
    for item in ITEMS.values():
        for ext in ('act','spr'):
            name=f'data/sprite/인간족/shadow_cross/shadow_cross_여_{item}.{ext}'
            data=files[PREFIX+item+'.'+ext];p=ASSETS/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);files[name]=data
    for sex in ('여','남'):
        for ext in ('act','spr'):
            name=f'data/sprite/인간족/shadow_cross/shadow_cross_{sex}_프리스트의검.{ext}'
            data=c.read(f'data/sprite/인간족/어세신/어세신_{sex}_프리스트의검.{ext}');assert data
            p=ASSETS/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);files[name]=data
    # Keep the registered legacy archive name. Its existing twelve male entries
    # are included byte-for-byte, so the embedded loader needs no new hook.
    male=GrfFile(ROOT/'Inputs/DualWeaponRuntime/dual_weapon_male_assets.grf')
    male_keys=[]
    for key in male.entries:
        if '_남_' in key and any(key.endswith('_'+i+'.'+e) for i in ITEMS.values() for e in ('act','spr')):
            files[key.replace('\\','/')]=male.read(key);male_keys.append(key)
    assert len(male_keys)==12;male.close()
    body=bytearray();table=bytearray()
    for key,data in sorted(files.items()):
        compressed=zlib.compress(data);offset=len(body);body.extend(compressed)
        table.extend(key.replace('/','\\').encode('cp949')+b'\0'+struct.pack('<IIIBI',len(compressed),len(compressed),len(data),1,offset))
    packed=zlib.compress(table);header=b'Master of Magic\0'+bytes(14)+struct.pack('<IIII',len(body),0,len(files)+7,0x200)
    grf=OUT/'dual_weapon_male_assets.grf';grf.write_bytes(header+body+struct.pack('<II',len(packed),len(table))+packed)
    check=GrfFile(grf);assert len(check.entries)==28 and all(check.read(k)==b for k,b in files.items());check.close()
    report=dict(schema='female_missing_weapon_assets/v1',resources=resources,source_resources=c.sources,
        grf_sha256=sha(grf.read_bytes()),files={k:{'bytes':len(v),'sha256':sha(v)} for k,v in files.items()},rows=rows,
        policy='Verbatim female Thief SPR; native female Assassin action/frame and hidden cells; authored hilt-axis registration. Legacy archive filename retained; twelve male entries unchanged.',live_acceptance=False)
    (ROOT/'docs/evidence/female-dagger-assets-20260907.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    c.close();print(json.dumps(dict(files=len(files),layers=len(rows),grf_sha256=report['grf_sha256'])))

if __name__=='__main__':build()
