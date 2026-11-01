from functools import lru_cache

from .vendor.qrcodegen import QrCode


@lru_cache(maxsize=256)
def matrix(text):
    code = QrCode.encode_text(text, QrCode.Ecc.MEDIUM)
    return tuple(''.join('1' if code.get_module(x, y) else '0' for x in range(code.get_size()))
                 for y in range(code.get_size()))


def svg(rows):
    size = len(rows) + 8
    path = ' '.join(f'M{x+4},{y+4}h1v1h-1z' for y, row in enumerate(rows) for x, cell in enumerate(row) if cell == '1')
    return f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" width="112" height="112" role="img" aria-label="Shipment QR code" shape-rendering="crispEdges"><rect width="100%" height="100%" fill="white"/><path d="{path}" fill="black"/></svg>'
