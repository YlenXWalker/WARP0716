"""Inventory the active Lua mappings, all Assassin bodies, and original assets.

Never treat a numeric view cutoff as Drake exclusion; use the actual symbol
and filename. Also inventory unreferenced resource pairs, without inventing
an item/view mapping for them.
"""
import json,hashlib
from pathlib import Path
from female_weapon_assets import FemaleCorpus,CLIENT,ROOT
from dual_weapon_corpus import TABLE,CLS
from dual_weapon_formats.weapontable_lua import lua_block,parse_ids,parse_names,parse_expansions
from dual_weapon_formats.act_reader import parse_act
from dual_weapon_formats.spr_reader import Spr

def main():
    c=FemaleCorpus(CLIENT);assert not c.unreadable
    a,b=[c.read(x).decode('cp949') for x in (TABLE,CLS)]
    ids=parse_ids(lua_block(a,'Weapon_IDs'))|parse_ids(lua_block(b,'Weapon_IDs_CLS'))
    names=parse_names(lua_block(a,'WeaponNameTable'))|parse_names(lua_block(b,'WeaponNameTable_CLS'))
    exp=parse_expansions(lua_block(a,'Expansion_Weapon_IDs'))|parse_expansions(lua_block(b,'Expansion_Weapon_IDs_CLS'))
    views=[dict(view=v,type=ids.get(exp.get(k,k)),symbol=k,suffix=names.get(k),excluded_drake='drake' in (k+str(names.get(k))).lower()) for k,v in ids.items() if ids.get(exp.get(k,k)) in (1,2,6)]
    rows=[];extras=[];bodies=[]
    for sex in ('여','남'):
        for job in ('어세신','shadow_cross'):
            prefix=f'data/sprite/인간족/{job}/{job}_{sex}'
            for v in sorted(views,key=lambda v:v['view']):
                stem=prefix+v['suffix'];ab,sb=c.read(stem+'.act'),c.read(stem+'.spr')
                row=dict(**v,gender=sex,family=job,stem=stem,present=bool(ab and sb))
                if ab and sb:
                    act,spr=parse_act(ab),Spr(sb);row.update(act_sha256=hashlib.sha256(ab).hexdigest(),spr_sha256=hashlib.sha256(sb).hexdigest(),actions=len(act['actions']),images=len(spr.images))
                elif not v['excluded_drake']:
                    ending='_'+sex+v['suffix'].lower()+'.spr'
                    row['alternative_job_pairs']=sorted(k[:-4] for k in c.keys if k.endswith(ending) and k[:-4]+'.act' in c.keys)
                rows.append(row)
            mapped={ (prefix+v['suffix']+'.spr').lower() for v in views }
            extras+=sorted(k[:-4] for k in c.keys if k.startswith(prefix.lower()+'_') and k.endswith('.spr') and k not in mapped and k[:-4]+'.act' in c.keys and 'drake' not in k)
        for job in ('어세신','어세신_h','어쌔신크로스','길로틴크로스','shadow_cross'):
            stem=f'data/sprite/인간족/몸통/{sex}/{job}_{sex}';ab,sb=c.read(stem+'.act'),c.read(stem+'.spr');assert ab and sb
            act,spr=parse_act(ab),Spr(sb)
            cells=[]
            for ph,base,count in [(0,32,6),(1,88,8)]:
                for d in range(8):
                    for f in range(count):
                        cells.append(dict(phase=ph,direction=d,frame=f,layers=[dict(index=l.sprite_index,x=l.x,y=l.y,mirror=l.mirror,width=spr.images[l.sprite_index].width,height=spr.images[l.sprite_index].height) for l in act['actions'][base+d].frames[f].layers]))
            bodies.append(dict(stem=stem,gender=sex,job=job,act_sha256=hashlib.sha256(ab).hexdigest(),spr_sha256=hashlib.sha256(sb).hexdigest(),cells=cells))
    result=dict(schema='assassin_weapon_manifest/v1',views=views,resources=rows,bodies=bodies,unmapped_pairs=extras,sources=c.sources,archives=c.archive_profiles,unreadable=c.unreadable)
    (ROOT/'docs/evidence/assassin-weapon-manifest-20260907.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n',encoding='utf8')
    print(json.dumps(dict(non_drake_views=[v['view'] for v in views if not v['excluded_drake']],bodies=len(bodies),missing=[{k:r[k] for k in ('view','gender','family','alternative_job_pairs')} for r in rows if not r['present'] and not r['excluded_drake']],body_hashes=[{k:b[k] for k in ('stem','act_sha256','spr_sha256')} for b in bodies])))

if __name__=='__main__':main()
