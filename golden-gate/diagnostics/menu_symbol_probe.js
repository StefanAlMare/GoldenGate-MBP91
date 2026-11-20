// Read only. Run as /usr/bin/osascript -l JavaScript menu_symbol_probe.js
ObjC.import('AppKit');
ObjC.import('CoreGraphics');

const side = 32;

function sample(kind, name) {
    const row = {kind: kind, name: name};
    const space = $.CGColorSpaceCreateWithName($.kCGColorSpaceSRGB);
    const bitmap = $.CGBitmapContextCreate(null, side, side, 8, side * 4, space,
        $.kCGImageAlphaPremultipliedLast | $.kCGBitmapByteOrder32Big);
    const bounds = $.NSMakeRect(0, 0, side, side);
    $.CGContextClearRect(bitmap, bounds);
    if (kind === 'control' && name === 'solid-16x16') {
        $.CGContextSetRGBFillColor(bitmap, 1, 1, 1, 1);
        $.CGContextFillRect(bitmap, $.NSMakeRect(8, 8, 16, 16));
    } else if (kind !== 'control') {
        const image = kind === 'sf' ?
            $.NSImage.imageWithSystemSymbolNameAccessibilityDescription(name, name) :
            $.NSImage.imageNamed(name);
        if (!image || image.isNil()) return Object.assign(row, {state: 'unavailable'});
        if (!image.isValid) return Object.assign(row, {state: 'invalid-image'});
        const original = image.size;
        if (!(original.width > 0 && original.height > 0)) return Object.assign(row, {state: 'invalid-size'});
        const scale = (side - 2) / Math.max(original.width, original.height);
        const w = scale * original.width, h = scale * original.height;
        const frame = $.NSMakeRect((side-w)/2, (side-h)/2, w, h);
        $.NSGraphicsContext.saveGraphicsState;
        try {
            $.NSGraphicsContext.setCurrentContext($.NSGraphicsContext.graphicsContextWithCGContextFlipped(bitmap, false));
            image.drawInRectFromRectOperationFraction(frame, $.NSZeroRect, $.NSCompositingOperationSourceOver, 1);
        } finally {
            $.NSGraphicsContext.restoreGraphicsState;
        }
    }

    const rep = $.NSBitmapImageRep.alloc.initWithCGImage($.CGBitmapContextCreateImage(bitmap));
    let nonzero = 0, covered = 0, peak = 0, hash = 2166136261;
    let xMin = side, yMin = side, xMax = -1, yMax = -1;
    for (let y = 0; y < side; y++) {
        for (let x = 0; x < side; x++) {
            const alpha = rep.colorAtXY(x, y).alphaComponent;
            if (alpha > 0) nonzero++;
            if (alpha >= 0.45) {
                covered++;
                xMin = Math.min(xMin,x); xMax = Math.max(xMax,x);
                yMin = Math.min(yMin,y); yMax = Math.max(yMax,y);
            }
            peak = Math.max(peak, alpha);
            hash = Math.imul(hash ^ (alpha >= 0.45 ? 1 : 0), 16777619) >>> 0;
        }
    }
    const solidRectangle = covered > 0 && covered === (xMax-xMin+1)*(yMax-yMin+1);
    const state = nonzero === 0 ? 'empty' : covered === 0 ? 'faint' :
        (kind !== 'control' && solidRectangle) ? 'solid-rectangle' : 'pixels';
    return Object.assign(row, {state: state, nonzero: nonzero, covered: covered,
        peakAlpha255: Math.round(peak*255), mask32: ('00000000'+hash.toString(16)).slice(-8)});
}

function processIdentity() {
    const identity = {pid: Number($.NSProcessInfo.processInfo.processIdentifier), arch: 'unknown', libhao: null};
    try {
        ObjC.bindFunction('_dyld_image_count', ['unsigned int', []]);
        ObjC.bindFunction('_dyld_get_image_header', ['void *', ['unsigned int']]);
        ObjC.bindFunction('_dyld_get_image_name', ['char *', ['unsigned int']]);
        const header = $.NSData.dataWithBytesLength($._dyld_get_image_header(0), 8);
        identity.arch = {'z/rt/gcAAAE=':'x86_64', 'z/rt/gwAAAE=':'arm64'}[
            ObjC.unwrap(header.base64EncodedStringWithOptions(0))] || 'unknown';
        const count = Number($._dyld_image_count());
        if (!(count > 0 && count <= 32768)) return identity;
        let hao = false;
        for (let i = 0; i < count; i++) {
            const path = $._dyld_get_image_name(i);
            if (!path) return identity;
            if (/^libhao(?:\.[^/]+)*\.dylib$/i.test(String(path).split('/').pop())) hao = true;
        }
        if (Number($._dyld_image_count()) === count) identity.libhao = hao;
    } catch (err) { identity.error = String(err.message).slice(0,120); }
    return identity;
}

function run() {
    const requests = [['control','empty'], ['control','solid-16x16'], ['sf','speaker.wave.2.fill'],
        ['sf','wifi'], ['sf','bluetooth'], ['named','NSBluetoothTemplate']];
    const rows = requests.map(([kind,name]) => {
        try { return sample(kind, name); }
        catch (err) { return {kind: kind, name: name, state: 'probe-error', error: String(err.message).slice(0,120)}; }
    });
    const controlsOK = rows[0].nonzero === 0 && rows[1].nonzero === 256 && rows[1].covered === 256;
    return 'GG_SYMBOL_ID '+JSON.stringify(processIdentity())+'\n'+rows.map(row=>'GG_SYMBOL '+JSON.stringify(row)).join('\n') +
        '\nGG_SYMBOL_CONTROLS '+ (controlsOK ? 'PASS' : 'FAIL');
}
