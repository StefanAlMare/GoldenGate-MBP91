"""Two overlapping draws on an explicitly selected legacy Metal device."""
import base64
import ctypes as C
import json
import os
from pathlib import Path
import runpy
import sys
import time

RECTS = ((0, 0, 24, 24), (8, 8, 24, 24))
MODES = ("texture-control", "original", "frozen", "snapshot", "alias-barrier")
SIZE = 32


def reference(mode):
    # probe.metal: seed=1/8,2/8,3/8,4/8 plus coordinate term; each draw adds 1/16.
    # Frozen reads the first generation for both draws, even in the overlap.
    pixels = bytearray()
    for y in range(SIZE):
        for x in range(SIZE):
            n = sum(left <= x < left + w and top <= y < top + h for left, top, w, h in RECTS)
            if mode == "frozen":
                n = min(n, 1)
            for channel in range(4):
                seed = (255 * (4 * (channel + 1) + (x + 3*y) % 4) + 16) // 32
                pixels.append(seed + 16*n)
    return bytes(pixels)


def compare_pixels(mode, packed):
    if len(packed) != SIZE*SIZE*4:
        raise ValueError("Dimensiunea imaginii este incorectă.")
    expected = reference(mode)
    errors = [max(abs(a-b) for a, b in zip(expected[i:i+4], packed[i:i+4]))
              for i in range(0, len(packed), 4)]
    overlap = [errors[y*SIZE+x] for y in range(8,24) for x in range(8,24)]
    return sum(e <= 1 for e in errors), sum(e <= 1 for e in overlap), max(errors)


def snapshot(api, command, src, dst, m):
    blit = m.required(api.send(command, "blitCommandEncoder"), "snapshot encoder")
    origin = m.MTLOrigin(0, 0, 0)
    api.send(blit, "copyFromTexture:sourceSlice:sourceLevel:sourceOrigin:sourceSize:"
             "toTexture:destinationSlice:destinationLevel:destinationOrigin:", None,
             (m.P, m.U, m.U, m.MTLOrigin, m.MTLSize, m.P, m.U, m.U, m.MTLOrigin),
             src, 0, 0, origin, m.MTLSize(SIZE, SIZE, 1), dst, 0, 0, origin)
    api.send(blit, "endEncoding", None)


def encode(api, command, target, previous, state, slot, mode, m):
    # The alias variant keeps both draws in one render pass, like the Intel adapter.
    # The snapshot variant must end the encoder for its intervening blit.
    enc = None
    for i, rect in enumerate(RECTS):
        if mode in ("snapshot", "texture-control") or (mode == "frozen" and i == 0):
            snapshot(api, command, target, previous, m)
        if enc is None:
            desc = api.pass_descriptor(m.LOAD, target)
            enc = m.required(api.send(command, "renderCommandEncoderWithDescriptor:", m.P, (m.P,), desc),
                             "render encoder")
            api.send(enc, "setRenderPipelineState:", None, (m.P,), state)
        if mode not in ("original", "author-probe"):
            texture = target if mode == "alias-barrier" else previous
            api.send(enc, "setFragmentTexture:atIndex:", None, (m.P, m.U), texture, slot)
        api.send(enc, "setScissorRect:", None, (m.MTLScissorRect,), m.MTLScissorRect(*rect))
        if mode == "alias-barrier":
            if not api.send(enc, "respondsToSelector:", m.BOOL, (m.P,), api.selector("textureBarrier")):
                raise m.ProbeError("textureBarrier indisponibil pe encoderul acestui dispozitiv.")
            api.send(enc, "textureBarrier", None)
        api.send(enc, "drawPrimitives:vertexStart:vertexCount:", None, (m.U,m.U,m.U), m.TRIANGLE, 0, 3)
        if i == 1 or mode in ("snapshot", "texture-control"):
            api.send(enc, "endEncoding", None)
            enc = None


def readback(api, command, gpu, target, m):
    count = SIZE*m.STRIDE
    buf = api.owned(api.send(gpu, "newBufferWithLength:options:", m.P, (m.U,m.U), count, m.MANAGED_BUFFER),
                    "readback")
    ptr = m.required(api.send(buf, "contents"), "readback address")
    C.memset(ptr, 0xcd, count)
    api.send(buf, "didModifyRange:", None, (m.NSRange,), m.NSRange(0, count))
    blit = m.required(api.send(command, "blitCommandEncoder"), "readback encoder")
    api.send(blit, "copyFromTexture:sourceSlice:sourceLevel:sourceOrigin:sourceSize:"
             "toBuffer:destinationOffset:destinationBytesPerRow:destinationBytesPerImage:", None,
             (m.P,m.U,m.U,m.MTLOrigin,m.MTLSize,m.P,m.U,m.U,m.U), target, 0, 0, m.MTLOrigin(0,0,0),
             m.MTLSize(SIZE,SIZE,1), buf, 0, m.STRIDE, count)
    api.send(blit, "synchronizeResource:", None, (m.P,), buf)
    api.send(blit, "endEncoding", None)
    api.send(command, "commit", None)
    deadline = time.monotonic() + 15
    while api.send(command, "status", m.U) < m.COMPLETED:
        if time.monotonic() >= deadline:
            raise m.ProbeError("Timpul de execuție GPU a expirat.", timedOut=True)
        time.sleep(.05)
    if api.send(command, "status", m.U) != m.COMPLETED:
        raise api.error("GPU command failed", api.send(command, "error"))
    return b"".join(C.string_at(ptr+y*m.STRIDE, SIZE*4) for y in range(SIZE))


