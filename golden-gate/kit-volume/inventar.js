// JavaScript for Automation. Read macOS property lists via Foundation.
function execute(path, args, plist) {
    const task = $.NSTask.alloc.init;
    const pipe = $.NSPipe.pipe;
    task.launchPath = $(path);
    task.arguments = $(args);
    task.standardOutput = pipe;
    task.standardError = $.NSFileHandle.fileHandleWithNullDevice;
    task.launch;
    const data = pipe.fileHandleForReading.readDataToEndOfFile;
    task.waitUntilExit;
    if (task.terminationStatus !== 0) return null;
    if (plist) {
        const obj = $.NSPropertyListSerialization.propertyListWithDataOptionsFormatError(data, 0, null, null);
        return obj.isNil() ? null : ObjC.deepUnwrap(obj);
    }
    return ObjC.unwrap($.NSString.alloc.initWithDataEncoding(data, $.NSUTF8StringEncoding)).trim();
}

function kind(info, part) {
    const fs = ['FilesystemType', 'FilesystemName', 'FileSystemPersonality', 'TypeBundleName', 'UserVisibleFilesystemName']
        .map(k => String(info[k] || '').toLowerCase()).concat(String(part.FilesystemType || '').toLowerCase()).join(' ');
    const exfat = /\bexfat\b/.test(fs);
    const ntfs = /\bntfs(?:_3g|3g)?\b|\bnt file system\b|\btuxera_ntfs\b/.test(fs);
    const apfs = /\bapfs\b/.test(fs);
    if ((exfat && ntfs) || (apfs && (exfat || ntfs))) return 'metadate contradictorii';
    if (exfat) return 'exFAT';
    if (ntfs) return 'NTFS';
    if (apfs) return 'APFS';
    if (/\bfat(?:12|16|32)?\b|msdos|ms-dos/.test(fs)) return 'FAT';
    return fs.trim() ? 'alt sistem de fișiere' : 'neidentificat';
}

function id(value) {
    return typeof value === 'string' && /^disk[0-9]+(?:s[0-9]+)*$/.test(value) ? value : '';
}

function uuid(value) {
    return typeof value === 'string' && /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value) ? value.toUpperCase() : '';
}

function contentType(value) {
    return String(value || '').toLowerCase().replace(/[ _-]/g, '');
}

function dataPartition(value) {
    return ['microsoftbasicdata', 'windowsntfs', 'windowsfat32', 'windowsfat32(lba)', 'ebd0a0a2b9e5443387c068b6b72699c7'].indexOf(contentType(value)) !== -1;
}

function bootProtection(host, apfs, physicalIds) {
    const target = id(host.DeviceIdentifier);
    const protectedIds = new Set();
    const roots = new Set([id(host.APFSContainerReference), id(host.ParentWholeDisk), (target.match(/^disk[0-9]+/) || [''])[0]]);
    const isAPFS = kind(host, {}) === 'APFS' || !!host.APFSContainerReference || !!host.APFSSnapshotUUID;
    if (isAPFS) {
        const matches = (apfs.Containers || []).filter(c => {
            const vol = (c.Volumes || []).some(v => {
                const dev = id(v.DeviceIdentifier);
                return dev && target && (target === dev || target.indexOf(dev + 's') === 0);
            });
            return vol || (!!id(c.ContainerReference) && roots.has(c.ContainerReference));
        });
        if (matches.length !== 1) return {known:false, ids:protectedIds};
        const stores = matches[0].PhysicalStores || [];
        if (!stores.length || !stores.every(s => physicalIds.has(id(s.DeviceIdentifier))))
            return {known:false, ids:protectedIds};
        stores.forEach(s => protectedIds.add(s.DeviceIdentifier));
    } else if (target && physicalIds.has(target)) {
        protectedIds.add(target);
    } else {
        return {known:false, ids:protectedIds};
    }
    return {known:true, ids:protectedIds};
}

