"""Generate the small raster application mark, with no runtime dependencies."""
import struct
import zlib
from pathlib import Path

size = 72
pixels = bytearray()
for y in range(size):
    pixels.append(0)
    for x in range(size):
        color = (121, 215, 181, 255)
        if 23 <= x <= 51 and abs(y - 36) <= (51 - x) * .7:
            color = (20, 44, 34, 255)
        pixels.extend(color)

def chunk(kind, data):
    return struct.pack('!I', len(data)) + kind + data + struct.pack('!I', zlib.crc32(kind + data))

target = Path(__file__).parent / 'app/downloads/console-mark.png'
target.write_bytes(b'\x89PNG\r\n\x1a\n' + chunk(b'IHDR', struct.pack('!2I5B', size, size, 8, 6, 0, 0, 0))
                   + chunk(b'IDAT', zlib.compress(pixels)) + chunk(b'IEND', b''))