def load_author_encoder(api, gpu, registry_id, m):
    """The prebuilt test library targets Metal's default device in its initializer."""
    default = api.metal.MTLCreateSystemDefaultDevice
    default.argtypes, default.restype = [], m.P
    def default_id():
        device = api.owned(default(), "default Metal device")
        return api.send(device, "registryID", C.c_uint64)

    if default_id() != registry_id:
        raise m.ProbeError("Proba autorului omisă: GT 650M nu este GPU-ul implicit în acest proces.")
    get_class = api.objc.object_getClass
    get_class.argtypes, get_class.restype = [m.P], m.P
    device_class = m.required(get_class(gpu), "device class")
    implementation = api.objc.class_getMethodImplementation
    implementation.argtypes, implementation.restype = [m.P,m.P], m.P
    factory = api.selector("newRenderPipelineStateWithDescriptor:options:reflection:error:")
    original = m.required(implementation(device_class, factory), "original pipeline implementation")
    if "METAL_FRAMEBUFFER_PROBE" in os.environ:
        raise m.ProbeError("Procesul are deja METAL_FRAMEBUFFER_PROBE configurat.")
    os.environ["METAL_FRAMEBUFFER_PROBE"] = "1"
    try:
        encoder = C.CDLL(str(Path("encoder.dylib").resolve()), mode=os.RTLD_LOCAL | os.RTLD_NOW)
    finally:
        del os.environ["METAL_FRAMEBUFFER_PROBE"]
    if default_id() != registry_id or implementation(device_class, factory) in (None, original):
        raise m.ProbeError("Instalarea în proces a adaptorului pe clasa dispozitivului ales este neconfirmată.")
    return encoder


def measure(key, mode):
    helper = runpy.run_path(str(Path(__file__).with_name("lowered-metal.py")))
    m = helper["metal"]
    if not m.native_x86_64():
        raise ValueError("Procesul nu este x86_64 nativ.")
    api = m.ObjC()
    pool = m.required(api.send(api.cls("NSAutoreleasePool"), "new"), "autorelease pool")
    result = dict(key=key, mode=mode, status="INCONCLUSIVE")
    try:
        name = m.NAMES[key]
        devices = [d for d in api.collect_devices() if api.text(api.send(d, "name")) == name]
        if len(devices) != 1:
            raise m.ProbeError("Dispozitiv absent sau ambiguu: "+name)
        gpu = devices[0]
        registry_id = m.required(api.send(gpu, "registryID", C.c_uint64), "GPU ID")
        result.update(name=name, registryID=hex(registry_id))
        if mode == "author-probe":
            if key != "nvidia":
                raise m.ProbeError("Proba autorului necesită placa NVIDIA.")
            encoder_library = load_author_encoder(api, gpu, registry_id, m)
            result.update(defaultRegistryID=hex(registry_id), deviceFactoryChanged=True)
        orig = api.shader_library(gpu, Path("probe.metallib").resolve())
        writer = api.pipeline(gpu, orig, "initial0")
        slot = 0
        if mode in ("original","author-probe","texture-control"):
            state = api.pipeline(gpu, orig, "texture0" if mode == "texture-control" else "fetch0")
        else:
            lib = api.shader_library(gpu, Path("lowered-single.metallib").resolve())
            binding = helper["load_binding"](Path("lowered-single.bindings.json"))
            state, slot = helper["reflected_pipeline"](api,gpu,orig,lib,binding,result)
        queue = api.owned(api.send(gpu, "newCommandQueue"), "command queue")
        command = m.required(api.send(queue, "commandBuffer"), "command buffer")
        desc = api.texture_descriptor()
        target, prev = [api.owned(api.send(gpu, "newTextureWithDescriptor:", m.P, (m.P,), desc), "texture")
                        for _ in range(2)]
        if target == prev:
            raise m.ProbeError("Texturile distincte sunt identice.")
        api.draw(command, target, m.CLEAR, writer)
        encode(api, command, target, prev, state, slot, mode, m)
        pixels = readback(api, command, gpu, target, m)
        result.update(status="READBACK", pixels=base64.b64encode(pixels).decode())
    except m.ProbeError as exc:
        result.update(exc.record(mode))
    finally:
        api.send(pool, "drain", None)
    return result


if __name__ == "__main__":
    key, mode = sys.argv[1:]
    if key not in ("intel", "nvidia") or (mode not in MODES and (key,mode) != ("nvidia","author-probe")):
        raise SystemExit("GPU sau probă necunoscută.")
    print(json.dumps(result := measure(key, mode)), flush=True)
    if result.get("timedOut"):
        sys.exit(124)
