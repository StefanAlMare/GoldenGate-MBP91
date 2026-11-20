// Run with osascript -l JavaScript in the console user's Aqua session.
// --prepare-only checks the images without registering a status item.
ObjC.import('AppKit');
ObjC.import('CoreGraphics');

function menuTemplate(image) {
    if (!image || image.isNil() || !image.isValid) throw Error('Imagine AppKit indisponibilă.');
    const copy = image.copy;
    const size = copy.size;
    if (!(size.width > 0 && size.height > 0)) throw Error('Dimensiune de imagine nevalidă.');
    const scale = 16 / Math.max(size.width, size.height);
    copy.size = $.NSMakeSize(scale * size.width, scale * size.height);
    copy.template = true;
    return copy;
}

function opaqueWiFi(wifi) {
    const side = 32;
    const bounds = $.NSMakeRect(0, 0, side, side);
    const space = $.CGColorSpaceCreateWithName($.kCGColorSpaceSRGB);
    const bitmap = $.CGBitmapContextCreate(null, side, side, 8, 4 * side, space,
        $.kCGImageAlphaPremultipliedLast | $.kCGBitmapByteOrder32Big);
    if (!bitmap) throw Error('Bitmap indisponibil.');
    $.CGContextClearRect(bitmap, bounds);
    const size = wifi.size, scale = 28 / Math.max(size.width, size.height);
    const w = scale * size.width, h = scale * size.height;
    $.NSGraphicsContext.saveGraphicsState;
    try {
        $.NSGraphicsContext.setCurrentContext($.NSGraphicsContext.graphicsContextWithCGContextFlipped(bitmap, false));
        wifi.drawInRectFromRectOperationFraction($.NSMakeRect((side-w)/2, (side-h)/2, w, h),
            $.NSZeroRect, $.NSCompositingOperationSourceOver, 1);
    } finally {
        $.NSGraphicsContext.restoreGraphicsState;
    }
    $.CGContextSetBlendMode(bitmap, $.kCGBlendModeSourceIn);
    $.CGContextSetRGBFillColor(bitmap, 0, 0, 0, 1);
    $.CGContextFillRect(bitmap, bounds);
    $.CGContextSetBlendMode(bitmap, $.kCGBlendModeDestinationOver);
    $.CGContextSetRGBFillColor(bitmap, 1, 1, 1, 1);
    $.CGContextFillRect(bitmap, bounds);
    const result = $.CGBitmapContextCreateImage(bitmap);
    const rep = $.NSBitmapImageRep.alloc.initWithCGImage(result);
    let dark = 0, light = 0;
    for (let y = 0; y < side; y++) {
        for (let x = 0; x < side; x++) {
            const c = rep.colorAtXY(x, y);
            if (c.alphaComponent < 0.99) throw Error('Bitmapul de control conține transparență.');
            if (c.redComponent < 0.25) dark++;
            if (c.redComponent > 0.75) light++;
        }
    }
    if (dark < 10 || light < 100) throw Error('Semnul Wi-Fi și fundalul nu se disting în bitmap.');
    const image = $.NSImage.alloc.initWithCGImageSize(result, $.NSMakeSize(16, 16));
    image.template = false;
    return {image: image, dark: dark, light: light};
}

function run(args) {
    const prepare = args.length === 1 && args[0] === '--prepare-only';
    if (args.length && !prepare) throw Error('Argument acceptat: --prepare-only.');
    const wifi = menuTemplate($.NSImage.imageWithSystemSymbolNameAccessibilityDescription('wifi', 'Wi-Fi'));
    const bluetooth = menuTemplate($.NSImage.imageNamed('NSBluetoothTemplate'));
    const sound = menuTemplate($.NSImage.imageWithSystemSymbolNameAccessibilityDescription('speaker.wave.2.fill', 'Sunet'));
    const tile = opaqueWiFi(wifi);
    const phases = [['GG1', 'Wi-Fi', wifi], ['GG2', 'Bluetooth', bluetooth],
        ['GG3', 'Sunet', sound], ['GG4', 'Wi-Fi negru pe pătrat alb', tile.image]];
    console.log('GG_STATUS_BITMAP dark=' + tile.dark + ' light=' + tile.light);
    if (prepare) return 'GG_STATUS_PREPARAT';
    const app = $.NSApplication.sharedApplication;
    app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);
    app.finishLaunching;
    const bar = $.NSStatusBar.systemStatusBar;
    const item = bar.statusItemWithLength(64);
    if (!item || item.isNil()) throw Error('NSStatusBar nu a creat elementul.');
    try {
        const button = item.button;
        if (!button || button.isNil()) throw Error('Elementul nu are buton AppKit.');
        button.imagePosition = $.NSImageLeft;
        for (const phase of phases) {
            button.title = phase[0];
            button.image = phase[2];
            button.displayIfNeeded;
            app.updateWindows;
            console.log('GG_STATUS_FAZA ' + phase[0] + ' ' + phase[1] + ' | 8 s');
            $.NSRunLoop.currentRunLoop.runUntilDate($.NSDate.dateWithTimeIntervalSinceNow(8));
        }
    } finally {
        bar.removeStatusItem(item);
    }
    return 'GG_STATUS_FINAL element temporar retras; vizibilitatea se confirmă pe ecran.';
}
