"""Render CPU review sheets from final x86 packets and original GRF pixels."""
import json,sys,functools,html,argparse
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.append(str(ROOT/'.venv/Lib/site-packages'));sys.dont_write_bytecode=True
from PIL import Image,ImageDraw,ImageFont
from verify_assassin_weapon_matrix import Fixture,Resources,PAYLOAD
from female_weapon_assets import FemaleCorpus,CLIENT,OUT
from dual_weapon_native import NativeProjector
from dual_weapon_paths import EXE
from dual_weapon_native import invoke_native
from dual_weapon_formats.spr_reader import Spr
from dual_weapon_geometry import paint
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--exe',type=Path,default=EXE)
    parser.add_argument('--output',type=Path,default=OUT/'review')
    args=parser.parse_args();dest=args.output;dest.mkdir(parents=True,exist_ok=True)
    manifest=json.loads((ROOT/'docs/evidence/assassin-weapon-manifest-20260907.json').read_text(encoding='utf8'))
    decl={r['view']:r for r in manifest['views'] if not r['excluded_drake']}
    c=FemaleCorpus(CLIENT);p=NativeProjector(args.exe);p.project=functools.lru_cache(maxsize=8192)(p.project)
    font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',14);titles=[];body_names=['Assassin','High Assassin','Assassin Cross','Guillotine Cross','Shadow Cross']
    for bi,b in enumerate(manifest['bodies']):
        res=Resources(c,b);m=Fixture(res,PAYLOAD);weapons={v:m.load(r['suffix'].lstrip('_')) for v,r in decl.items()};pixels={}
        def pic(name,index,kind=0):
            key=name,index,kind
            if key not in pixels:
                raw,w,h=Spr(res.read(name+'.spr')).get_rgba(index,kind);pixels[key]=Image.frombytes('RGBA',(w,h),raw)
            return pixels[key]
        def original(r,a,f):
            if (a,f) not in r['layers']:return None
            l=m.native_layer(r,a,f);im=r['images'].get((l[8],l[2]))
            if im is None:return None
            bm=im[1];q=p.project(l,(bm.width,bm.height,0,0),origin=(400,300))
            return pic(r['name'],l[2],l[8]),[*q[:4],q[7]]
        def draw(canvas,image,g):
            paint(canvas,image,g,scale=2,origin=(65,115))
        def board(mv,ov,a,f,custom):
            stock,trail=m.equip(weapons[mv],weapons[ov],mv,ov,decl[mv]['type'],decl[ov]['type'])
            canvas=Image.new('RGBA',(260,285),'#e4eaf0')
            body=original(m.body,a,f)
            if body:draw(canvas,*body)
            for channel,r in ((5,stock),(6,trail)):
                q=invoke_native(m,p,r,a,f,1.,channel) if custom else None
                if q and q['handled']:
                    for dr in q['draws']:
                        g=dr['geometry'];g=[g[0]-195,g[1]-560,g[2]-195,g[3]-560,g[4]]
                        draw(canvas,pic(dr['resource'],dr['image'][1],dr['image'][0]),g)
                else:
                    cell=original(r,a,f)
                    if cell:draw(canvas,*cell)
            ImageDraw.Draw(canvas).text((8,8),f'R {mv} / L {ov} | A{a} F{f}',fill='black',font=font)
            return canvas.convert('RGB')
        title=('Female' if bi<5 else 'Male')+' '+body_names[bi%5];titles.append(title)
        for phase,a,f in [('held',32,0),('attack',94,3)]:
            sheet=Image.new('RGB',(1040,1740),'#e4eaf0');pen=ImageDraw.Draw(sheet)
            pen.text((10,8),title+' | main view / off blue sword 45 | CPU projection; heads and occlusion omitted',fill='black',font=font)
            for i,v in enumerate(decl):sheet.paste(board(v,45,a,f,True),((i%4)*260,30+(i//4)*285))
            sheet.save(dest/f'body{bi}-{phase}.png')
        frames=[]
        for a,n in ((32,6),(38,6),(88,8),(94,8)):
            for f in range(n):
                sheet=Image.new('RGB',(520,315),'#e4eaf0');pen=ImageDraw.Draw(sheet)
                sheet.paste(board(33,45,a,f,False),(0,30));sheet.paste(board(33,45,a,f,True),(260,30))
                pen.text((8,8),'Native generic dagger / sword',fill='black',font=font)
                pen.text((268,8),'Original Gladius / blue sword',fill='black',font=font);frames.append(sheet)
        frames[0].save(dest/f'body{bi}-gladius-blue.gif',save_all=True,append_images=frames[1:],duration=150,loop=0)
        print(json.dumps(dict(body=bi,review_sheets=2,animation_frames=len(frames))),flush=True)
    sections='\n'.join(f'<section><h2>{html.escape(t)}</h2><img src="body{i}-gladius-blue.gif" alt="Generic and original weapon animation comparison"><details><summary>All 24 main-hand views, held</summary><img class="sheet" src="body{i}-held.png"></details><details><summary>All 24 main-hand views, attack</summary><img class="sheet" src="body{i}-attack.png"></details></section>' for i,t in enumerate(titles))
    (dest/'index.html').write_text('<!doctype html><meta charset="utf-8"><title>Assassin weapon coverage review</title><style>body{font:16px system-ui;max-width:1100px;margin:32px auto;background:#fafafa;color:#172838}section{margin:32px 0;padding:20px;background:white;border:1px solid #d4dce2}img{max-width:100%;image-rendering:pixelated}.sheet{width:1040px}summary{padding:12px;cursor:pointer}</style><h1>Assassin weapon coverage review</h1><p>Final compiled x86 packets over original GRF body and weapon pixels. These are CPU projections, not game recordings. Head/effect art and native body/weapon depth occlusion are omitted. Existing accepted geometry stays exact. Right/main is anatomical, independent of screen side.</p>'+sections,encoding='utf8')
    c.close()
if __name__=='__main__':main()
