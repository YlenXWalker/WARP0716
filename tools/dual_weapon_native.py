"""Reusable x86 fixtures and native C40C20 projection; no historical test runners."""
from __future__ import annotations
import configparser,hashlib,math,struct,sys,zlib
from pathlib import Path
sys.dont_write_bytecode=True
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
from dual_weapon_paths import ROOT,CLIENT,EXE,BODY,INPUT,FAMILIES,BODIES
from dual_weapon_formats.act_reader import parse_act
from dual_weapon_formats.spr_reader import Spr
from dual_weapon_formats.grf_reader import GrfFile
from dual_weapon_corpus import Corpus
PREFIX="data/sprite/인간족/어세신/어세신_여_"
PAIR_NAMES={25:"단검_단검",26:"검_검",27:"도끼_도끼",28:"단검_검",29:"단검_도끼",30:"검_도끼"}
NAMES={1:("1238",34),2:("13412",45),6:("도끼",6)}
PAIRS=[(25,1,1),(26,2,2),(27,6,6),(28,2,1),(28,1,2),(29,6,1),(29,1,6),(30,6,2),(30,2,6)]

def normalized_layer(raw, image):
    """Raw ACT center -> native integer edge; ceil-half confirmed from live fields.

    This helper intentionally requires a valid image and does not invent the
    native sentinel behavior for invalid sprite indices.
    """
    return [raw.x - (image.width + 1) // 2, raw.y - (image.height + 1) // 2,
            raw.sprite_index, raw.mirror, int.from_bytes(bytes(raw.color), 'little'),
            raw.scale_x, raw.scale_y, raw.rotation, raw.sprite_type]

def f32(value):
    return struct.unpack('<f', struct.pack('<f', value))[0]

class NativeProjector:
    ENTRY, END = 0xC40C20, 0xC412C8

    def __init__(self, executable):
        self.executable = executable
        raw = executable.read_bytes()
        self.sha256 = hashlib.sha256(raw).hexdigest()
        pe = pefile.PE(data=raw)
        assert pe.FILE_HEADER.Machine == 0x14c and pe.OPTIONAL_HEADER.ImageBase == 0x400000
        self.code = pe.get_data(self.ENTRY - 0x400000, self.END - self.ENTRY)
        assert self.code[:6] == bytes.fromhex('55 8b ec 83 ec 0c')
        assert self.code[-3:] == bytes.fromhex('c2 44 00')
        self.u = Uc(UC_ARCH_X86, UC_MODE_32)
        self.u.mem_map(0x400000, (pe.OPTIONAL_HEADER.SizeOfImage + 4095) & ~4095)
        self.u.mem_write(0x400000, pe.get_memory_mapped_image())
        self.base = 0x40000000
        self.u.mem_map(self.base, 0x10000)
        self.actor, self.layer, self.image = self.base, self.base + 0x1000, self.base + 0x1100
        self.packet, self.rect, self.color = self.base + 0x1200, self.base + 0x1300, self.base + 0x1400
        self.depth, self.viewport, self.stack = self.base + 0x1500, self.base + 0x1600, self.base + 0xE000
        self.stop = self.base + 0xF000
        self.w(0x12515F8, self.viewport)
        self.w(self.viewport + 0x28, 8192, 8192)
        assert struct.unpack('<d', self.u.mem_read(0xFD4420, 8))[0] == 1.0

    def w(self, address, *values):
        self.u.mem_write(address, struct.pack('<' + 'I' * len(values), *(x & 0xffffffff for x in values)))

    def project(self, layer, dimensions, unit=1.0, actor_scale=1.0,
                origin=(400.0, 300.0), offsets=(0, 0), extra_x=0.0, actor_angle=0):
        self.u.mem_write(self.actor, bytes(0x600))
        self.w(self.actor + 0x50, struct.unpack('<I', struct.pack('<f', actor_scale))[0])
        self.w(self.actor + 0x7C, actor_angle)
        self.w(self.actor + 0x98, 0xffffffff)
        # Native constant-depth path avoids unrelated camera/depth division.
        self.u.mem_write(self.actor + 0xA2, b'\1')
        self.u.mem_write(self.layer, struct.pack('<4iI2f2i', *layer))
        self.u.mem_write(self.image, struct.pack('<4h', *dimensions))
        self.u.mem_write(self.packet, bytes(48))
        bits = lambda x: struct.unpack('<I', struct.pack('<f', x))[0]
        args = [0, 0, bits(unit), self.layer, bits(origin[0]), bits(origin[1]),
                self.depth, bits(extra_x), self.depth + 16, self.depth + 20,
                self.image, self.packet, self.rect, self.color,
                offsets[0], offsets[1], 0]
        self.w(self.stack, self.stop, *args)
        registers = [UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP]
        for i, register in enumerate(registers):
            self.u.reg_write(register, 0x777000 + i * 16)
        self.u.reg_write(UC_X86_REG_ESP, self.stack)
        self.u.reg_write(UC_X86_REG_ECX, self.actor)
        self.u.emu_start(self.ENTRY, self.stop, count=10000)
        assert self.u.reg_read(UC_X86_REG_EIP) == self.stop
        assert self.u.reg_read(UC_X86_REG_ESP) == self.stack + 72, 'Native RET68 imbalance'
        assert self.u.reg_read(UC_X86_REG_EAX) & 255 == 1, 'Native packet was clipped'
        for i, register in enumerate(registers):
            assert self.u.reg_read(register) == 0x777000 + i * 16
        assert bytes(self.u.mem_read(self.layer, 36)) == struct.pack('<4iI2f2i', *layer)
        return struct.unpack('<6fIf', self.u.mem_read(self.packet, 32))

