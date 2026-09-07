"""Read effective GRF/loose-file resources and the active weapon view declarations."""
import configparser,hashlib
from pathlib import Path
from dual_weapon_paths import ROOT
from dual_weapon_formats.grf_reader import GrfFile
from dual_weapon_formats.weapontable_lua import lua_block,parse_ids,parse_names,parse_expansions
TABLE = "data/luafiles514/lua files/datainfo/weapontable.lub"

CLS = "data/luafiles514/lua files/cls/weapontable.lub"
def sha(data):
    return hashlib.sha256(data).hexdigest()

class Corpus:
    def __init__(self, client):
        self.client, self.archives, self.unreadable, self.sources = client, [], [], {}
        self.archive_profiles = []
        ini = configparser.ConfigParser()
        ini.read(client / "DATA.INI")
        self.priority = [client / value for _, value in sorted(ini["Data"].items(), key=lambda x: int(x[0]))]
        self.keys = set()
        for path in self.priority:
            try:
                archive = GrfFile(path)
                self.archives.append((path, archive))
                self.keys.update(archive.entries)
                self.archive_profiles.append({"path": str(path), "format": archive.format,
                    "version": archive.version, "entry_count": archive.file_count,
                    "ACT_entries": sum(key.endswith('.act') for key in archive.entries),
                    "SPR_entries": sum(key.endswith('.spr') for key in archive.entries)})
            except (ValueError, OSError) as error:
                self.unreadable.append({"path": str(path), "reason": str(error)})
        loose = client / "data"
        if loose.is_dir():
            self.keys.update(p.relative_to(client).as_posix().lower() for p in loose.rglob("*") if p.is_file())

    def read(self, key):
        key = key.lower()
        path = self.client / Path(key)
        data, source = (path.read_bytes(), path) if path.is_file() else (None, None)
        if data is None:
            for path, archive in self.archives:
                data = archive.read(key)
                if data is not None:
                    source = path
                    break
        if data is not None:
            self.sources[key] = {"source": str(source), "bytes": len(data), "sha256": sha(data)}
        return data

    def absent_status(self):
        return "not_found_in_readable_sources_unreadable_archive_remains" if self.unreadable else "absent"

    def close(self):
        for _, archive in self.archives:
            archive.close()

def weapon_views(corpus):
    a,b=[corpus.read(p).decode('cp949') for p in (TABLE,CLS)]
    ids=parse_ids(lua_block(a,'Weapon_IDs'))|parse_ids(lua_block(b,'Weapon_IDs_CLS'))
    names=parse_names(lua_block(a,'WeaponNameTable'))|parse_names(lua_block(b,'WeaponNameTable_CLS'))
    expansions=parse_expansions(lua_block(a,'Expansion_Weapon_IDs'))|parse_expansions(lua_block(b,'Expansion_Weapon_IDs_CLS'))
    views=[]
    for symbol,view in ids.items():
        base=ids.get(expansions.get(symbol,symbol))
        suffix=names.get(symbol)
        if base in (1,2,6) and suffix and 'drake' not in (symbol+suffix).lower():
            views.append(dict(view=view,base_type=base,resource_stem=suffix.lstrip('_'),suffix=suffix,symbol=symbol))
    return {'views':sorted(views,key=lambda row:row['view'])}
