"""A small PNG reader, so that the grader needs no image library: grey, RGB, palette and alpha images
of any bit depth, not interlaced. Pixels come out as RGBA rows of bytes."""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


class Image:
    def __init__(self, width: int, height: int, rows: list[bytes]):
        self.width, self.height, self.rows = width, height, rows   # each row: width × RGBA

    def crop(self, x: int, y: int, w: int, h: int) -> list[bytes]:
        return [row[4 * x:4 * (x + w)] for row in self.rows[y:y + h]]


def _unfilter(data: bytes, stride: int, height: int, bpp: int) -> list[bytes]:
    rows, prev = [], bytearray(stride)
    for y in range(height):
        kind, line = data[y * (stride + 1)], bytearray(data[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for i in range(stride):
            left = line[i - bpp] if i >= bpp else 0
            up, corner = prev[i], prev[i - bpp] if i >= bpp else 0
            if kind == 1:
                line[i] = (line[i] + left) & 255
            elif kind == 2:
                line[i] = (line[i] + up) & 255
            elif kind == 3:
                line[i] = (line[i] + (left + up) // 2) & 255
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                line[i] = (line[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        rows.append(bytes(line))
        prev = line
    return rows


def read(path: Path) -> Image:
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError(f"{path}: not a PNG")
    pos, idat, palette, trns = 8, b"", b"", b""
    while pos < len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = body
        elif kind == b"tRNS":
            trns = body
        elif kind == b"IDAT":
            idat += body
        pos += 12 + length
    if interlace or color not in CHANNELS:
        raise ValueError(f"{path}: unsupported PNG (colour {color}, interlace {interlace})")
    bits = CHANNELS[color] * depth
    rows = _unfilter(zlib.decompress(idat), (width * bits + 7) // 8, height, max(1, bits // 8))
    out = []
    for row in rows:
        samples = _samples(row, depth, width * CHANNELS[color])
        if color == 6:
            out.append(bytes(samples))
        elif color == 2:
            out.append(b"".join(bytes(samples[i:i + 3]) + b"\xff" for i in range(0, len(samples), 3)))
        elif color == 3:
            out.append(b"".join(palette[3 * k:3 * k + 3] + bytes([trns[k] if k < len(trns) else 255]) for k in samples))
        elif color == 0:
            scale = 255 // ((1 << depth) - 1) if depth < 8 else 1
            out.append(b"".join(bytes([v * scale] * 3 + [255]) for v in samples))
        else:
            out.append(b"".join(bytes([samples[i]] * 3 + [samples[i + 1]]) for i in range(0, len(samples), 2)))
    return Image(width, height, out)


def _samples(row: bytes, depth: int, count: int) -> list[int]:
    """One value per sample: 16-bit samples keep their high byte, smaller ones are unpacked as they
    are (palette indices, or grey levels that `read` scales)."""
    if depth == 16:
        return list(row[::2])[:count]
    if depth == 8:
        return list(row)[:count]
    per_byte, mask = 8 // depth, (1 << depth) - 1
    return [(byte >> (8 - depth * (k + 1))) & mask for byte in row for k in range(per_byte)][:count]
