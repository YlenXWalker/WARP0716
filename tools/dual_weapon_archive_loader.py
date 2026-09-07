"""Execute the existing 2025 embedded GRF loader with ABI-observing AddPak stubs."""
import struct
import pefile
from unicorn import Uc,UC_ARCH_X86,UC_MODE_32,UC_HOOK_CODE
from unicorn.x86_const import *
ENTRY=0x181f2f0

SITE=0x181f3ae

ADDP=0xa88890

MANAGER=0x159d410

EXPECTED=['greyworld.grf','data.grf','spritedata.grf','palettedata.grf','mapdata.grf','maindata.grf','update.grf']

NAME=b'dual_weapon_male_assets.grf\0'
def align(n,a):return (n+a-1)//a*a

def verify(data,expected):
 p=pefile.PE(data=data);u=Uc(UC_ARCH_X86,UC_MODE_32);base=p.OPTIONAL_HEADER.ImageBase
 u.mem_map(base,align(p.OPTIONAL_HEADER.SizeOfImage,4096));u.mem_write(base,p.get_memory_mapped_image())
 u.mem_map(0x30000000,0x20000);stop=0x30010000;sp=0x3000fff0
 u.mem_write(sp,struct.pack('<I',stop));u.reg_write(UC_X86_REG_ESP,sp)
 saved=[UC_X86_REG_EBX,UC_X86_REG_ESI,UC_X86_REG_EDI,UC_X86_REG_EBP]
 for i,r in enumerate(saved):u.reg_write(r,0x10000+i)
 calls=[]
 def read32(a):return struct.unpack('<I',u.mem_read(a,4))[0]
 def hook(uc,addr,size,user):
  if addr==stop:uc.emu_stop();return
  if addr!=ADDP:return
  esp=uc.reg_read(UC_X86_REG_ESP);s=read32(esp+4);name=bytes(uc.mem_read(s,128)).split(b'\0')[0].decode('ascii')
  assert uc.reg_read(UC_X86_REG_ECX)==MANAGER
  calls.append(name)
  uc.reg_write(UC_X86_REG_EAX,0x100000+len(calls));uc.reg_write(UC_X86_REG_ECX,0xdead0001);uc.reg_write(UC_X86_REG_EDX,0xdead0002)
  uc.reg_write(UC_X86_REG_EFLAGS,0x202 if len(calls)%2 else 0x246)
  uc.reg_write(UC_X86_REG_ESP,esp+8);uc.reg_write(UC_X86_REG_EIP,read32(esp))
 u.hook_add(UC_HOOK_CODE,hook);u.emu_start(ENTRY,stop,count=20000)
 assert u.reg_read(UC_X86_REG_EIP)==stop and u.reg_read(UC_X86_REG_ESP)==sp+4
 assert calls==expected,calls
 assert all(u.reg_read(r)==0x10000+i for i,r in enumerate(saved))
 # The eighth call cannot change the caller-visible result of the seventh.
 assert u.reg_read(UC_X86_REG_EAX)==0x100007 and u.reg_read(UC_X86_REG_EFLAGS)==0x202
 return dict(calls=calls,stack_balanced=True,callee_saved=True,original_volatile_result_and_flags_preserved=True)
