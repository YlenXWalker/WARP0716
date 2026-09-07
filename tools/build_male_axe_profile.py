"""Register original axe donor hilt axes to the verified male generic axe path."""
import sys,json,math,hashlib
from pathlib import Path
from dual_weapon_data import write_profile
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT/'.venv/Lib/site-packages'));sys.dont_write_bytecode=True
import numpy as np
from assassin_axe_assets import POINTS,ITEMS,image_map
from dual_weapon_data import load_profile
from female_weapon_assets import FemaleCorpus,CLIENT
from build_female_family_profile import emit
from dual_weapon_formats.spr_reader import Spr
from dual_weapon_formats.act_reader import parse_act
from dual_weapon_native import NativeProjector,normalized_layer
from dual_weapon_geometry import affine
from male_weapon_seams import endpoint_contact,HELD_FISTS

TERMINALS={58:(24,27),59:(29,20),60:(28,25),61:(31,34)}
REPORT=ROOT/'Inputs/DualWeaponAuthored/profiles/male-axe-profile-20260907.json.gz'
HEADER=ROOT/'CustomDLL/DualWeapon/male_axe_profile.h'
def main():
    c=FemaleCorpus(CLIENT);data=load_profile('dual-weapon-male-hand-profile-20260907.json')
    an=json.loads((ROOT/'Inputs/DualWeaponAuthored/grips/male-assassin-landmarks.json').read_text(encoding='utf8'))
    p=NativeProjector(CLIENT/'2025-07-16_Ragexe_175220998_clientinfo_patched.exe')
    rows=[];contacts=[];cache={};oldcontacts={(r['body'],r['direction'],r['frame'],r['role']):r for r in data['contacts'] if r['view']==6}
    def load(stem):
        if stem not in cache:
            a,s=parse_act(c.read(stem+'.act')),Spr(c.read(stem+'.spr'));ims={}
            for i in range(s.n_indexed8):
                raw,w,h=s.get_rgba(i,0);alpha=np.frombuffer(raw,dtype=np.uint8).reshape(h,w,4)[:,:,3];yy,xx=np.where(alpha>0);ims[i]=(s.images[i],np.stack([xx,yy],axis=1))
            cache[stem]=(a,s,ims)
        return cache[stem]
    for view,item in ITEMS.items():
        stem=f'data/sprite/인간족/어세신/어세신_남_{item}';act,spr,ims=load(stem)
        for old in data['rows']:
            if old['view']!=6:continue
            r={**old,'key':view,'view':view,'order':old['role']}
            if not r['visible']:rows.append(r);continue
            sa,sf=r['source_action'],r['source_frame'];l=act['actions'][sa].frames[sf].layers[0];im,wp=ims[l.sprite_index];n=normalized_layer(l,im)
            gp,gt=an['weapon_pixels']['6'][str(old['source_layer'][2])];grip,tip=POINTS['남'][view][l.sprite_index]
            axis=np.array(gt)-gp;newaxis=np.array(tip)-grip
            if r['mirror']:axis[0]*=-1;newaxis[0]*=-1
            angle=(r['angle']+math.degrees(math.atan2(axis[1],axis[0])-math.atan2(newaxis[1],newaxis[0]))+180)%360-180
            r.update(source_layer=n,dimensions=[im.width,im.height],grip=grip,tip=tip,angle=angle);rows.append(r)
            if r['phase']:continue
            d,f,role=r['direction'],r['frame'],r['role'];rad=math.radians(angle);wm=np.array([[math.cos(rad),-math.sin(rad)],[math.sin(rad),math.cos(rad)]])@np.diag([-1 if r['mirror'] else 1,1])
            for bi,b in enumerate(data['bodies']):
                ba,bs,bims=load(b['stem']);bl=ba['actions'][32+d].frames[f].layers[0];bim,bp=bims[bl.sprite_index];bn=normalized_layer(bl,bim);q=p.project(bn,(bim.width,bim.height,0,0),origin=(960,495));bo,bm=affine([*q[:4],q[7]],(bim.width,bim.height))
                if d in (0,1,6,7):
                    bpt=HELD_FISTS[bi][bl.sprite_index-54][role];wpt=TERMINALS[view]
                    assert bpt in {tuple(x) for x in bp};assert wpt in {tuple(x) for x in wp},(view,l.sprite_index,wpt)
                    bc=np.array(bpt)+(.5,0.);inward=bm[:,1]/np.linalg.norm(bm[:,1]);wc=np.array(wpt)+.5+.5*np.sign(wm.T@inward)
                    detail=dict(hand_mask=[list(bpt)],body_pixel=list(bpt),weapon_pixel=list(wpt),method='authored_fist_top_to_original_handle_terminal')
                else:
                    seed=oldcontacts[bi,d,f,role]['generic_body_seed'];bc,wc,detail=endpoint_contact(bp,seed,bm,wp,grip,tip,wm)
                contacts.append(dict(body=bi,key=view,view=view,direction=d,frame=f,role=role,body_contact=bc.tolist(),weapon_contact=wc.tolist(),**detail))
    result=dict(schema='male_axe_profile/v1',keys=list(ITEMS),bodies=data['bodies'],rows=rows,contacts=contacts,terminals=TERMINALS,points=POINTS['남'],sources=c.sources,live_acceptance=False)
    write_profile(REPORT, json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8');emit(result,HEADER,'DWMA');print(json.dumps(dict(rows=len(rows),contacts=len(contacts))))
if __name__=='__main__':main()
