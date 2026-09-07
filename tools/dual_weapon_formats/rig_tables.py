"""Read the frozen DWR3 transform rig used by the native-basis generator.

The binary layout is defined below; the active runtime contract is documented
in docs/dual-wield-original-weapon-sprites.md.
"""

from __future__ import annotations

import dataclasses
import hashlib
import struct

DWR3_HEADER = struct.Struct("<4sHBBIII")
DWR3_TRANSFORM = struct.Struct("<bbBBh")


@dataclasses.dataclass(frozen=True)
class RigTransform:
	dx: int
	dy: int
	flags: int
	metadata: int
	rotation: int


def dense_index(family, gender, state, state_count, phase, direction, frame, hand) -> int:
	return ((((((family * 2 + gender) * state_count + state) * 2 + phase) * 8 + direction) * 8 + frame) * 2 + hand)


def parse_rig_bytes(rig: bytes) -> dict:
	magic, schema, family_count, state_count, index_count, transform_count, crc = (
		DWR3_HEADER.unpack_from(rig, 0)
	)
	if magic != b"DWR3" or schema != 3 or state_count != 15:
		raise ValueError("unexpected DWR3 header")
	family_offset = DWR3_HEADER.size
	index_offset = family_offset + family_count * 16
	transform_offset = index_offset + index_count * 2
	if transform_offset + transform_count * DWR3_TRANSFORM.size != len(rig):
		raise ValueError("DWR3 size mismatch")
	indices = struct.unpack_from(f"<{index_count}H", rig, index_offset)
	transforms = [
		RigTransform(*DWR3_TRANSFORM.unpack_from(rig, transform_offset + index * DWR3_TRANSFORM.size))
		for index in range(transform_count)
	]
	records = []
	for family in range(family_count):
		for gender in range(2):
			for state in range(state_count):
				for phase in range(2):
					for direction in range(8):
						for frame in range(8):
							for hand in range(2):
								dense = dense_index(family, gender, state, state_count, phase, direction, frame, hand)
								transform_index = indices[dense]
								if transform_index:
									records.append({
										"family": family,
										"gender": gender,
										"state": state,
										"phase": phase,
										"direction": direction,
										"frame": frame,
										"hand": hand,
										"transform_index": transform_index,
										"transform": transforms[transform_index - 1],
									})
	return {
		"bytes": rig,
		"sha256": hashlib.sha256(rig).hexdigest().upper(),
		"family_count": family_count,
		"state_count": state_count,
		"index_count": index_count,
		"transform_count": transform_count,
		"crc32": crc,
		"records": records,
	}
