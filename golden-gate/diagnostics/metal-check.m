#import <Foundation/Foundation.h>
#import <Metal/Metal.h>
#import <unistd.h>

static int fail(const char *message) {
    fprintf(stderr, "INCONCLUSIVE: %s\n", message);
    return 1;
}

int main(void) {
    @autoreleasepool {
        id<MTLDevice> gpu = nil;
        for (id<MTLDevice> candidate in MTLCopyAllDevices()) {
            printf("Metal device: %s\n", candidate.name.UTF8String);
            if ([candidate.name containsString:@"GeForce GT 650M"]) gpu = candidate;
        }
        if (!gpu) return fail("GT 650M was not enumerated by Metal in this session.");
        printf("Selected: %s (registryID 0x%llx)\n", gpu.name.UTF8String, (unsigned long long)gpu.registryID);
        fflush(stdout);
        const NSUInteger edge = 4, stride = 256;
        MTLTextureDescriptor *desc = [MTLTextureDescriptor texture2DDescriptorWithPixelFormat:MTLPixelFormatRGBA8Unorm width:edge height:edge mipmapped:NO];
        desc.storageMode = MTLStorageModePrivate;
        desc.usage = MTLTextureUsageRenderTarget;
        id<MTLTexture> texture = [gpu newTextureWithDescriptor:desc];
        id<MTLBuffer> buffer = [gpu newBufferWithLength:stride * edge options:MTLResourceStorageModeManaged];
        id<MTLCommandQueue> queue = [gpu newCommandQueue];
        id<MTLCommandBuffer> cmd = [queue commandBuffer];
        if (!texture || !buffer || !cmd || !buffer.contents) return fail("Cannot create Metal resources.");
        memset(buffer.contents, 0, buffer.length);
        [buffer didModifyRange:NSMakeRange(0, buffer.length)];
        MTLRenderPassDescriptor *pass = [MTLRenderPassDescriptor renderPassDescriptor];
        pass.colorAttachments[0].texture = texture;
        pass.colorAttachments[0].loadAction = MTLLoadActionClear;
        pass.colorAttachments[0].storeAction = MTLStoreActionStore;
        pass.colorAttachments[0].clearColor = MTLClearColorMake(1,0,0,1);
        id<MTLRenderCommandEncoder> render = [cmd renderCommandEncoderWithDescriptor:pass];
        if (!render) return fail("Cannot start render pass.");
        [render endEncoding];
        id<MTLBlitCommandEncoder> blit = [cmd blitCommandEncoder];
        if (!blit) return fail("Cannot start blit.");
        [blit copyFromTexture:texture sourceSlice:0 sourceLevel:0 sourceOrigin:MTLOriginMake(0,0,0) sourceSize:MTLSizeMake(edge,edge,1) toBuffer:buffer destinationOffset:0 destinationBytesPerRow:stride destinationBytesPerImage:stride * edge];
        [blit synchronizeResource:buffer];
        [blit endEncoding];
        [cmd commit];
        for (int i=0; i<200 && cmd.status<MTLCommandBufferStatusCompleted; ++i) usleep(50000);
        if (cmd.status != MTLCommandBufferStatusCompleted) {
            fprintf(stderr,"INCONCLUSIVE: Metal status %lu, %s\n",(unsigned long)cmd.status,cmd.error.localizedDescription.UTF8String ?: "timeout or unavailable error detail");
            return 2;
        }
        const unsigned char expected[] = {255,0,0,255};
        const unsigned char *pixels = buffer.contents;
        for (NSUInteger y=0; y<edge; ++y)
            for (NSUInteger x=0; x<edge; ++x)
                if (memcmp(pixels+y*stride+x*4,expected,4)) return fail("GPU readback did not match expected red.");
        puts("PASS: NVIDIA GeForce GT 650M | Metal render clear + readback | 16/16 pixels");
        return 0;
    }
}
