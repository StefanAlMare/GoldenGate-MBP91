"""Compare original and texture-lowered fetch0 on an explicitly selected GT 650M."""
import ctypes as C
from importlib.util import module_from_spec, spec_from_file_location
import json
from pathlib import Path
import sys

spec = spec_from_file_location("metal_probe", Path(__file__).with_name("native-metal.py"))
metal = module_from_spec(spec)
spec.loader.exec_module(metal)
P, U = metal.P, metal.U
MODES = ("texture-control", "framebuffer-read", "lowered-fetch0")
SENTINEL = 0xcd
TEXTURE_NAME = "__fbcompat_fb_attachment_0"


def load_binding(path):
    manifest = json.loads(path.read_text(encoding="utf-8"))
    entries = [item for item in manifest if item["function"] == "@fetch0"]
    expected = {"name": TEXTURE_NAME, "attachment": 0, "texture_index": 127, "type": "float4"}
    if (len(entries) != 1 or entries[0]["multisample"] is not False
            or entries[0]["bindings"] != [expected]):
        raise metal.ProbeError("Unexpected single-sample fetch0 binding manifest")
    return expected


def reflected_pipeline(api, gpu, original, lowered, binding, details):
    pipeline = api.pipeline_descriptor()
    for setter, library, name in (("setVertexFunction:", original, "fullscreen"),
                                  ("setFragmentFunction:", lowered, "fetch0")):
        fn = api.send(library, "newFunctionWithName:", P, (P,), api.string(name))
        api.send(pipeline, setter, None, (P,), api.owned(fn, name + " shader"))

    reflection, error = P(), P()
    # MTLPipelineOptionArgumentInfo is 1. Metal populates both out-parameters.
    state = api.send(gpu, "newRenderPipelineStateWithDescriptor:options:reflection:error:",
                     P, (P, U, C.POINTER(P), C.POINTER(P)), pipeline, 1,
                     C.byref(reflection), C.byref(error))
    if not state:
        raise api.error("lowered fetch0 pipeline creation failed", error, pipeline="fetch0")
    state = api.owned(state, "lowered pipeline")
    details["pipelineCreated"] = True
    arguments = metal.required(api.send(metal.required(reflection, "pipeline reflection"),
                                       "fragmentArguments"), "fragment arguments")
    matches = []
    for i in range(api.send(arguments, "count", U)):
        arg = api.send(arguments, "objectAtIndex:", P, (U,), i)
        if api.text(api.send(arg, "name")) == binding["name"] and api.send(arg, "isActive", metal.BOOL):
            matches.append((api.send(arg, "type", U), api.send(arg, "index", U)))
    if len(matches) != 1:
        raise metal.ProbeError("Expected one active reflected fragment argument named " + binding["name"]
                               + ", found " + str(len(matches)))
    arg_type, slot = matches[0]
    details.update(reflectedTextureName=binding["name"], reflectedTextureIndex=slot,
                   reflectedArgumentType=arg_type)
    if arg_type != 2 or not 0 <= slot <= 127:
        raise metal.ProbeError("Reflected argument is not a texture with a valid resource index")
    details.update(reflectedTextureType="texture", reflectedIndexMatchesManifest=slot == binding["texture_index"])
    return state, slot


def destination_pattern(rows):
    pixels = bytearray(metal.SIZE * metal.STRIDE)
    for y, row in enumerate(rows):
        for x, bit in enumerate(row):
            offset = y * metal.STRIDE + 4*x
            for c in range(4):
                seed = (255 * (4*(c+1) + (x+3*y) % 4) + 16) // 32
                pixels[offset+c] = SENTINEL if bit == "1" else seed
    return bytes(pixels)


