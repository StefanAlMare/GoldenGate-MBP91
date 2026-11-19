'use strict';
const {describe,plan,report} = require('./inventar');
const assert = require('node:assert/strict');
const N='A0000001-0000-4000-8000-000000000001';
const X='B0000002-0000-4000-8000-000000000002';
function fixture() {
  const pts = [
    ['disk0s1','EFI'],['disk0s2','Apple_APFS'],['disk0s3','Microsoft Basic Data'],
    ['disk0s4','Windows_Recovery'],['disk0s5','Microsoft Basic Data'],['disk0s6','Microsoft Basic Data']
  ].map(([DeviceIdentifier, Content])=>({DeviceIdentifier, Content}));
  const phys={AllDisksAndPartitions:[{DeviceIdentifier:'disk0',Partitions:pts}]};
  const all={AllDisks:['disk0',...pts.map(p=>p.DeviceIdentifier),'disk2','disk2s1','disk3s1']};
  const infos={disk0:{Internal:true,WholeDisk:true},disk2:{},disk2s1:{},disk3s1:{}};
  for(const p of pts) infos[p.DeviceIdentifier]={ParentWholeDisk:'disk0',Content:p.Content,Mounted:false};
  Object.assign(infos.disk0s3,{FileSystemPersonality:'Windows NT File System',VolumeUUID:N,Mounted:false,VolumeName:'fixture-secret'});
  Object.assign(infos.disk0s6,{FilesystemType:'exfat',VolumeUUID:X.toLowerCase(),Mounted:true,MountPoint:'/Volumes/fixture-secret',Serial:'my-secret'});
  return {infos,phys,all,host:{DeviceIdentifier:'disk2s1s1',Content:'Apple_APFS',FilesystemType:'apfs'},apfs:{Containers:[{ContainerReference:'disk2',PhysicalStores:[{DeviceIdentifier:'disk0s2'}],Volumes:[{DeviceIdentifier:'disk2s1'}]}]}};
}
function go(change) {
    const f=fixture();
    if(change)change(f);
    return describe(f.phys,f.all,f.host,f.apfs,dev=>f.infos[dev]||null);
}
let checks=0;
function trial(fn) {fn(); ++checks;}
trial(()=>assert.equal(plan(go(),['disk0s3','disk0s6']), 'UUID='+N+' none auto ro,noauto 0 0\nUUID='+X+' none auto ro,noauto 0 0'));
trial(()=>assert.doesNotMatch(report(go(),'MacBookPro9,1','x86_64','26B131'), /A0000001|B0000002|secret|\/Volumes/));
trial(()=>assert.match(report(go(),'MacBookPro9,1','x86_64','26B131'),/disk0s6 \| internal \| exFAT \| yes/));
trial(()=>assert.throws(()=>plan(go(),['disk0s5']),/unconfirmed/));
trial(()=>assert.throws(()=>plan(go(),['disk0s1']),/outside the selection/));
trial(()=>assert.throws(()=>plan(go(),['disk0s2']),/APFS backing store/));
trial(()=>assert.throws(()=>plan(go(),['disk0s4']),/outside the selection/));
trial(()=>assert.throws(()=>plan(go(f=>f.infos.disk3s1.VolumeUUID=X),['disk0s6']),/duplicate/));
trial(()=>assert.throws(()=>plan(go(f=>delete f.infos.disk0s6.VolumeUUID),['disk0s6']),/unavailable/));
trial(()=>assert.throws(()=>plan(go(f=>delete f.infos.disk2),['disk0s6']),/incomplete/));
trial(()=>assert.throws(()=>plan(go(f=>delete f.apfs.Containers),['disk0s6']),/identify/));
trial(()=>assert.throws(()=>plan(go(f=>delete f.infos.disk0.Internal),['disk0s6']),/incomplete/));
trial(()=>assert.throws(()=>plan(go(f=>f.infos.disk0.VirtualOrPhysical='Virtual'),['disk0s6']),/incomplete/));
trial(()=>assert.throws(()=>plan(go(f=>f.infos.disk0s6.ParentWholeDisk='disk9'),['disk0s6']),/incomplete/));
trial(()=>assert.throws(()=>plan(go(),['disk0s6','disk0s6']),/distinct/));
trial(()=>assert.throws(()=>plan(go(),[]),/Explicitly/));
trial(()=>assert.throws(()=>plan(go(),['disk0s3','disk0s1']),/outside the selection/));
trial(()=>assert.throws(()=>plan(go(f=>f.apfs.Containers[0].PhysicalStores.push({DeviceIdentifier:'disk0s6'})),['disk0s6']),/APFS backing store/));
trial(()=>assert.throws(()=>plan(go(f=>f.infos.disk0s6.Content='Apple_APFS'),['disk0s6']),/outside the selection/));
trial(()=>assert.throws(()=>plan(go(f=>f.host={DeviceIdentifier:'disk0s6',FilesystemType:'exfat'}),['disk0s6']),/APFS backing store/));
trial(()=>assert.equal(go(f=>f.infos.disk0.Internal=false).rows.find(x=>x.dev==='disk0s3').loc,'extern'));
trial(()=>assert.throws(()=>plan(go(f=>f.infos.disk0s6.FileSystemPersonality='NTFS'),['disk0s6']),/unconfirmed/));
trial(()=>assert.throws(()=>plan(go(f=>f.phys.AllDisksAndPartitions[0].Partitions[5].Content='EFI'),['disk0s6']),/outside the selection/));
trial(()=>assert.match(report(go(),'MacBookPro9,1','x86_64','26B131','ro'), /disk0s6 \| intern \| exFAT \| da/));
trial(()=>assert.throws(()=>plan(go(),['disk0s5'],'ro'),/neconfirmat/));
trial(()=>assert.equal(plan(go(),['disk0s6'],'ro'),plan(go(),['disk0s6'])));
console.log(checks+' inventory fixture checks passed.');
