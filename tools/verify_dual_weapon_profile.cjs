// Verifies profile reporting against the actual QJS, without mocking a renderer.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const crypto = require('node:crypto');
const sourcePath = path.resolve(__dirname, '../Scripts/Patches/AllowDualCustomWeaponSprites.qjs');
let exeAccesses = 0;
let prepared = true;
const context = vm.createContext({
  RagexeClientProfile: { Id: 20250716 },
  RagexeAllocationStatic: { isPrepared: () => prepared },
  Exe: new Proxy({}, { get() { exeAccesses++; throw new Error('Unexpected EXE access'); } }),
});
vm.runInContext(fs.readFileSync(sourcePath, 'utf8'), context, { filename: sourcePath });
const check = (expression) => vm.runInContext(expression, context);
assert.equal(check('AllowDualCustomWeaponSprites.validate()'), true);
prepared = false;
assert.equal(check('AllowDualCustomWeaponSprites.validate()'), false);
prepared = true;
context.RagexeClientProfile.Id = 20260219;
assert.equal(check('AllowDualCustomWeaponSprites.validate()'), false);
assert.throws(() => check('AllowDualCustomWeaponSprites(null)'), /no dual-weapon compositor/);
// Same process/profile switching catches stale SupportsPose caching.
context.RagexeClientProfile.Id = 20250716;
assert.equal(check('AllowDualCustomWeaponSprites.validate()'), true);
context.RagexeClientProfile.Id = 20990101;
assert.equal(check('AllowDualCustomWeaponSprites.validate()'), false);
assert.equal(exeAccesses, 0);
console.log('PASS: supported/unsupported profiles, allocation readiness, profile switching, zero EXE accesses.');

// External payload integrity is checked before allocation/hook writes.
let payload = fs.readFileSync(path.resolve(__dirname, '../Inputs/DualWeaponRuntime/compositor.dwcp'));
const manifest = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../Inputs/DualWeaponRuntime/compositor.json'), 'utf8'));
const digest = bytes => crypto.createHash('sha256').update(bytes).digest('hex');
assert.equal(digest(payload), manifest.sha256, 'Runtime payload/manifest mismatch');
assert.equal(manifest.contact_measurement_only, false, 'Offline measurement payload must never be installed');
for (const [key, relative] of Object.entries({
  source_sha256: 'CustomDLL/DualWeapon/compositor.c',
  native_basis_sha256: 'CustomDLL/DualWeapon/native_basis.h',
  native_basis_builder_sha256: 'tools/build_dual_weapon_native_basis.py',
  pixel_profile_sha256: 'CustomDLL/DualWeapon/grip_profile.h',
  edge_profile_sha256: 'CustomDLL/DualWeapon/held_edge_contacts.h',
  pixel_annotations_sha256: 'Inputs/DualWeaponAuthored/grips/female-assassin-pixel-landmarks.json',
  male_profile_sha256: 'CustomDLL/DualWeapon/male_profile.h',
  male_source_sha256: 'CustomDLL/DualWeapon/male_compositor.h',
  male_builder_sha256: 'tools/build_male_dual_weapon_profile.py',
  male_seam_builder_sha256: 'tools/male_weapon_seams.py',
  male_asset_builder_sha256: 'tools/male_weapon_assets.py',
  male_asset_report_sha256: 'docs/evidence/dual-weapon-male-missing-assets-20260907.json',
  male_annotations_sha256: 'Inputs/DualWeaponAuthored/grips/male-assassin-landmarks.json',
})) {
  assert.equal(digest(fs.readFileSync(path.resolve(__dirname, '..', relative))), manifest[key], relative + ' is stale relative to the payload');
}
for (const [relative, hash] of Object.entries(manifest.extended_source_hashes)) {
  assert.equal(digest(fs.readFileSync(path.resolve(__dirname, '..', relative))), hash, relative + ' is stale');
}
const assetManifest = JSON.parse(fs.readFileSync(path.resolve(__dirname, '../docs/evidence/assassin-weapon-assets-20260907.json'), 'utf8'));
assert.equal(digest(fs.readFileSync(path.resolve(__dirname, '../Inputs/DualWeaponRuntime/dual_weapon_male_assets.grf'))), assetManifest.grf_sha256);
console.log('PASS: payload, manifest, male/female sources, annotations and generated tables have matching hashes.');
let validFile = true, closes = 0;
context.Warp = { Path: path.resolve(__dirname, '..') };
context.BinFile = class {
  get Valid() { return validFile; }
  ReadHex() { return payload.toString('hex'); }
  Close() { closes++; }
};
context.RagexeClientProfile.Id = 20250716;
assert.ok(check('DualWeaponStatic.readCompositor().codeBytes') > 0);
assert.equal(closes, 1);
payload = Buffer.from(payload);
payload[payload.length - 1] ^= 1;
assert.throws(() => check('AllowDualCustomWeaponSprites(null)'), /CRC mismatch/);
assert.equal(exeAccesses, 0);
validFile = false;
assert.throws(() => check('AllowDualCustomWeaponSprites(null)'), /is missing/);
assert.equal(exeAccesses, 0);
console.log('PASS: external payload loads; corrupt/missing payloads reject before EXE access.');

// Exercise every possible VA page residue, including WARP's physical/VA skew.
// The protected byte range must stay inside the exclusive reservation, and
// therefore cannot touch the immediately adjacent code allocations.
for (let residue = 0; residue < 0x1000; residue++) {
  const physical = 0x100000, virtual = 0x2000000 + residue;
  let reservation = null;
  context.RagexeAllocationStatic.allocate = (size, alignment) => {
    reservation = { size, alignment };
    return [physical, virtual];
  };
  check('DualWeaponStatic.OwnedAllocations = []');
  const [phy, va] = check('DualWeaponStatic.allocateStatePages(0x5000)');
  assert.equal(va % 0x1000, 0);
  assert.equal(phy - physical, va - virtual);
  assert.equal(reservation.size, 0x5fff);
  assert.ok(va >= virtual && va + 0x5000 <= virtual + reservation.size);
  assert.equal(check('DualWeaponStatic.OwnedAllocations[0][1]'), physical + reservation.size);
  // A second allocation in the padding must also be rejected, not just one
  // overlapping the state subrange returned to the caller.
  context.RagexeAllocationStatic.allocate = () => [physical, virtual];
  assert.throws(() => check('DualWeaponStatic.allocateChecked(1, 1)'), /overlaps/);
}
assert.throws(() => check('DualWeaponStatic.allocateStatePages(0x5001)'), /page multiple/);
assert.throws(() => check('DualWeaponStatic.buildEquipHook(0x1e5f000,0x1e5f400,0x1e5f400,0x5000,0x112000,0x1e60400,0x1e5f800)'), /isolated VA pages/);
assert.throws(() => check('DualWeaponStatic.buildEquipHook(0x300010,0x300000,0x300000,0x5000,0x112000,0x301000,0x300400)'), /isolated VA pages/);
console.log('PASS: 4096 VA residues isolate protected pages; padding stays reserved; unsafe owner emission rejected.');
