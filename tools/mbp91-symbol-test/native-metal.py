"""Golden Gate offscreen Metal probe for a native x86_64 Python on macOS."""
import base64
import ctypes as C
import functools
import json
from pathlib import Path
import re
import sys
import time


# Public macOS Metal enum values, from the Metal framework headers.
RGBA8_UNORM, PRIVATE, MANAGED_BUFFER = 70, 2, 1 << 4
SHADER_READ, RENDER_TARGET = 1, 4
LOAD, CLEAR, STORE, TRIANGLE, COMPLETED = 1, 2, 1, 3, 4
SIZE, STRIDE = 32, 256
MODES = ("texture-control", "framebuffer-read")
NAMES = {"intel": "Intel HD Graphics 4000", "nvidia": "NVIDIA GeForce GT 650M"}
P, U, I, BOOL, CHAR = C.c_void_p, C.c_ulong, C.c_long, C.c_byte, C.c_char_p
ERROR_OUT = C.POINTER(P)


class MTLScissorRect(C.Structure):
    _fields_ = [(name, U) for name in ("x", "y", "width", "height")]


class MTLOrigin(C.Structure):
    _fields_ = [(name, U) for name in ("x", "y", "z")]


class MTLSize(C.Structure):
    _fields_ = [(name, U) for name in ("width", "height", "depth")]


class NSRange(C.Structure):
    _fields_ = [("location", U), ("length", U)]


class ProbeError(Exception):
    def __init__(self, reason, **details):
        super().__init__(reason)
        self.details = details

    def record(self, mode):
        return dict(mode=mode, status="INCONCLUSIVE", reason=str(self), **self.details)


def required(obj, label):
    if not obj:
        raise ProbeError(label + " unavailable")
    return obj


def native_x86_64():
    # Read the loaded main executable's Mach-O header (the active process slice).
    libc = C.CDLL("/usr/lib/libSystem.B.dylib")
    header = libc._dyld_get_image_header
    header.argtypes, header.restype = [C.c_uint32], C.POINTER(C.c_uint32)
    fields = header(0)
    return bool(fields and fields[0] == 0xfeedfacf and fields[1] == 0x01000007 and C.sizeof(P) == 8)


def framebuffer_adapter_mapped():
    try:
        libc = C.CDLL("/usr/lib/libSystem.B.dylib")
        count, name = libc._dyld_image_count, libc._dyld_get_image_name
        count.argtypes, count.restype = [], C.c_uint32
        name.argtypes, name.restype = [C.c_uint32], CHAR
        for index in range(count()):
            path = name(index)
            if path and path.rsplit(b"/", 1)[-1] == b"libmetal-framebuffer.dylib":
                return True
        return False
    except (AttributeError, OSError):
        return None


