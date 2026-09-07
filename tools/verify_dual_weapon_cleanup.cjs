// Verify patch discovery, upstream fallback and wrapper equivalence after cleanup.
// Optional argument: the pre-cleanup QJS for an explicit byte-for-byte comparison.
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
const assert = require('node:assert/strict'), crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const patch = 'AllowDualCustomWeaponSprites';
const source = fs.readFileSync(path.join(root, 'Scripts/Patches', patch + '.qjs'));
assert.equal(source.subarray(0, 2).toString(), '/*');
assert.equal(source.toString().replaceAll('\r\n', '').includes('\n'), false);
const tree = fs.readFileSync(path.join(root, 'Patches/Special.yml'), 'utf8');
assert.match(tree, new RegExp('^ *- ' + patch + ':', 'm'));
assert.doesNotMatch(tree, /^ *- AllowDualWeaponSprites:/m);
const c = vm.createContext({Exe:{BuildDate:20250716, Allocate:()=>[0x2000,0x1802000]}});
vm.runInContext(source.toString(), c);
const check = code => vm.runInContext(code, c);
assert.equal(check('typeof AllowDualCustomWeaponSprites'), 'function');
assert.equal(check('AllowDualCustomWeaponSprites.validate()'), true);
assert.deepEqual(Array.from(check('DualWeaponStatic.allocateChecked(16,16)')), [0x2000,0x1802000]);
assert.throws(()=>check('DualWeaponStatic.allocateChecked(16,16)'),/overlaps/);
c.Exe.BuildDate=20260219;
assert.equal(check('AllowDualCustomWeaponSprites.validate()'), false);
c.Exe.BuildDate=20250716;
assert.equal(check('AllowDualCustomWeaponSprites.validate()'), true);
for (const retired of ['ItemDatabase:', 'buildImageCapture', 'BOH_DWR', 'BOH_DWZ',
                       'OutputDebugStringA', 'GetAsyncKeyState', 'attackCaptureSize'])
  assert.ok(!source.includes(retired), 'Retired source remains: ' + retired);
const comparisons=[];
if (process.argv[2]) {
 const previous=vm.createContext({});
 vm.runInContext(fs.readFileSync(process.argv[2],'utf8'),previous);
 const vector = [
  ['buildScopedDepthDrawThunk',[0x1804000,0x1808000]],
  ['buildVertexDepthBridge',[0x1804000,0x1808000,0xc4a64c]],
  ['buildFinalDrawWrapper',[0x1804000,0x1808000,0x180c000,0x1810000,0x1814000]],
  ['buildEquipEntry',[0x1804000]],
 ];
 for(const [name,args] of vector) {
  let oldName=name,oldArgs=args.slice();
  if(name==='buildFinalDrawWrapper')oldArgs.splice(4,0,0x1900000);
  if(name==='buildEquipEntry'){oldName='buildEquipEntryDiagnostic';oldArgs.push(0x1900000,0x1901000);}
  for(const base of [0x1800000,0x2000000,0x3000000]) {
   const expression=(n,a)=>'DualWeaponStatic.'+n+'('+a.join(',')+').finish('+base+')';
   const actual=check(expression(name,args)),expected=vm.runInContext(expression(oldName,oldArgs),previous);
   assert.equal(actual,expected,name);
   comparisons.push({name,base,bytes:actual.split(' ').length,
    sha256:crypto.createHash('sha256').update(Buffer.from(actual.replaceAll(' ',''),'hex')).digest('hex')});
  }
 }
}
const report={schema:'dual_weapon_cleanup_source/v1',source_sha256:crypto.createHash('sha256').update(source).digest('hex'),
 source_bytes:source.length,longest_line:Math.max(...source.toString().split('\n').map(s=>s.trimEnd().length)),
 patch_entry:patch,tree_file_export_match:true,upstream_profile_and_allocator_fallback:true,
 removed_runtime_debug_and_capture:true,wrapper_comparisons:comparisons};
fs.writeFileSync(path.join(root,'docs/evidence/dual-weapon-cleanup-source-20260907.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({passed:true,...report}));