function describe(phys, all, host, apfs, getInfo, lang) {
    const ids = new Set();
    const rows = [];
    const counts = {};
    const allIds = new Set();
    (phys.AllDisksAndPartitions || []).forEach(d => {
        if (!id(d.DeviceIdentifier)) return;
        ids.add(d.DeviceIdentifier);
        (d.Partitions || []).forEach(p => { if (id(p.DeviceIdentifier)) ids.add(p.DeviceIdentifier); });
    });
    const boot = bootProtection(host, apfs, ids);
    let complete = Array.isArray(all.AllDisks) && all.AllDisks.length > 0;
    function census(dev) {
        if (!id(dev) || allIds.has(dev)) return;
        allIds.add(dev);
        const info = getInfo(dev);
        if (!info) { complete = false; return; }
        const fsid = uuid(info.VolumeUUID);
        if (fsid) counts[fsid] = 1 + (counts[fsid] || 0);
    }
    (all.AllDisks || []).forEach(census);
    ids.forEach(census);
    const physical = phys.AllDisksAndPartitions;
    if (!Array.isArray(physical)) throw new Error(translated('Inventarul discurilor fizice este indisponibil.', lang));
    physical.forEach(d => {
        const disk = id(d.DeviceIdentifier);
        if (!disk) return;
        const parent = getInfo(disk) || {};
        const real = parent.WholeDisk === true && parent.VirtualOrPhysical !== 'Virtual' && parent.Virtual !== true;
        const location = parent.Internal === true ? 'intern' : parent.Internal === false ? 'extern' : 'necunoscut';
        const parts = (d.Partitions || []).length ? d.Partitions : [d];
        parts.forEach(p => {
            const dev = id(p.DeviceIdentifier);
            if (!dev) return;
            const info = getInfo(dev) || {};
            const fs = kind(info,p);
            const ct = info.Content || p.Content;
            const fsid = uuid(info.VolumeUUID);
            const mounted = typeof info.Mounted === 'boolean' ? (info.Mounted ? 'da' : 'nu') : (info.MountPoint ? 'da' : '?');
            let reason = '';
            if (boot.ids.has(dev)) reason = 'volum de pornire / suport APFS';
            else if (!dataPartition(ct) || (info.Content && p.Content && (!dataPartition(info.Content) || !dataPartition(p.Content)))) reason = 'tip de partiție în afara selecției';
            else if (fs !== 'NTFS' && fs !== 'exFAT') reason = 'NTFS/exFAT neconfirmat';
            else if (!boot.known) reason = 'suportul sistemului pornit nu a putut fi determinat';
            else if (!real || location === 'necunoscut' || dev === disk || (info.ParentWholeDisk || info.PartOfWhole) !== disk)
                reason = 'identitate fizică incompletă';
            else if (!complete) reason = 'inventar de UUID-uri incomplet';
            else if (!fsid) reason = 'UUID de volum indisponibil';
            else if (counts[fsid] !== 1) reason = 'UUID de volum duplicat sau neverificat';
            rows.push({dev:dev, fs:fs, loc:location, mounted:mounted, reason:reason, fsid:fsid, basic:dataPartition(ct)});
        });
    });
    return {rows:rows, boot:boot.known, complete:complete};
}

// Disk checks use the same values in both languages. Translate at the output boundary.
const english = {
    'metadate contradictorii': 'conflicting metadata',
    'alt sistem de fișiere': 'other filesystem',
    'neidentificat': 'unidentified',
    'intern': 'internal',
    'extern': 'external',
    'necunoscut': 'unknown',
    'da': 'yes',
    'nu': 'no',
    'incomplet': 'incomplete',
    'volum de pornire / suport APFS': 'startup volume / APFS backing store',
    'tip de partiție în afara selecției': 'partition type outside the selection',
    'NTFS/exFAT neconfirmat': 'NTFS/exFAT unconfirmed',
    'suportul sistemului pornit nu a putut fi determinat': 'could not identify the startup system’s backing store',
    'identitate fizică incompletă': 'incomplete physical disk identity',
    'inventar de UUID-uri incomplet': 'incomplete UUID inventory',
    'UUID de volum indisponibil': 'volume UUID unavailable',
    'UUID de volum duplicat sau neverificat': 'duplicate or unverified volume UUID',
    'candidat pentru verificare manuală': 'candidate for manual verification',
    'Inventarul discurilor fizice este indisponibil.': 'Physical disk inventory is unavailable.',
    'Selectează explicit unul sau mai mulți identificatori BSD distincți, de exemplu --plan disk0s3.': 'Explicitly select one or more distinct BSD identifiers, for example --plan disk0s3.',
    ' nu identifică o singură partiție fizică.': ' does not identify a single physical partition.',
    'Inventar Golden Gate • NTFS și exFAT': 'Golden Gate inventory • NTFS and exFAT',
    'Model declarat: ': 'Reported model: ',
    ' | Arhitectură: ': ' | Architecture: ',
    ' | Build macOS: ': ' | macOS build: ',
    'OpenCore poate prezenta un SMBIOS diferit de hardware-ul fizic.': 'OpenCore can report an SMBIOS model different from the physical hardware.',
    'Suport de pornire identificat: ': 'Startup backing store identified: ',
    ' | Inventar UUID disponibil: ': ' | UUID inventory available: ',
    'Dispozitiv | Locație | FS raportat | Montat | Evaluare': 'Device | Location | Reported filesystem | Mounted | Assessment',
    'Dispozitivele diskNsM pot fi renumerotate la repornire. Volumele necunoscute cer verificare separată.': 'Device identifiers (diskNsM) can change after a restart. Check unidentified volumes separately.',
    'diskutil nu a returnat lista discurilor fizice. Rulează din macOS pe calculatorul evaluat.': 'diskutil returned no list of physical disks. Run from macOS on the computer being tested.'
};