class ObjC:
    def __init__(self):
        self.objc = C.CDLL("/usr/lib/libobjc.A.dylib")
        frameworks = "/System/Library/Frameworks"
        self.foundation = C.CDLL(frameworks + "/Foundation.framework/Foundation")
        self.metal = C.CDLL(frameworks + "/Metal.framework/Metal")
        for method in (self.objc.sel_registerName, self.objc.objc_getClass):
            method.argtypes, method.restype = [CHAR], P
        self.metal.MTLCopyAllDevices.argtypes = []
        self.metal.MTLCopyAllDevices.restype = P
        self.address = C.cast(self.objc.objc_msgSend, P).value

    @functools.lru_cache(None)
    def selector(self, name):
        return self.objc.sel_registerName(name.encode("ascii"))

    @functools.lru_cache(None)
    def cls(self, name):
        return required(self.objc.objc_getClass(name.encode("ascii")), name)

    @functools.lru_cache(None)
    def method(self, result_type, argument_types):
        # Each call has a fixed signature. libffi implements the x86_64
        # passing rules for the rect, origin and size structs taken by value.
        return C.CFUNCTYPE(result_type, P, P, *argument_types)(self.address)

    def send(self, obj, name, result=P, types=(), *values):
        return self.method(result, types)(obj, self.selector(name), *values)

    def owned(self, obj, label):
        return self.send(required(obj, label), "autorelease")

    def string(self, text):
        return required(self.send(self.cls("NSString"), "stringWithUTF8String:", P,
                                  (CHAR,), text.encode("utf-8")), "NSString")

    def text(self, obj):
        value = self.send(obj, "UTF8String", CHAR) if obj else None
        return value.decode("utf-8", "replace") if value else ""

    def error(self, label, ns_error=None, **details):
        if ns_error:
            description = self.text(self.send(ns_error, "localizedDescription"))
            domain = self.text(self.send(ns_error, "domain"))
            if domain:
                details.update(nativeDomain=domain, nativeCode=self.send(ns_error, "code", I))
            if description:
                label += ": " + description
        return ProbeError(label, **details)

    def collect_devices(self):
        devices = self.owned(self.metal.MTLCopyAllDevices(), "MTLCopyAllDevices")
        return [self.send(devices, "objectAtIndex:", P, (U,), i)
                for i in range(self.send(devices, "count", U))]

    def texture_descriptor(self):
        desc = required(self.send(self.cls("MTLTextureDescriptor"),
                        "texture2DDescriptorWithPixelFormat:width:height:mipmapped:", P,
                        (U, U, U, BOOL), RGBA8_UNORM, SIZE, SIZE, False), "texture descriptor")
        self.send(desc, "setStorageMode:", None, (U,), PRIVATE)
        self.send(desc, "setUsage:", None, (U,), SHADER_READ | RENDER_TARGET)
        return desc

    def pipeline_descriptor(self):
        desc = self.owned(self.send(self.cls("MTLRenderPipelineDescriptor"), "new"), "pipeline descriptor")
        self.send(self.attachment(desc), "setPixelFormat:", None, (U,), RGBA8_UNORM)
        return desc

    def attachment(self, desc):
        return required(self.send(self.send(desc, "colorAttachments"), "objectAtIndexedSubscript:",
                                  P, (U,), 0), "color attachment")

    def pass_descriptor(self, load, texture=None):
        desc = required(self.send(self.cls("MTLRenderPassDescriptor"), "renderPassDescriptor"), "render pass")
        color = self.attachment(desc)
        self.send(color, "setTexture:", None, (P,), texture)
        self.send(color, "setLoadAction:", None, (U,), load)
        self.send(color, "setStoreAction:", None, (U,), STORE)
        return desc

    def shader_library(self, gpu, path):
        url = self.send(self.cls("NSURL"), "fileURLWithPath:", P, (P,), self.string(str(path)))
        error = P()
        library = self.send(gpu, "newLibraryWithURL:error:", P, (P, ERROR_OUT), url, C.byref(error))
        if not library:
            raise self.error("Could not load precompiled shader library", error)
        return self.owned(library, "shader library")

    def pipeline(self, gpu, library, fragment):
        desc = self.pipeline_descriptor()
        for setter, name in (("setVertexFunction:", "fullscreen"), ("setFragmentFunction:", fragment)):
            fn = self.send(library, "newFunctionWithName:", P, (P,), self.string(name))
            self.send(desc, setter, None, (P,), self.owned(fn, name + " shader"))
        error = P()
        state = self.send(gpu, "newRenderPipelineStateWithDescriptor:error:", P,
                          (P, ERROR_OUT), desc, C.byref(error))
        if not state:
            raise self.error(fragment + " pipeline creation failed", error, pipeline=fragment)
        return self.owned(state, "render pipeline")

    def draw(self, command, destination, action, state, source=None, rects=None, texture_index=0):
        desc = self.pass_descriptor(action, destination)
        encoder = required(self.send(command, "renderCommandEncoderWithDescriptor:", P,
                                     (P,), desc), "render encoder")
        self.send(encoder, "setRenderPipelineState:", None, (P,), state)
        if source:
            self.send(encoder, "setFragmentTexture:atIndex:", None, (P, U), source, texture_index)
        for rect in rects if rects is not None else (None,):
            if rect is not None:
                self.send(encoder, "setScissorRect:", None, (MTLScissorRect,), rect)
            self.send(encoder, "drawPrimitives:vertexStart:vertexCount:", None,
                      (U, U, U), TRIANGLE, 0, 3)
        self.send(encoder, "endEncoding", None)

    def render(self, gpu, library, writer, queue, mode, rows, *,
               shader=None, texture_index=0, prepare_destination=None):
        control = mode == "texture-control"
        if shader is None:
            shader = self.pipeline(gpu, library, "texture0" if control else "fetch0")
        desc = self.texture_descriptor()
        source = self.owned(self.send(gpu, "newTextureWithDescriptor:", P, (P,), desc), "source texture")
        output = (self.owned(self.send(gpu, "newTextureWithDescriptor:", P, (P,), desc),
                             "destination texture") if control else source)
        if control and output == source:
            raise ProbeError("Source and destination must be distinct textures")
        length = STRIDE * SIZE
        buffer = self.owned(self.send(gpu, "newBufferWithLength:options:", P,
                            (U, U), length, MANAGED_BUFFER), "readback buffer")
        addr = required(self.send(buffer, "contents"), "readback address")
        C.memset(addr, 0xcd, length)
        self.send(buffer, "didModifyRange:", None, (NSRange,), NSRange(0, length))
        command = required(self.send(queue, "commandBuffer"), "command buffer")
        self.draw(command, source, CLEAR, writer)
        if prepare_destination is not None:
            prepare_destination(self, gpu, command, output, rows)
        elif control:
            self.draw(command, output, CLEAR, writer)
        self.draw(command, output, LOAD, shader, source if control else None, spans(rows), texture_index)
        blit = required(self.send(command, "blitCommandEncoder"), "blit encoder")
        self.send(blit, "copyFromTexture:sourceSlice:sourceLevel:sourceOrigin:sourceSize:"
                  "toBuffer:destinationOffset:destinationBytesPerRow:destinationBytesPerImage:", None,
                  (P, U, U, MTLOrigin, MTLSize, P, U, U, U),
                  output, 0, 0, MTLOrigin(0, 0, 0), MTLSize(SIZE, SIZE, 1), buffer, 0, STRIDE, length)
        self.send(blit, "synchronizeResource:", None, (P,), buffer)
        self.send(blit, "endEncoding", None)
        self.send(command, "commit", None)
        deadline = time.monotonic() + 15
        while True:
            status = self.send(command, "status", U)
            if status >= COMPLETED:
                break
            if time.monotonic() >= deadline:
                raise ProbeError("Metal command timed out before completion", timedOut=True)
            time.sleep(.05)
        if status != COMPLETED:
            raise self.error("GPU command failed (status %d)" % status, self.send(command, "error"))
        packed = b"".join(C.string_at(addr + y*STRIDE, SIZE*4) for y in range(SIZE))
        if packed == b"\xcd" * len(packed):
            raise ProbeError("Readback buffer still contains only its initialization marker")
        return score(rows, packed)


