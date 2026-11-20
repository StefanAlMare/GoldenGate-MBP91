// Run with osascript -l JavaScript, intel|nvidia, a precompiled probe.metallib and a Wi-Fi mask.
ObjC.import("Foundation");
ObjC.import("Metal");

const side = 32;
const rowStride = 256;
// Stable public Metal enum values. Some installations expose the functions
// but omit constants and classes from JavaScript for Automation's $ namespace.
const mtl = {
    rgba8Unorm:70, texture2D:2, storagePrivate:2, renderTarget:4, shaderRead:1,
    store:1, clear:2, load:1, triangle:3, resourceStorageManaged:16, completed:4
};
const descriptorClasses = {};

function emit(value) {
    const text = $(JSON.stringify(value) + "\n");
    $.NSFileHandle.fileHandleWithStandardOutput.writeData(text.dataUsingEncoding($.NSUTF8StringEncoding));
}

function present(object) { return object !== undefined && object !== null && !object.isNil(); }

function need(object, label, outError) {
    if (present(object)) return object;
    const error = outError ? outError[0] : null;
    const e = Error(label + (present(error) ? ": " + ObjC.unwrap(error.localizedDescription) : ": unavailable"));
    if (present(error)) {
        e.nativeDomain = String(ObjC.unwrap(error.domain));
        e.nativeCode = Number(error.code);
    }
    throw e;
}

function metalDescriptor(name) {
    let cls = descriptorClasses[name];
    if (!cls) {
        cls = $.NSClassFromString(name);
        if (!present(cls)) {
            const bundle = need($.NSBundle.bundleWithPath("/System/Library/Frameworks/Metal.framework"), "Metal framework");
            const error = Ref();
            if (!bundle.loadAndReturnError(error)) need(null, "Load Metal framework for " + name, error);
            cls = $.NSClassFromString(name);
        }
        if (!present(cls)) throw Error("Objective-C runtime cannot find public Metal class " + name);
        descriptorClasses[name] = cls;
    }
    return need(cls.alloc.init, name + " allocation");
}

function copyRegion() {
    const origin = typeof $.MTLOriginMake === "function" ? $.MTLOriginMake(0,0,0) : {x:0,y:0,z:0};
    const size = typeof $.MTLSizeMake === "function" ? $.MTLSizeMake(side,side,1) : {width:side,height:side,depth:1};
    return {origin:origin,size:size};
}

function decode64(text) {
    const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/";
    const result = [];
    let value = 0, bits = 0;
    for (let i = 0; i < text.length; i++) {
        if (text[i] === "=") break;
        const n = alphabet.indexOf(text[i]);
        if (n < 0) throw Error("Malformed GPU readback encoding");
        value = (value << 6) | n;
        bits += 6;
        if (bits >= 8) {
            bits -= 8;
            result.push((value >> bits) & 255);
            value &= (1 << bits) - 1;
        }
    }
    return result;
}

function validateMask(mask) {
    if (mask.symbol !== "wifi" || mask.size !== side || !Array.isArray(mask.rows) ||
            mask.rows.length !== side || mask.rows.some(row => !/^[01]{32}$/.test(row)))
        throw Error("Expected 32 rows of 32 binary pixels from the Wi-Fi symbol");
    const count = mask.rows.join("").split("1").length - 1;
    if (count < 16 || count > side*side-16 || count !== mask.selectedPixels)
        throw Error("Invalid Wi-Fi foreground size");
    return mask;
}

// The first stage writes seed(p,0) into an RGBA8Unorm target. Only on symbol
// pixels the second shader reads its quantised colour, adds 1/16 and stores it.
function expected(x, y, selected) {
    return [.125, .25, .375, .5].map(function (base) {
        const seedByte = Math.round(255 * (base + ((x + 3*y) % 4) / 32));
        return selected ? Math.round(seedByte + 255 / 16) : seedByte;
    });
}

function compare(bytes, mask) {
    if (bytes.length !== side * rowStride) throw Error("Unexpected GPU readback length");
    let inside = 0, outside = 0, maxError = 0, firstMismatch = null;
    for (let y = 0; y < side; y++) {
        for (let x = 0; x < side; x++) {
            const selected = mask.rows[y][x] === "1";
            const target = expected(x,y,selected);
            const offset = y * rowStride + 4 * x;
            const pixel = bytes.slice(offset, offset + 4);
            const delta = Math.max.apply(null, target.map((n,c) => Math.abs(n-pixel[c])));
            maxError = Math.max(maxError, delta);
            if (delta <= 1) {
                if (selected) inside++; else outside++;
            } else if (firstMismatch === null) firstMismatch = {x:x,y:y,expected:target,actual:pixel};
        }
    }
    return {status:inside+outside === side*side ? "PASS" : "MISMATCH",
        matched:inside+outside, pixels:side*side, matchedInside:inside, matchedOutside:outside,
        maxChannelError:maxError, firstMismatch:firstMismatch};
}

