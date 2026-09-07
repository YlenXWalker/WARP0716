// Verify extracted support assets and rejection before any EXE access.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict'),crypto=require('node:crypto');
const root=path.resolve(__dirname,'..');
const source=fs.readFileSync(path.join(root,'Scripts/Patches/AllowDualCustomWeaponSprites.qjs'),'utf8');
const manifest=JSON.parse(fs.readFileSync(path.join(root,'Inputs/DualWeaponRuntime/legacy-support.json'),'utf8'));
const sha=b=>crypto.createHash('sha256').update(b).digest('hex');
const original=fs.readFileSync(path.join(root,'Inputs/DualWeaponRuntime/legacy-support.dwls'));
let bundle=Buffer.from(original),missing=false,accesses=0;
const payload=fs.readFileSync(path.join(root,'Inputs/DualWeaponRuntime/compositor.dwcp'));
const c=vm.createContext({RagexeClientProfile:{Id:20250716},Warp:{Path:root},Exe:new Proxy({},{get(){accesses++;throw Error('EXE touched');}}),BinFile:class{
 constructor(name){this.name=name;}
 get Valid(){return !(missing&&this.name.endsWith('.dwls'));}
 ReadHex(){return (this.name.endsWith('.dwls')?bundle:payload).toString('hex');}
 Close(){}
}});
vm.runInContext(source,c);
const current=vm.runInContext('DualWeaponStatic.readLegacyAssets()',c);
assert.equal(sha(original),manifest.sha256);
for(const [part,name] of [['core','DualWeaponAuthoredCore'],['helper','DualWeaponCharacterEnvelopeCore']]){
 const expected=manifest.parts[name],raw=Buffer.from(current[part].hex.replaceAll(' ',''),'hex');
 assert.equal(sha(raw),expected.sha256);assert.equal(raw.length,expected.bytes);
 assert.equal(current[part].entry,expected.entry);assert.equal(current[part].relocs.length,expected.relocations);
 const rel=Buffer.alloc(8*current[part].relocs.length);
 for(const [i,[off,target]] of current[part].relocs.entries()){rel.writeUInt32LE(off,i*8);rel.writeUInt32LE(target,i*8+4);}
 assert.equal(sha(rel),expected.relocations_sha256);
 for(const [address,hash] of Object.entries(expected.relocated_sha256)){
  const a=Buffer.from(raw);
  for(const [off,target] of current[part].relocs)a.writeUInt32LE(Number(address)+target,off);
  assert.equal(sha(a),hash);
 }
}
assert.equal(sha(Buffer.from(current.rigHex.replaceAll(' ',''),'hex')),manifest.parts.DualWeaponAuthoredRig.sha256);
function crc(buf){let n=0xffffffff;for(const x of buf){n^=x;for(let i=0;i<8;i++)n=(n>>>1)^((n&1)?0xedb88320:0);}return (n^0xffffffff)>>>0;}
const failures=[];
function reject(label,edit,repair=false){
 bundle=Buffer.from(original);edit(bundle);
 if(repair)bundle.writeUInt32LE(crc(bundle.subarray(48)),36);
 assert.throws(()=>vm.runInContext('AllowDualCustomWeaponSprites(null)',c),/invalid legacy|CRC mismatch/);
 assert.equal(accesses,0);failures.push(label);
}
reject('bad magic',b=>b[0]^=1);
reject('unsupported version',b=>b.writeUInt32LE(2,4));
reject('length overflow',b=>b.writeUInt32LE(0xffffffff,8));
reject('reserved flags',b=>b.writeUInt32LE(1,40));
reject('bad checksum',b=>b[b.length-1]^=1);
const reloc=48+original.readUInt32LE(8)+original.readUInt32LE(20)+original.readUInt32LE(32);
reject('relocation outside image',b=>b.writeUInt32LE(b.readUInt32LE(8),reloc),true);
reject('relocation target outside image',b=>b.writeUInt32LE(b.readUInt32LE(8),reloc+4),true);
reject('duplicate relocation',b=>b.copy(b,reloc+8,reloc,reloc+8),true);
bundle=Buffer.from(original);missing=true;
assert.throws(()=>vm.runInContext('AllowDualCustomWeaponSprites(null)',c),/is missing/);assert.equal(accesses,0);failures.push('missing file');
const raw=fs.readFileSync(path.join(root,'Scripts/Patches/AllowDualCustomWeaponSprites.qjs'));
assert.equal(raw.subarray(0,2).toString(),'/*');assert.ok(!/(?<!\r)\n/.test(raw.toString()));
assert.ok(source.split(/\r?\n/).every(x=>x.length<500),'giant generated lines remain');
const report={schema:'dual_weapon_legacy_bundle_execution/v1',qjs_before_bytes:manifest.origin.qjs_bytes,qjs_after_bytes:raw.length,largest_line:Math.max(...source.split(/\r?\n/).map(x=>x.length)),bundle_sha256:crypto.createHash('sha256').update(original).digest('hex'),exact_original_bytes:true,exact_435_relocations:true,relocated_base_cases:8,rejections_before_exe_access:failures,exe_accesses:accesses};
fs.writeFileSync(path.join(root,'docs/evidence/dual-weapon-qjs-bundle-20260907.json'),JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify(report));