def spans(rows):
    for y, row in enumerate(rows):
        for run in re.finditer("1+", row):
            yield MTLScissorRect(run.start(), y, run.end() - run.start(), 1)


def read_mask(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    rows = data.get("rows")
    if (data.get("size") != SIZE or data.get("symbol") != "wifi" or
            not isinstance(rows, list) or len(rows) != SIZE or
            not all(isinstance(row, str) and re.fullmatch("[01]{32}", row) for row in rows)):
        raise ProbeError("Expected 32 by 32 binary Wi-Fi mask")
    count = sum(row.count("1") for row in rows)
    if count != data.get("selectedPixels") or not 16 <= count <= SIZE * SIZE - 16:
        raise ProbeError("Unexpected Wi-Fi mask area")
    return rows, count


def score(rows, packed):
    inside = outside = largest = 0
    first = None
    for y, row in enumerate(rows):
        for x, bit in enumerate(row):
            selected = bit == "1"
            seed = [(255 * (4*(c+1) + (x+3*y) % 4) + 16) // 32 for c in range(4)]
            expected = [n + 16*selected for n in seed]
            begin = (SIZE*y+x) * 4
            actual = list(packed[begin:begin+4])
            delta = max(abs(a-b) for a, b in zip(actual, expected))
            largest = max(largest, delta)
            if delta <= 1:
                inside += selected
                outside += not selected
            elif first is None:
                first = dict(x=x, y=y, expected=expected, actual=actual)
    matched = inside + outside
    return dict(status="PASS" if matched == SIZE*SIZE else "MISMATCH", pixels=SIZE*SIZE,
                matched=matched, matchedInside=inside, matchedOutside=outside,
                maxChannelError=largest, firstMismatch=first, rgbaBase64=base64.b64encode(packed).decode("ascii"))


def self_test(api):
    texture = api.texture_descriptor()
    color = api.attachment(api.pipeline_descriptor())
    draw_color = api.attachment(api.pass_descriptor(LOAD))
    observed = [api.send(texture, name, U) for name in ("width", "height", "storageMode", "usage", "pixelFormat")]
    observed += [api.send(color, "pixelFormat", U), api.send(draw_color, "loadAction", U),
                 api.send(draw_color, "storeAction", U)]
    if observed != [SIZE, SIZE, PRIVATE, SHADER_READ | RENDER_TARGET, RGBA8_UNORM, RGBA8_UNORM, LOAD, STORE]:
        raise ProbeError("Metal descriptors did not round-trip their fields")
    return dict(event="self-test", status="PASS", processArchitecture="x86_64",
                scope="Native descriptor setters and getters; no GPU command submitted",
                enumeratedDevices=len(api.collect_devices()))


def run(api, key, shader_path, mask_path):
    info = dict(event="gpu-render", key=key, name=None, registryID=None, width=SIZE,
                height=SIZE, pixelFormat="RGBA8Unorm", processArchitecture="x86_64",
                backend="native-python-ctypes", cases=[])
    try:
        rows, info["selectedPixels"] = read_mask(mask_path)
        matches = [gpu for gpu in api.collect_devices()
                   if NAMES[key].casefold() == api.text(api.send(gpu, "name")).casefold()]
        if len(matches) != 1:
            raise ProbeError("Expected one %s; found %d matching devices" % (NAMES[key], len(matches)))
        gpu = matches[0]
        info["name"] = api.text(api.send(gpu, "name"))
        info["registryID"] = hex(required(api.send(gpu, "registryID", C.c_uint64), "GPU registry ID"))
        library = api.shader_library(gpu, shader_path.resolve())
        writer = api.pipeline(gpu, library, "initial0")
        queue = api.owned(api.send(gpu, "newCommandQueue"), "command queue")
    except ProbeError as exc:
        info["cases"] = [exc.record(mode) for mode in MODES]
        return info
    timeout = False
    for mode in MODES:
        try:
            if timeout:
                raise ProbeError("Previous GPU operation timed out")
            info["cases"].append(dict(mode=mode, **api.render(gpu, library, writer, queue, mode, rows)))
        except ProbeError as exc:
            timeout = bool(exc.details.get("timedOut"))
            info["cases"].append(exc.record(mode))
    return info


def main(args):
    check = args in (["--self-test"], ["--bridge-test"])
    if not check and (len(args) != 3 or args[0] not in NAMES):
        raise ValueError("usage: native-metal.py intel|nvidia LIBRARY MASK (or --bridge-test)")
    if not native_x86_64():
        raise ValueError("This Metal probe requires an x86_64 process on macOS")
    api = ObjC()
    pool = required(api.send(api.cls("NSAutoreleasePool"), "new"), "autorelease pool")
    try:
        result = self_test(api) if check else run(api, args[0], Path(args[1]), Path(args[2]))
        result["client"] = "native-x86_64-python-ctypes"
        result["framebufferAdapterMapped"] = framebuffer_adapter_mapped()
        print(json.dumps(result), flush=True)
    finally:
        api.send(pool, "drain", None)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (ValueError, OSError, ProbeError) as failure:
        sys.exit(str(failure))
