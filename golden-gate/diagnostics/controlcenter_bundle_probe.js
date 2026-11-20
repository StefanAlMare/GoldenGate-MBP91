// Read the named Wi-Fi resource from the ControlCenter bundle without launching it.
ObjC.import('AppKit');

function run(args) {
    const path = args.length ? args[0] : '/System/Library/CoreServices/ControlCenter.app';
    const bundle = $.NSBundle.bundleWithPath(path);
    return ['wifi.menu.network','wifi.menu.scanning.2'].map(name => inspect(bundle, name)).join('\n');
}

function inspect(bundle, name) {
    const result = {resource: name};
    function finish(state) {
        result.state = state;
        return 'GG_CC_RESOURCE ' + JSON.stringify(result);
    }

    if (bundle.isNil() || ObjC.unwrap(bundle.bundleIdentifier) !== 'com.apple.controlcenter') {
        return finish('bundle-unavailable');
    }
    const image = bundle.imageForResource(name);
    if (image.isNil() || !image.isValid) return finish('image-unavailable');
    result.points = [Number(image.size.width), Number(image.size.height)];
    const data = image.TIFFRepresentation;
    if (data.isNil()) return finish('no-raster');
    const rep = $.NSBitmapImageRep.imageRepWithData(data);
    if (rep.isNil()) return finish('no-raster');
    const width = Number(rep.pixelsWide), height = Number(rep.pixelsHigh);
    result.pixels = [width, height];
    if (!(width > 0 && width <= 256 && height > 0 && height <= 256)) return finish('unexpected-size');

    let covered = 0, nonzero = 0, peak = 0, mask = 2166136261;
    for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
            const alpha = rep.colorAtXY(x, y).alphaComponent;
            nonzero += alpha > 0 ? 1 : 0;
            peak = Math.max(peak, alpha);
            const bit = alpha >= 0.45 ? 1 : 0;
            covered += bit;
            mask = Math.imul(mask ^ bit, 16777619) >>> 0;
        }
    }
    result.nonzero = nonzero;
    result.peakAlpha255 = Math.round(255 * peak);
    result.covered = covered;
    result.mask = ('00000000' + mask.toString(16)).slice(-8);
    return finish(nonzero === 0 ? 'empty' : covered === 0 ? 'faint' :
                  covered === width * height ? 'filled-at-threshold' : 'partial-coverage');
}
