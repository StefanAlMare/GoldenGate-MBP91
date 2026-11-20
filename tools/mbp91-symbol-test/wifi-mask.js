// osascript -l JavaScript wifi-mask.js [32]
// AppKit supplies the silhouette. A Metal client can treat each row as a draw mask.
ObjC.import('AppKit');
ObjC.import('CoreGraphics');

function run(args) {
    const size = 32;
    if (args.length > 1 || (args.length && args[0] !== String(size))) {
        throw Error('The Wi-Fi mask uses a 32-pixel canvas.');
    }
    const image = $.NSImage.imageWithSystemSymbolNameAccessibilityDescription('wifi', 'Wi-Fi');
    if (!image || !image.isValid) throw Error('AppKit could not provide its Wi-Fi symbol.');
    const space = $.CGColorSpaceCreateWithName($.kCGColorSpaceSRGB);
    const bitmap = $.CGBitmapContextCreate(null, size, size, 8, size * 4, space,
        $.kCGImageAlphaPremultipliedLast | $.kCGBitmapByteOrder32Big);
    if (!bitmap) throw Error('Could not create the symbol reference bitmap.');
    const bounds = $.NSMakeRect(0, 0, size, size);
    $.CGContextClearRect(bitmap, bounds);
    const original = image.size;
    const scale = (size - 2) / Math.max(original.width, original.height);
    const width = scale * original.width;
    const height = scale * original.height;
    const frame = $.NSMakeRect((size - width) / 2, (size - height) / 2, width, height);
    const graphics = $.NSGraphicsContext.graphicsContextWithCGContextFlipped(bitmap, false);
    $.NSGraphicsContext.saveGraphicsState;
    try {
        $.NSGraphicsContext.setCurrentContext(graphics);
        image.drawInRectFromRectOperationFraction(frame, $.NSZeroRect, $.NSCompositingOperationSourceOver, 1);
    } finally {
        $.NSGraphicsContext.restoreGraphicsState;
    }
    const rep = $.NSBitmapImageRep.alloc.initWithCGImage($.CGBitmapContextCreateImage(bitmap));
    let pixels = 0;
    const rows = [];
    for (let y = 0; y < size; y++) {
        let row = '';
        for (let x = 0; x < size; x++) {
            const filled = rep.colorAtXY(x, y).alphaComponent >= 0.45;
            row += filled ? '1' : '0';
            if (filled) pixels++;
        }
        rows.push(row);
    }
    if (pixels < size || pixels > size * size * 0.9) {
        throw Error('AppKit produced an empty or implausibly filled Wi-Fi reference.');
    }
    const system = $.NSDictionary.dictionaryWithContentsOfFile('/System/Library/CoreServices/SystemVersion.plist');
    const build = ObjC.unwrap(system.objectForKey('ProductBuildVersion'));
    return JSON.stringify({symbol: 'wifi', size: size, selectedPixels: pixels, rows: rows, systemBuild: build});
}
