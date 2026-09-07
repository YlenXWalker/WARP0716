"""Reader for the frozen legacy core/depth helper/rig DWLS bundle.

Layout v1: 12 little-endian DWORDs, then raw core, raw helper, raw rig,
then core and helper (offset,target) relocation pairs. Raw images retain
their historical bytes; relocation replaces, rather than adds to, a word.
"""
from pathlib import Path
import struct,zlib
ROOT=Path(__file__).resolve().parents[1]
PATH=ROOT/'Inputs/DualWeaponRuntime/legacy-support.dwls'

def read(path=PATH):
    b=path.read_bytes();h=struct.unpack_from('<12I',b)
    magic,version,cn,ce,cr,hn,he,hr,rn,crc,res0,res1=h
    assert magic==0x534C5744 and version==1 and not (res0 or res1)
    assert 0<cn<=0x200000 and 0<hn<=0x10000 and ce<cn and he<hn and cr<=4096 and hr<=4096
    assert len(b)==48+cn+hn+rn+8*(cr+hr) and zlib.crc32(b[48:])==crc
    off=48;core=b[off:off+cn];off+=cn;helper=b[off:off+hn];off+=hn;rig=b[off:off+rn];off+=rn
    pairs=list(struct.iter_unpack('<2I',b[off:]));core_rel,helper_rel=pairs[:cr],pairs[cr:]
    for length,relocs in ((cn,core_rel),(hn,helper_rel)):
        assert len({o for o,t in relocs})==len(relocs)
        assert all(o+4<=length and t<length for o,t in relocs)
    return {'DualWeaponAuthoredCore':{'data':core,'relocs':core_rel,'entry':ce},
            'DualWeaponCharacterEnvelopeCore':{'data':helper,'relocs':helper_rel,'entry':he},
            'DualWeaponAuthoredRig':{'data':rig,'relocs':[],'entry':0}}

def payload(name):return read()[name]['data']
def relocations(name):return read()[name]['relocs']
