import struct


def rle_decompress(data, decompressed_length):
    out = bytearray(decompressed_length)
    pos = 0
    k = 0
    n = len(data)
    while k < n:
        b = data[k]
        if b == 0:
            if k + 1 >= n:
                break
            pos += data[k + 1]
            k += 2
            if pos > decompressed_length:
                break
        else:
            if pos >= decompressed_length:
                break
            out[pos] = b
            pos += 1
            k += 1
    return bytes(out)


class SprImage:
    __slots__ = ('width', 'height', 'is_indexed', 'pixels')
    # pixels: for indexed -> bytes of palette indices (len = width*height)
    #         for bgra32  -> bytes of BGRA quads (len = width*height*4)


class Spr:
    def __init__(self, data):
        magic, minor, major = struct.unpack_from('<2sBB', data, 0)
        if magic != b'SP':
            raise ValueError('bad SPR magic: %r' % magic)
        self.version = major + minor / 10.0
        pos = 4
        if self.version >= 3.2:
            self.n_indexed8, = struct.unpack_from('<i', data, pos)
            pos += 4
            self.n_bgra32 = 0
        else:
            self.n_indexed8, self.n_bgra32 = struct.unpack_from('<HH', data, pos)
            pos += 4

        self.images = []
        for _ in range(self.n_indexed8):
            width, height = struct.unpack_from('<HH', data, pos)
            pos += 4
            if self.version >= 2.2:
                length, = struct.unpack_from('<i', data, pos)
                pos += 4
                raw = data[pos:pos + length]
                pos += length
                pixels = rle_decompress(raw, width * height)
            elif self.version >= 2.1:
                length, = struct.unpack_from('<H', data, pos)
                pos += 2
                raw = data[pos:pos + length]
                pos += length
                pixels = rle_decompress(raw, width * height)
            else:
                pixels = data[pos:pos + width * height]
                pos += width * height
            img = SprImage()
            img.width, img.height, img.is_indexed, img.pixels = width, height, True, pixels
            self.images.append(img)

        for _ in range(self.n_bgra32):
            width, height = struct.unpack_from('<HH', data, pos)
            pos += 4
            raw = data[pos:pos + width * height * 4]
            pos += width * height * 4
            img = SprImage()
            img.width, img.height, img.is_indexed, img.pixels = width, height, False, raw
            self.images.append(img)

        self.palette = None
        if self.n_indexed8 > 0:
            pal_bytes = data[-1024:]
            palette = []
            for i in range(256):
                r, g, b, a = pal_bytes[4 * i], pal_bytes[4 * i + 1], pal_bytes[4 * i + 2], pal_bytes[4 * i + 3]
                palette.append((r, g, b, 255 if i != 0 else 0))
            self.palette = palette

    def get_rgba(self, sprite_index, sprite_type):
        if sprite_type == 0:
            img = self.images[sprite_index]
        else:
            img = self.images[self.n_indexed8 + sprite_index]
        if img.is_indexed:
            out = bytearray(img.width * img.height * 4)
            for i, idx in enumerate(img.pixels):
                r, g, b, a = self.palette[idx]
                out[4 * i:4 * i + 4] = bytes((r, g, b, a))
            return bytes(out), img.width, img.height
        else:
            # stored bottom-up BGRA per _loadBgra32Image; convert to top-down RGBA
            w, h = img.width, img.height
            src = img.pixels
            out = bytearray(w * h * 4)
            for y in range(h):
                for x in range(w):
                    si = 4 * ((h - y - 1) * w + x)
                    di = 4 * (w * y + x)
                    out[di + 0] = src[si + 2]
                    out[di + 1] = src[si + 1]
                    out[di + 2] = src[si + 0]
                    out[di + 3] = src[si + 3]
            return bytes(out), w, h


if __name__ == '__main__':
    import sys
    from grf_reader import GrfFile

    grf_path = sys.argv[1] if len(sys.argv) > 1 else r'C:\Users\Administrator\Documents\Ragnarok\Banquet of Heroes\spritedata.grf'
    entry = sys.argv[2] if len(sys.argv) > 2 else 'data/sprite/인간족/어세신/어세신_여_1238.spr'

    grf = GrfFile(grf_path)
    data = grf.read(entry.lower())
    spr = Spr(data)
    print('version', spr.version, 'n_indexed8', spr.n_indexed8, 'n_bgra32', spr.n_bgra32, 'num images', len(spr.images))
    for i, img in enumerate(spr.images[:6]):
        print(' image', i, img.width, 'x', img.height, 'indexed' if img.is_indexed else 'bgra32')
