"""Parser for the client's weapontable.lub dual-capable weapon view tables.

See docs/dual-wield-original-weapon-sprites.md for the active Lua mapping contract.
"""

from __future__ import annotations

import dataclasses
import pathlib
import re

DUAL_BASE_TYPES = {1: "dagger", 2: "sword", 6: "axe"}
REFERENCE_VIEWS = {1: 34, 2: 45, 6: 6}


@dataclasses.dataclass(frozen=True)
class WeaponView:
	view: int
	symbol: str
	suffix: str
	base_type: int
	origin: str


def lua_block(text: str, name: str) -> str:
	match = re.search(
		rf"(?ms)^[ \t]*{re.escape(name)}[ \t]*=[ \t]*\{{(.*?)^[ \t]*\}}",
		text,
	)
	return match.group(1) if match else ""


def parse_ids(block: str) -> dict[str, int]:
	result: dict[str, int] = {}
	for symbol, value in re.findall(r"(?m)^[ \t]*([A-Za-z0-9_]+)[ \t]*=[ \t]*(\d+)", block):
		result[symbol] = int(value)
	return result


def parse_names(block: str) -> dict[str, str]:
	result: dict[str, str] = {}
	pattern = (
		r"\[(?:Weapon_IDs|Weapon_IDs_CLS)\.([A-Za-z0-9_]+)\]"
		r"[ \t]*=[ \t]*\"([^\"]*)\""
	)
	for symbol, suffix in re.findall(pattern, block):
		result[symbol] = suffix
	return result


def parse_expansions(block: str) -> dict[str, str]:
	result: dict[str, str] = {}
	pattern = (
		r"\[(?:Weapon_IDs|Weapon_IDs_CLS)\.([A-Za-z0-9_]+)\]"
		r"[ \t]*=[ \t]*(?:Weapon_IDs|Weapon_IDs_CLS)\.([A-Za-z0-9_]+)"
	)
	for symbol, base_symbol in re.findall(pattern, block):
		result[symbol] = base_symbol
	return result


def parse_weapon_tables(
	standard_path: pathlib.Path,
	cls_path: pathlib.Path,
) -> list[WeaponView]:
	"""Return every dual-capable weapon view declared across the two tables.

	standard_path/cls_path are the stock weapontable.lub and its (usually
	empty) *_CLS override companion -- see
	docs/dual-wield-original-weapon-sprites.md's "Lua resource mapping"
	section for the three-layer schema this reads (Weapon_IDs,
	WeaponNameTable, Expansion_Weapon_IDs, plus their _CLS variants).
	"""
	standard = standard_path.read_bytes().decode("cp949")
	cls = cls_path.read_bytes().decode("cp949")
	ids = parse_ids(lua_block(standard, "Weapon_IDs"))
	names = parse_names(lua_block(standard, "WeaponNameTable"))
	expansions = parse_expansions(lua_block(standard, "Expansion_Weapon_IDs"))
	cls_ids = parse_ids(lua_block(cls, "Weapon_IDs_CLS"))
	cls_names = parse_names(lua_block(cls, "WeaponNameTable_CLS"))
	cls_expansions = parse_expansions(lua_block(cls, "Expansion_Weapon_IDs_CLS"))
	all_ids = ids | cls_ids
	all_names = names | cls_names
	all_expansions = expansions | cls_expansions
	result: list[WeaponView] = []
	for symbol, view in sorted(all_ids.items(), key=lambda item: (item[1], item[0])):
		base_symbol = all_expansions.get(symbol, symbol)
		base_type = all_ids.get(base_symbol, ids.get(base_symbol, 0))
		if base_type not in DUAL_BASE_TYPES:
			continue
		suffix = all_names.get(symbol)
		if suffix is None:
			continue
		result.append(WeaponView(
			view=view,
			symbol=symbol,
			suffix=suffix,
			base_type=base_type,
			origin="cls" if symbol in cls_ids else "standard",
		))
	views = [entry.view for entry in result]
	if len(views) != len(set(views)):
		raise AssertionError("duplicate dual-capable weapon view IDs")
	return result
