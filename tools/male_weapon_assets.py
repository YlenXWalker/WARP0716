"""Original male Thief dagger bitmaps on the native Assassin ACT layout.

The SPR bytes are copied verbatim. Only ACT image selection, integer center
and rotation change. The generated overlay supplies missing native filenames;
the equipment owner's exact requested-name guard stays enabled.
"""
from pathlib import Path
import hashlib,json,math,struct,zlib
import numpy as np
from dual_weapon_corpus import Corpus
from dual_weapon_formats.act_reader import parse_act
from dual_weapon_formats.spr_reader import Spr
from dual_weapon_formats.grf_reader import GrfFile

ROOT=Path(__file__).resolve().parents[1]
ASSETS=ROOT/'Inputs/DualWeaponAuthored/male-compat'
OUT=ROOT/'Outputs/dual_weapon_male_seam_fix'
CLIENT=Path(r'D:\Programs\Games\Ragnarok\02_client\Banquet of Heroes')
PREFIXES=['data/sprite/인간족/어세신/어세신_남_','data/sprite/인간족/shadow_cross/shadow_cross_남_']
NEW_POINTS={
31:{0:((30,8),(1,17)),1:((25,8),(1,2)),2:((10,4),(1,34)),3:((3,7),(30,2)),4:((24,7),(1,18)),5:((17,9),(1,15)),6:((26,5),(1,2))},
32:{0:((24,8),(1,19)),1:((24,8),(1,4)),2:((12,8),(1,30)),3:((3,6),(25,3)),4:((23,8),(1,19)),5:((21,12),(1,21)),6:((22,6),(1,3))},
33:{0:((27,10),(1,20)),1:((28,8),(1,3)),2:((13,7),(1,27)),3:((4,7),(30,6)),4:((24,8),(1,19)),5:((21,12),(1,21)),6:((26,7),(1,6))}}
ITEMS={31:'1207',32:'1216',33:'1219'}
GENERIC_POINTS={0:((8,18),(1,1)),1:((3,18),(9,1)),2:((8,5),(1,1)),3:((4,5),(23,16)),4:((2,9),(5,1)),5:((11,4),(1,21))}
# Full and perspective images are selected explicitly, not by unrelated frame
# counts from the donor job. The target retains all Assassin action lengths.
IMAGE_MAP={0:2,1:1,2:5,3:3,4:6,5:4}

class MaleCorpus(Corpus):
    def read(self,key):
        key=key.replace('\\','/').lower();p=ASSETS/key
        if p.is_file():
            b=p.read_bytes();self.sources[key]={'source':str(p),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()};return b
        return super().read(key)

def layers_with_offsets(data):
    """Offsets in an existing 2.4/2.5 ACT, preserving all other raw bytes."""
    minor,major=data[2:4];assert major==2 and minor in (4,5)
    pos=16;count=struct.unpack_from('<H',data,4)[0]
    for action in range(count):
        nf=struct.unpack_from('<I',data,pos)[0];pos+=4
        for frame in range(nf):
            pos+=32;nl=struct.unpack_from('<I',data,pos)[0];pos+=4
            for li in range(nl):
                yield action,frame,li,pos
                pos+=44 if minor==5 else 36
            pos+=4;na=struct.unpack_from('<I',data,pos)[0];pos+=4+16*na

def rotation(angle):
    a=math.radians(angle);return np.array([[math.cos(a),-math.sin(a)],[math.sin(a),math.cos(a)]])

def native_point(layer,dimensions,point):
    w,h=dimensions;mirror=layer.mirror
    center=np.array([layer.x+(0 if w%2 else .5),layer.y+(0 if h%2 else .5)])
    matrix=rotation(layer.rotation)@np.diag([(-w+1 if mirror else w+1)/w,(h+1)/h])
    return center+matrix@(np.array(point)+.5-np.array([w,h])/2)

