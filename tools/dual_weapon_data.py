"""Deterministic compressed expected geometry for builders and current verification."""
import gzip,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DIRECTORY=ROOT/'Inputs/DualWeaponAuthored/profiles'
NAMES={'female-family-profile-20260907.json', 'dual-weapon-male-hand-profile-20260907.json', 'female-dagger-profile-20260907.json', 'male-axe-profile-20260907.json'}
def load_profile(name):
    return json.loads(gzip.decompress((DIRECTORY/(Path(name).name.removesuffix('.gz')+'.gz')).read_bytes()))
def write_profile(path,text,encoding=None):
    data=json.loads(text)
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_bytes(gzip.compress(json.dumps(data,separators=(',',':'),ensure_ascii=False).encode('utf8'),mtime=0))
    return len(text)