function spans(mask, emitSpan) {
    for (let y=0; y<side; y++) {
        const row = mask.rows[y];
        let x=0;
        while (x<side) {
            if (row[x] === "0") { x++; continue; }
            const first = x++;
            while (x<side && row[x] === "1") x++;
            emitSpan({x:first,y:y,width:x-first,height:1});
        }
    }
}

function pipeline(device, library, fragment) {
    const descriptor = metalDescriptor("MTLRenderPipelineDescriptor");
    descriptor.vertexFunction = need(library.newFunctionWithName("fullscreen"), "fullscreen vertex shader");
    descriptor.fragmentFunction = need(library.newFunctionWithName(fragment), fragment + " fragment shader");
    descriptor.colorAttachments.objectAtIndexedSubscript(0).pixelFormat = mtl.rgba8Unorm;
    const error = Ref();
    const state = device.newRenderPipelineStateWithDescriptorError(descriptor,error);
    try { return need(state, fragment + " render pipeline", error); }
    catch (failure) { failure.pipeline = fragment; throw failure; }
}

function textureDescriptor() {
    const desc = metalDescriptor("MTLTextureDescriptor");
    desc.textureType = mtl.texture2D;
    desc.pixelFormat = mtl.rgba8Unorm;
    desc.width = side;
    desc.height = side;
    desc.storageMode = mtl.storagePrivate;
    desc.usage = mtl.renderTarget | mtl.shaderRead;
    return desc;
}

function texture(device) {
    return need(device.newTextureWithDescriptor(textureDescriptor()), "GPU texture");
}

function draw(cmd, output, load, state, readTexture, mask) {
    const pass = metalDescriptor("MTLRenderPassDescriptor");
    const color = pass.colorAttachments.objectAtIndexedSubscript(0);
    color.texture = output;
    color.loadAction = load;
    color.storeAction = mtl.store;
    const enc = need(cmd.renderCommandEncoderWithDescriptor(pass), "render encoder");
    enc.setRenderPipelineState(state);
    if (readTexture !== null) enc.setFragmentTextureAtIndex(readTexture,0);
    const triangle=mtl.triangle;
    if (mask === null) enc.drawPrimitivesVertexStartVertexCount(triangle,0,3);
    else spans(mask, function (rect) {
        enc.setScissorRect(rect);
        enc.drawPrimitivesVertexStartVertexCount(triangle,0,3);
    });
    enc.endEncoding;
}

function renderCase(device, library, writer, queue, mode, mask) {
    const state = pipeline(device, library, mode === "texture-control" ? "texture0" : "fetch0");
    const source = texture(device);
    const output = mode === "texture-control" ? texture(device) : source;
    const n = side * rowStride;
    const buffer = need(device.newBufferWithLengthOptions(n,mtl.resourceStorageManaged), "readback buffer");
    const cmd = need(queue.commandBuffer, "command buffer");
    draw(cmd, source, mtl.clear, writer, null, null);
    if (mode === "texture-control") {
        draw(cmd, output, mtl.clear, writer, null, null);
        draw(cmd, output, mtl.load, state, source, mask);
    } else draw(cmd, output, mtl.load, state, null, mask);

    const blit = need(cmd.blitCommandEncoder, "readback encoder");
    const region = copyRegion();
    blit.copyFromTextureSourceSliceSourceLevelSourceOriginSourceSizeToBufferDestinationOffsetDestinationBytesPerRowDestinationBytesPerImage(
        output,0,0,region.origin,region.size,buffer,0,rowStride,n);
    blit.synchronizeResource(buffer);
    blit.endEncoding;
    cmd.commit;
    const deadline = Date.now() + 15000;
    while (Number(cmd.status) < mtl.completed && Date.now() < deadline)
        $.NSThread.sleepForTimeInterval(.05);
    if (Number(cmd.status) !== mtl.completed) {
        const error = cmd.error;
        throw Error("GPU completion status " + String(cmd.status) +
            (present(error) ? ": " + ObjC.unwrap(error.localizedDescription) : " (time limit or incomplete)"));
    }
    const data = need($.NSData.dataWithBytesLength(buffer.contents,n), "readback bytes");
    const result=compare(decode64(ObjC.unwrap(data.base64EncodedStringWithOptions(0))),mask);
    const packed=$.NSMutableData.dataWithCapacity(side*side*4);
    for (let y=0;y<side;y++) packed.appendData(data.subdataWithRange($.NSMakeRange(y*rowStride,side*4)));
    result.rgbaBase64=ObjC.unwrap(packed.base64EncodedStringWithOptions(0));
    return result;
}