def build():
    OUT.mkdir(parents=True,exist_ok=True);c=Corpus(CLIENT);assert not c.unreadable
    original=c.read(PREFIXES[0]+'단검.act');ga=parse_act(original);gs=Spr(c.read(PREFIXES[0]+'단검.spr'))
    offsets=list(layers_with_offsets(original));rows=[];files={}
    for view,item in ITEMS.items():
        donor=f'data/sprite/인간족/도둑/도둑_남_{item}.spr';sb=c.read(donor);assert sb
        spr=Spr(sb);ab=bytearray(original)
        for action,frame,li,pos in offsets:
            l=ga['actions'][action].frames[frame].layers[li]
            if l.sprite_index<0:continue
            assert l.sprite_type==0 and l.scale_x==l.scale_y==1 and l.sprite_index in IMAGE_MAP
            index=IMAGE_MAP[l.sprite_index];im=spr.images[index];gi=gs.images[l.sprite_index]
            grip,tip=NEW_POINTS[view][index];gp,gt=GENERIC_POINTS[l.sprite_index]
            desired=native_point(l,(gi.width,gi.height),gp)
            axis=native_point(l,(gi.width,gi.height),gt)-desired
            sa=np.array(tip)-grip
            if l.mirror:sa[0]*=-1
            angle=int(round(math.degrees(math.atan2(axis[1],axis[0])-math.atan2(sa[1],sa[0]))))%360
            matrix=rotation(angle)@np.diag([(-im.width+1 if l.mirror else im.width+1)/im.width,(im.height+1)/im.height])
            center=desired-matrix@(np.array(grip)+.5-np.array([im.width,im.height])/2)
            x=int(round(center[0]-(0 if im.width%2 else .5)));y=int(round(center[1]-(0 if im.height%2 else .5)))
            struct.pack_into('<iii',ab,pos,x,y,index);struct.pack_into('<i',ab,pos+28,angle)
            if original[2]>=5:struct.pack_into('<ii',ab,pos+36,im.width,im.height)
            rows.append(dict(view=view,action=action,frame=frame,image=index,x=x,y=y,angle=angle,generic_image=l.sprite_index))
        parsed=parse_act(ab);assert [len(a.frames) for a in parsed['actions']]==[len(a.frames) for a in ga['actions']]
        for prefix in PREFIXES:
            for ext,data in [('spr',sb),('act',bytes(ab))]:
                name=prefix+item+'.'+ext;p=ASSETS/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data);files[name]=data
        assert all(files[prefix+item+'.spr']==sb for prefix in PREFIXES)
    # Standard GRF 2.0, no encryption and no changes to the installed archives.
    body=bytearray();table=bytearray()
    for key,data in sorted(files.items()):
        compressed=zlib.compress(data);offset=len(body);body.extend(compressed)
        table.extend(key.replace('/','\\').encode('cp949')+b'\0'+struct.pack('<IIIBI',len(compressed),len(compressed),len(data),1,offset))
    packed=zlib.compress(table);header=b'Master of Magic\0'+bytes(14)+struct.pack('<IIII',len(body),0,len(files)+7,0x200)
    grf=OUT/'dual_weapon_male_assets.grf';grf.write_bytes(header+body+struct.pack('<II',len(packed),len(table))+packed)
    check=GrfFile(grf)
    assert len(check.entries)==len(files) and all(check.read(k)==b for k,b in files.items());check.close()
    report=dict(schema='male_missing_weapon_assets/v1',source_resources=c.sources,source_script_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        grf_sha256=hashlib.sha256(grf.read_bytes()).hexdigest(),files={k:{'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for k,v in files.items()},rows=rows,
        policy='Verbatim original male Thief SPR; native Assassin dagger ACT frame lengths and hidden cells; authored per-image hilt axes; no changed archive or disabled resource-name guard.',live_acceptance=False)
    (ROOT/'docs/evidence/dual-weapon-male-missing-assets-20260907.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    c.close();print(json.dumps({'files':len(files),'frames':len(rows),'grf_bytes':grf.stat().st_size,'sha256':report['grf_sha256']}))

if __name__=='__main__':build()