def upload_destination(api, gpu, command, destination, rows):
    data = destination_pattern(rows)
    count = len(data)
    buffer = api.owned(api.send(gpu, "newBufferWithLength:options:", P, (U, U), count,
                               metal.MANAGED_BUFFER), "sentinel staging buffer")
    address = metal.required(api.send(buffer, "contents"), "sentinel staging address")
    C.memmove(address, data, count)
    api.send(buffer, "didModifyRange:", None, (metal.NSRange,), metal.NSRange(0, count))
    blit = metal.required(api.send(command, "blitCommandEncoder"), "sentinel upload encoder")
    api.send(blit, "copyFromBuffer:sourceOffset:sourceBytesPerRow:sourceBytesPerImage:sourceSize:"
             "toTexture:destinationSlice:destinationLevel:destinationOrigin:", None,
             (P, U, U, U, metal.MTLSize, P, U, U, metal.MTLOrigin),
             buffer, 0, metal.STRIDE, count, metal.MTLSize(metal.SIZE, metal.SIZE, 1),
             destination, 0, 0, metal.MTLOrigin(0, 0, 0))
    api.send(blit, "endEncoding", None)


def measure(api, mode):
    report = dict(event="gpu-render", key="nvidia", name=None, registryID=None,
                  width=metal.SIZE, height=metal.SIZE, pixelFormat="RGBA8Unorm",
                  processArchitecture="x86_64", client="native-x86_64-python-ctypes", cases=[])
    details = {}
    try:
        rows, report["selectedPixels"] = metal.read_mask(Path("wifi-mask.json"))
        name = metal.NAMES["nvidia"]
        matches = [gpu for gpu in api.collect_devices()
                   if name.casefold() == api.text(api.send(gpu, "name")).casefold()]
        if len(matches) != 1:
            raise metal.ProbeError("Expected one %s; found %d matching devices" % (name, len(matches)))
        gpu = matches[0]
        report["name"] = api.text(api.send(gpu, "name"))
        report["registryID"] = hex(metal.required(api.send(gpu, "registryID", C.c_uint64), "GPU registry ID"))
        original = api.shader_library(gpu, Path("probe.metallib").resolve())
        writer = api.pipeline(gpu, original, "initial0")
        queue = api.owned(api.send(gpu, "newCommandQueue"), "command queue")
        if mode == "lowered-fetch0":
            binding = load_binding(Path("lowered-single.bindings.json"))
            details["declaredTextureIndex"] = binding["texture_index"]
            lowered = api.shader_library(gpu, Path("lowered-single.metallib").resolve())
            state, slot = reflected_pipeline(api, gpu, original, lowered, binding, details)
            values = api.render(gpu, original, writer, queue, "texture-control", rows,
                                shader=state, texture_index=slot, prepare_destination=upload_destination)
            details.update(distinctTextures=True, destinationSentinel=SENTINEL)
        else:
            values = api.render(gpu, original, writer, queue, mode, rows)
        report["cases"].append(dict(mode=mode, **values, **details))
    except metal.ProbeError as error:
        report["cases"].append(dict(**error.record(mode), **details))
    except (OSError, ValueError, KeyError, TypeError) as error:
        report["cases"].append(dict(mode=mode, status="INCONCLUSIVE", reason=str(error), **details))
    report["framebufferAdapterMapped"] = metal.framebuffer_adapter_mapped()
    return report


def main(args):
    if len(args) != 1 or args[0] not in (*MODES, "--bridge-test"):
        raise ValueError("usage: lowered-metal.py " + "|".join((*MODES, "--bridge-test")))
    if not metal.native_x86_64():
        raise ValueError("This test requires a native x86_64 client")
    api = metal.ObjC()
    pool = metal.required(api.send(api.cls("NSAutoreleasePool"), "new"), "autorelease pool")
    try:
        if args[0] == "--bridge-test":
            result = metal.self_test(api)
            width = metal.SIZE
            rows = ["10"*(width//2) for _ in range(width)]
            pattern = destination_pattern(rows)
            packed = b"".join(pattern[y*metal.STRIDE:y*metal.STRIDE+4*width] for y in range(width))
            score = metal.score(rows, packed)
            if (score["matchedInside"], score["matchedOutside"]) != (0, width*width//2):
                raise metal.ProbeError("Invalid no-draw foreground sentinel or background")
            result["destinationSentinel"] = SENTINEL
            result["scope"] += "; verified foreground/background initialization"
        else:
            result = measure(api, args[0])
        print(json.dumps(result), flush=True)
    finally:
        api.send(pool, "drain", None)


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except (ValueError, OSError, metal.ProbeError) as error:
        sys.exit(str(error))