class Resources:
    def __init__(self,client):
        self.client=client; self.grfs=[]; self.evidence={}
        ini=configparser.ConfigParser(); ini.read(client/"DATA.INI")
        self.paths=[client/v for k,v in sorted(ini["Data"].items(),key=lambda kv:int(kv[0]))]
    def read(self,name):
        key=PREFIX+name
        loose=self.client/Path(key)
        source=None; data=None
        if loose.is_file(): data=loose.read_bytes(); source=str(loose)
        else:
            for i,path in enumerate(self.paths):
                if len(self.grfs)<=i: self.grfs.append(GrfFile(path))
                data=self.grfs[i].read(key.lower())
                if data is not None: source=str(path); break
        if data is None: raise FileNotFoundError(key)
        self.evidence[key]={"source":source,"bytes":len(data),"sha256":hashlib.sha256(data).hexdigest()}
        return data

class Machine:
    def __init__(self,resources,payload=None,native_layout=True):
        self.native_layout=native_layout
        self.u=Uc(UC_ARCH_X86,UC_MODE_32)
        self.u.mem_map(0x100000,0x3000000)
        self.next=0x800000; self.resources=resources; self.loaded={}
        self.draw=0x110000; self.stop=0x110100; self.calls=[]
        self.u.mem_write(self.draw,b"\xC2\x18\x00"); self.u.mem_write(self.stop,b"\xCC")
        blob=(payload or ROOT/"Inputs/DualWeaponRuntime/compositor.dwcp").read_bytes()
        magic,version,size,entry,n,rigsize,gripsize,crc=struct.unpack_from("<8I",blob)
        assert magic==0x50435744 and version==1 and zlib.crc32(blob[32:])==crc
        begin=32+n*4; self.code=0x200000
        data=bytearray(blob[begin:])
        for off in struct.unpack_from("<"+"I"*n,blob,32):
            value,=struct.unpack_from("<I",data,off)
            struct.pack_into("<I",data,off,self.code+value)
        self.u.mem_write(self.code,bytes(data)); self.entry=self.code+entry
        self.actor=self.alloc(0x600); self.registry=self.alloc(60*256); self.views=self.alloc(8*256)
        self.slot=self.alloc(28); self.ctx=self.alloc(21*4); self.packet=self.alloc(64)+4
        self.w(self.actor+0x4ac,self.slot,self.slot+28)
        context=[self.registry,0xdead0000,0,0,0,0x38,0x3c,256,0,0,0,0x440,0x444,0,0,0,0,
                 self.code+size,self.views,0,self.code+size+rigsize]
        self.w(self.ctx,*context)
        self.row=self.registry+((self.actor>>4)&255)*60
        self.viewrow=self.views+((self.actor>>4)&255)*8
        # Only the draw/return stubs need Python observers; keep native execution unhooked.
        self.u.hook_add(UC_HOOK_CODE,self.hook,begin=self.draw,end=self.stop)
    def alloc(self,n):
        addr=self.next; self.next=(addr+n+15)&~15
        assert self.next<0x2000000
        return addr
    def w(self,addr,*v): self.u.mem_write(addr,struct.pack("<"+"I"*len(v),*(x&0xffffffff for x in v)))
    def r(self,addr): return struct.unpack("<I",self.u.mem_read(addr,4))[0]
    def hook(self,uc,address,size,_):
        if address==self.stop: uc.emu_stop()
        elif address==self.draw:
            esp=uc.reg_read(UC_X86_REG_ESP)
            pkt,pal,a3,a4,a5,a6=struct.unpack("<6I",uc.mem_read(esp+4,24))
            self.calls.append({"actor":uc.reg_read(UC_X86_REG_ECX),"palette":pal,
                               "packet":struct.unpack("<6fIf3II",uc.mem_read(pkt,48)),
                               "image":self.r(pkt+44)})
    def load(self,name):
        if name in self.loaded: return self.loaded[name]
        act=parse_act(self.resources.read(name+".act")); spr=Spr(self.resources.read(name+".spr"))
        bitmaps={kind:[im for im in spr.images if im.is_indexed==(kind==0)] for kind in (0,1)}
        sa=self.alloc(0x530); aa=self.alloc(0x140); actions=self.alloc(12*len(act["actions"]))
        # CResource's inline CP949 filename is part of the native family guard.
        for address,extension in ((sa,'.spr'),(aa,'.act')):
            path=(PREFIX.removeprefix('data/').replace('/','\\')+name+extension).encode('cp949')+b'\0'
            assert len(path)<=0xf0
            self.u.mem_write(address+0x14,path)
        self.w(aa+0x110,actions,actions+12*len(act["actions"]))
        layers={}
        for ai,action in enumerate(act["actions"]):
            frames=self.alloc(68*len(action.frames))
            self.w(actions+ai*12,frames,frames+68*len(action.frames),frames+68*len(action.frames))
            for fi,frame in enumerate(action.frames):
                lb=self.alloc(36*len(frame.layers))
                self.w(frames+fi*68+32,lb,lb+36*len(frame.layers),lb+36*len(frame.layers),len(frame.layers))
                for li,l in enumerate(frame.layers):
                    x,y=l.x,l.y
                    if self.native_layout and 0<=l.sprite_index<len(bitmaps[l.sprite_type]):
                        im=bitmaps[l.sprite_type][l.sprite_index]
                        x-=(im.width+1)//2; y-=(im.height+1)//2
                    self.u.mem_write(lb+36*li,struct.pack("<4iI2f2i",x,y,l.sprite_index,l.mirror,
                                    int.from_bytes(bytes(l.color),"little"),l.scale_x,l.scale_y,l.rotation,l.sprite_type))
                if self.native_layout and frame.anchors:
                    ab=self.alloc(12*len(frame.anchors))
                    for ai2,anchor in enumerate(frame.anchors):self.w(ab+ai2*12,*anchor)
                    self.w(frames+fi*68+0x34,ab,ab+12*len(frame.anchors),ab+12*len(frame.anchors),len(frame.anchors))
                if frame.layers: layers[(ai,fi)]=(lb,frame.layers[0])
        images={}; image_addrs=[]
        for kind in [0,1]:
            subset=[im for im in spr.images if im.is_indexed==(kind==0)]
            vec=self.alloc(4*len(subset))
            self.w(sa+0x510+kind*12,vec,vec+4*len(subset),vec+4*len(subset))
            for i,im in enumerate(subset):
                ptr=self.alloc(16)
                self.u.mem_write(ptr,struct.pack("<HHIII",im.width,im.height,0,0,0))
                self.w(vec+i*4,ptr);images[(kind,i)]=(ptr,im);image_addrs.append(ptr)
        result=dict(spr=sa,act=aa,parsed=act,layers=layers,images=images,image_addrs=image_addrs,name=name,native_normalized=self.native_layout)
        self.loaded[name]=result
        return result
    def equip(self,pair,main,off,off_only=False):
        m=self.load(NAMES[main][0]); o=self.load(NAMES[off][0])
        stock_name=PAIR_NAMES[pair] if not off_only else {1:"단검",2:"검",6:"도끼"}[off]
        stock=self.load(stock_name)
        trail=self.load(stock_name+"_검광")
        self.w(self.slot+20,stock["spr"],trail["spr"])
        self.w(self.row,self.actor,0 if off_only else m["spr"],0 if off_only else m["act"],0,0,
               o["spr"],o["act"],0,0,stock["act"],trail["act"],pair,0 if off_only else main,off,0)
        self.w(self.viewrow,0 if off_only else NAMES[main][1],NAMES[off][1])
        self.w(self.actor+0x440,0 if off_only else 1001,1002)
        return m,o,stock,trail
    def invoke(self,resource,action,frame,foreign_palette=False,frame_wrap=False):
        self.calls=[]
        actual_frame=0 if frame_wrap and (action,frame) not in resource["layers"] else frame
        info=resource["layers"].get((action,actual_frame))
        if not info: return None
        _,l=info; image=resource["images"].get((l.sprite_type,l.sprite_index))
        if not image: return None
        ptr,im=image
        if self.native_layout:
            # Verified independently against all C40C20 instructions in
            # dual_weapon_native.py; unit-scale fixture.
            nx,ny=struct.unpack('<2i',self.u.mem_read(info[0],8))
            left=400+(nx+(im.width if l.mirror else 0))*l.scale_x
            right=400+(nx+(0 if l.mirror else im.width))*l.scale_x+1
            top=300+ny*l.scale_y;bottom=300+(ny+im.height)*l.scale_y+1
        else:
            # Historical synthetic fixture, retained only for isolated old
            # regressions. It is not native geometry or placement evidence.
            cx=400+l.x;cy=300+l.y;w=im.width*l.scale_x;h=im.height*l.scale_y
            left=cx-w/2;right=cx+w/2;top=cy-h/2;bottom=cy+h/2
        packet=struct.pack("<6fIf3II",top,left,bottom,right,0.5,0.5,
                           0xffffffff,float(l.rotation),0,0,0,ptr)
        self.u.mem_write(self.packet,packet)
        self.w(self.actor+0x38,action,frame)
        esp=0x2f00000
        args=[self.stop,self.actor,self.packet,resource["spr"]+0x110+(4 if foreign_palette else 0),
              0x123,0,0,0x456,self.ctx,self.draw]
        self.w(esp,*args)
        regs=[UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
        for i,reg in enumerate(regs): self.u.reg_write(reg,0x777000+i*16)
        self.u.reg_write(UC_X86_REG_ESP,esp)
        self.u.emu_start(self.entry,self.stop,count=1000000)
        assert self.u.reg_read(UC_X86_REG_EIP)==self.stop,"did not return"
        assert self.u.reg_read(UC_X86_REG_ESP)==esp+40,"stdcall stack"
        for i,reg in enumerate(regs): assert self.u.reg_read(reg)==0x777000+i*16,"callee-save register"
        assert bytes(self.u.mem_read(self.packet,48))==packet,"input packet mutated"
        return self.u.reg_read(UC_X86_REG_EAX)

class NativeLayout:
    def load(self, name):
        resource = super().load(name)
        if resource.get('native_normalized'):
            return resource
        for (action, frame), (address, raw) in resource['layers'].items():
            image = resource['images'].get((raw.sprite_type, raw.sprite_index))
            if image:
                native = normalized_layer(raw, image[1])
                self.u.mem_write(address, struct.pack('<4iI2f2i', *native))
            anchors = resource['parsed']['actions'][action].frames[frame].anchors
            vector = self.r(resource['act'] + 0x110)
            frame_address = self.r(vector + action * 12) + frame * 68
            if anchors:
                begin = self.alloc(12 * len(anchors))
                for i, anchor in enumerate(anchors):
                    self.w(begin + i * 12, *anchor)
                self.w(frame_address + 0x34, begin, begin + len(anchors) * 12,
                       begin + len(anchors) * 12, len(anchors))
        resource['native_normalized'] = True
        return resource

    def native_layer(self, resource, action, frame):
        return struct.unpack('<4iI2f2i', self.u.mem_read(resource['layers'][(action, frame)][0], 36))

class NativeMachine(NativeLayout, Machine):
    pass

class GripResources(Resources):
    def __init__(self,client):
        super().__init__(client);self.corpus=Corpus(client)
    def read(self,name):
        if name.startswith('@body.'):
            return self.corpus.read(BODY+name[len('@body'):])
        return super().read(name)

class GripMachine(NativeMachine):
    def __init__(self,resources,payload):
        super().__init__(resources,payload)
        self.body=self.load('@body');self.actslots=self.alloc(4)
        self.w(self.slot,self.body['spr']);self.w(self.actslots,self.body['act'])
        self.w(self.actor+0x4b8,self.actslots,self.actslots+4)
        for field,ext in [('act','.act'),('spr','.spr')]:
            name=(BODY.removeprefix('data/').replace('/','\\')+ext).encode('cp949')+b'\0'
            self.u.mem_write(self.body[field]+0x14,name)
    def equip_views(self,main,off,mt,ot,mv,ov,carrier='단검_검',off_only=False):
        stock,trail=self.load(carrier),self.load(carrier+'_검광')
        self.w(self.slot+20,stock['spr'],trail['spr'])
        self.w(self.row,self.actor,0 if off_only else main['spr'],0 if off_only else main['act'],0,0,
               off['spr'],off['act'],0,0,stock['act'],trail['act'],28,0 if off_only else mt,ot,0)
        self.w(self.viewrow,0 if off_only else mv,ov)
        self.w(self.actor+0x440,0 if off_only else 1001,1002)
        return stock,trail

def point(geometry,dimensions,pixel):
    top,left,bottom,right,angle=geometry;w,h=dimensions
    x=((pixel[0]+.5)/w-.5)*(right-left)
    y=((pixel[1]+.5)/h-.5)*(bottom-top)
    a=math.radians(angle)
    return [(left+right)/2+x*math.cos(a)-y*math.sin(a),
            (top+bottom)/2+x*math.sin(a)+y*math.cos(a)]

class MaleMachine(NativeMachine):
    def __init__(self,resources,payload):
        super().__init__(resources,payload)
        self.body=self.load('@body');self.actslots=self.alloc(4)
        self.w(self.slot,self.body['spr']);self.w(self.actslots,self.body['act'])
        self.w(self.actor+0x4b8,self.actslots,self.actslots+4)
    def load(self,name):
        r=super().load(name)
        for field,ext in [('act','.act'),('spr','.spr')]:
            stem=self.resources.body if name=='@body' else self.resources.prefix+name
            s=(stem.removeprefix('data/').replace('/','\\')+ext).encode('cp949')+b'\0'
            self.u.mem_write(r[field]+0x14,s)
        return r
    def equip(self,main,off,mv,ov,mt,ot,carrier='단검_검',off_only=False):
        stock,trail=self.load(carrier),self.load(carrier+'_검광')
        self.w(self.slot+20,stock['spr'],trail['spr'])
        self.w(self.row,self.actor,0 if off_only else main['spr'],0 if off_only else main['act'],0,0,
               off['spr'],off['act'],0,0,stock['act'],trail['act'],28,0 if off_only else mt,ot,1)
        self.w(self.viewrow,0 if off_only else mv,ov)
        self.w(self.actor+0x440,0 if off_only else 1001,1002)
        return stock,trail

def semantic_draw(machine, call):
    owners = [r for r in machine.loaded.values() if call['palette'] == r['spr'] + 0x110]
    assert len(owners) == 1
    owner = owners[0]
    images = [key for key, value in owner['images'].items() if value[0] == call['image']]
    assert len(images) == 1
    assert call['actor'] == machine.actor
    return {'resource': owner['name'], 'image': images[0], 'packet_without_image_pointer': call['packet'][:11]}

def invoke_native(machine, projector, resource, action, frame, unit, channel=5, actor_angle=0):
    info = resource['layers'].get((action, frame))
    if not info:
        return None
    layer = machine.native_layer(resource, action, frame)
    image = resource['images'].get((layer[8], layer[2]))
    if not image:
        return None
    pointer, bitmap = image
    native = projector.project(layer, (bitmap.width, bitmap.height, 0, 0), unit,
                               origin=(960.0, 495.0), actor_angle=actor_angle)
    packet = struct.pack('<6fIf3II', *native, 0, 0, 0, pointer)
    machine.u.mem_write(machine.packet, packet)
    machine.w(machine.actor + 0x38, action, frame)
    machine.calls = []
    esp = 0x2f00000
    machine.w(esp, machine.stop, machine.actor, machine.packet,
              resource['spr'] + 0x110, 0x123, 0, 0, 0x456, machine.ctx, machine.draw)
    registers = [UC_X86_REG_EBX, UC_X86_REG_ESI, UC_X86_REG_EDI, UC_X86_REG_EBP]
    for i, register in enumerate(registers):
        machine.u.reg_write(register, 0x777000 + i * 16)
    machine.u.reg_write(UC_X86_REG_ESP, esp)
    machine.u.emu_start(machine.entry, machine.stop, count=1000000)
    assert machine.u.reg_read(UC_X86_REG_EIP) == machine.stop
    assert machine.u.reg_read(UC_X86_REG_ESP) == esp + 40
    for i, register in enumerate(registers):
        assert machine.u.reg_read(register) == 0x777000 + i * 16
    assert bytes(machine.u.mem_read(machine.packet, 48)) == packet
    draws = []
    for call in machine.calls:
        semantic = semantic_draw(machine, call)
        values = semantic.pop('packet_without_image_pointer')
        semantic['geometry'] = list(values[:4]) + [values[7]]
        semantic['center'] = [(values[1] + values[3]) / 2, (values[0] + values[2]) / 2]
        # Actual native z/color remain current-packet owned, so they must be
        # preserved rather than compared to the hypothetical reference packet.
        assert values[4:7] == native[4:7]
        draws.append(semantic)
    return {'handled': machine.u.reg_read(UC_X86_REG_EAX), 'draws': draws}