function run(args) {
    if (args.length === 1 && args[0] === "--bridge-test") {
        const result = {event:"bridge-test",status:"INCONCLUSIVE",lookup:"NSClassFromString",classes:[]};
        try {
            const descriptor = metalDescriptor("MTLRenderPipelineDescriptor");
            const attachment = descriptor.colorAttachments.objectAtIndexedSubscript(0);
            attachment.pixelFormat = mtl.rgba8Unorm;
            if (Number(attachment.pixelFormat)!==mtl.rgba8Unorm) throw Error("Pipeline attachment format");
            result.classes.push("MTLRenderPipelineDescriptor");
            const tex = textureDescriptor();
            if (Number(tex.width)!==side || Number(tex.height)!==side ||
                    Number(tex.pixelFormat)!==mtl.rgba8Unorm || Number(tex.usage)!==(mtl.renderTarget|mtl.shaderRead))
                throw Error("Texture descriptor properties");
            result.classes.push("MTLTextureDescriptor");
            const pass = metalDescriptor("MTLRenderPassDescriptor");
            const color = pass.colorAttachments.objectAtIndexedSubscript(0);
            color.loadAction = mtl.load;
            color.storeAction = mtl.store;
            if (Number(color.loadAction)!==mtl.load || Number(color.storeAction)!==mtl.store) throw Error("Pass descriptor actions");
            result.classes.push("MTLRenderPassDescriptor");
            const region = copyRegion();
            if (Number(region.origin.z)!==0 || Number(region.size.width)!==side || Number(region.size.depth)!==1)
                throw Error("Blit region fields");
            result.status="PASS";
        } catch(error) { result.reason = String(error); }
        emit(result);
        return;
    }
    if (args.length === 1 && args[0] === "--self-test") {
        const row="0".repeat(8)+"1".repeat(16)+"0".repeat(8);
        const mask=validateMask({symbol:"wifi",size:side,selectedPixels:16*side,rows:new Array(side).fill(row)});
        const bytes = new Array(side*rowStride).fill(0);
        for (let y=0; y<side; y++) for (let x=0; x<side; x++)
            expected(x,y,row[x]==="1").forEach((n,c) => {bytes[y*rowStride+4*x+c]=n;});
        let area=0; spans(mask,r=>{area+=r.width*r.height;});
        if (compare(bytes,mask).status !== "PASS" || area!==mask.selectedPixels)
            throw Error("Synthetic reference or span comparison");
        bytes[rowStride+4*8]+=8;
        const bad=compare(bytes,mask);
        if (bad.matchedInside!==mask.selectedPixels-1 || bad.matchedOutside!==side*side-mask.selectedPixels ||
                decode64("AAH+/w==").join() !== "0,1,254,255") throw Error("Synthetic error comparison");
        emit({event:"self-test",status:"PASS",scope:"CPU comparator, mask spans and Base64 decoding only"});
        return;
    }
    if (args.length !== 3 || !["intel","nvidia"].includes(args[0]))
        throw Error("Usage: metal-render.js intel|nvidia path/to/probe.metallib path/to/wifi-mask.json");
    const key=args[0], file=args[1], maskPath=args[2];
    const parsed=need($.NSData.dataWithContentsOfFile(maskPath),"Wi-Fi mask");
    const mask=validateMask(JSON.parse(ObjC.unwrap($.NSString.alloc.initWithDataEncoding(parsed,$.NSUTF8StringEncoding))));
    if (!$.NSFileManager.defaultManager.isReadableFileAtPath(file)) throw Error("Cannot read probe.metallib");

    const info={event:"gpu-render",key:key,name:null,registryID:null,width:side,height:side,
        pixelFormat:"RGBA8Unorm",selectedPixels:mask.selectedPixels,cases:[]};
    const devices=$.MTLCopyAllDevices();
    const matches=[];
    for (let i=0; i<Number(devices.count); i++) {
        const d=devices.objectAtIndex(i), name=ObjC.unwrap(d.name);
        if ((key==="intel" ? /HD Graphics 4000/i : /GeForce GT 650M/i).test(name)) matches.push(d);
    }
    const modes=["texture-control","framebuffer-read"];
    const device=matches[0];
    let library,writer,queue;
    try {
        if (matches.length!==1) throw Error("Expected precisely one "+key+" device; enumerated matches="+matches.length);
        info.name=ObjC.unwrap(device.name);
        info.registryID=String(device.registryID);
        if (!info.registryID || info.registryID==="0") throw Error("Missing device registry ID");
        const error=Ref();
        library=need(device.newLibraryWithURLError($.NSURL.fileURLWithPath(file),error),"precompiled library",error);
        writer=pipeline(device,library,"initial0");
        queue=need(device.newCommandQueue,"command queue");
    } catch(error) {
        info.cases=modes.map(mode=>({mode:mode,status:"INCONCLUSIVE",reason:String(error)}));
        emit(info);
        return;
    }
    for (const mode of modes) {
        try { info.cases.push(Object.assign({mode:mode},renderCase(device,library,writer,queue,mode,mask))); }
        catch(error) {
            info.cases.push({mode:mode,status:"INCONCLUSIVE",reason:String(error),
                pipeline:error.pipeline, nativeDomain:error.nativeDomain, nativeCode:error.nativeCode});
        }
    }
    emit(info);
}