function translated(value, lang) {
    return lang === 'ro' ? value : english[value] || value;
}

function plan(inventory, selected, lang) {
    if (!selected.length || (new Set(selected)).size !== selected.length || !selected.every(id))
        throw new Error(translated('Selectează explicit unul sau mai mulți identificatori BSD distincți, de exemplu --plan disk0s3.', lang));
    return selected.map(dev => {
        const matches = inventory.rows.filter(r => r.dev === dev);
        if (matches.length !== 1) throw new Error(dev + translated(' nu identifică o singură partiție fizică.', lang));
        const r = matches[0];
        if (r.reason) throw new Error(dev + ' — ' + translated(r.reason, lang) + '.');
        return 'UUID=' + r.fsid + ' none auto ro,noauto 0 0';
    }).join('\n');
}

function report(inventory, model, arch, build, lang) {
    const t = value => translated(value, lang);
    const lines = [
        t('Inventar Golden Gate • NTFS și exFAT'),
        t('Model declarat: ') + model + t(' | Arhitectură: ') + arch + t(' | Build macOS: ') + build,
        t('OpenCore poate prezenta un SMBIOS diferit de hardware-ul fizic.'),
        t('Suport de pornire identificat: ') + t(inventory.boot ? 'da' : 'nu') +
            t(' | Inventar UUID disponibil: ') + t(inventory.complete ? 'da' : 'incomplet'),
        t('Dispozitiv | Locație | FS raportat | Montat | Evaluare')
    ];
    inventory.rows.forEach(r => {
        lines.push([r.dev, t(r.loc), t(r.fs), t(r.mounted), t(r.reason || 'candidat pentru verificare manuală')].join(' | '));
    });
    lines.push(t('Dispozitivele diskNsM pot fi renumerotate la repornire. Volumele necunoscute cer verificare separată.'));
    return lines.join('\n');
}

function run(argv) {
    ObjC.import('Foundation');
    let lang = 'en';
    if (argv[0] === '--lang') {
        lang = argv[1];
        if (lang !== 'ro' && lang !== 'en') throw new Error('Expected --lang en or --lang ro.');
        argv = argv.slice(2);
    }
    const usage = (lang === 'ro' ? 'Utilizare' : 'Usage') + ': Inventar.command [--lang en|ro] [--plan diskNsM ...]';
    if (argv.length === 1 && argv[0] === '--help') return usage;
    if (argv.length && argv[0] !== '--plan') throw new Error(usage);
    const cache = {};
    function plist(args) { return execute('/usr/sbin/diskutil', args, true); }
    function info(dev) {
        if (!(dev in cache)) cache[dev] = plist(['info','-plist',dev]);
        return cache[dev];
    }
    const physical = plist(['list','-plist','physical']);
    if (!physical) throw new Error(translated('diskutil nu a returnat lista discurilor fizice. Rulează din macOS pe calculatorul evaluat.', lang));
    const inventory = describe(physical, plist(['list','-plist']) || {}, info('/') || {}, plist(['apfs','list','-plist']) || {}, info, lang);
    if (argv.length) return plan(inventory,argv.slice(1),lang);
    const model = execute('/usr/sbin/sysctl',['-n','hw.model'],false) || '?';
    const arch = execute('/usr/bin/uname',['-m'],false) || '?';
    const build = execute('/usr/bin/sw_vers',['-buildVersion'],false) || '?';
    return report(inventory,model,arch,build,lang);
}
if (typeof module !== 'undefined') module.exports = {kind, describe, plan, report, bootProtection};
