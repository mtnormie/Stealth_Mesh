"""iOS PWA manifest, app icon, LAN IP detection, and ISO 18004 QR SVG renderer."""

from __future__ import annotations

from html import escape
import json
import socket

PWA_MANIFEST_JSON: str = json.dumps(
    {
        "name": "Stealth Mesh Messenger",
        "short_name": "StealthMesh",
        "description": "Autonomous AES-256-GCM LoRa Mesh Messenger",
        "start_url": "/",
        "display": "standalone",
        "background_color": "#0d151c",
        "theme_color": "#0d151c",
        "orientation": "portrait-primary",
        "icons": [
            {
                "src": "/icon.svg",
                "sizes": "any",
                "type": "image/svg+xml",
                "purpose": "any maskable",
            }
        ],
    },
    ensure_ascii=False,
)

APP_ICON_SVG: str = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 256 256">'
    '<rect width="256" height="256" rx="56" fill="#0d151c"/>'
    '<circle cx="128" cy="128" r="86" fill="none" stroke="#189e82" stroke-width="6" stroke-dasharray="12 8"/>'
    '<line x1="72" y1="88" x2="184" y2="88" stroke="#2ee5b8" stroke-width="7"/>'
    '<line x1="72" y1="88" x2="128" y2="178" stroke="#2ee5b8" stroke-width="7"/>'
    '<line x1="184" y1="88" x2="128" y2="178" stroke="#2ee5b8" stroke-width="7"/>'
    '<circle cx="72" cy="88" r="18" fill="#101820" stroke="#7de2c3" stroke-width="7"/>'
    '<circle cx="184" cy="88" r="18" fill="#101820" stroke="#7de2c3" stroke-width="7"/>'
    '<circle cx="128" cy="178" r="18" fill="#2ee5b8" stroke="#ffffff" stroke-width="5"/>'
    "</svg>"
)


def detect_lan_ip() -> str:
    """Return the primary LAN IPv4 address if reachable, or 127.0.0.1."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("192.168.1.1", 80))
        ip = sock.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except OSError:
        pass
    finally:
        sock.close()
    return "127.0.0.1"


# ---------------------------------------------------------------------------
# Pure-Python ISO/IEC 18004 QR Code SVG Generator (Versions 1..6, ECC Level L)
# ---------------------------------------------------------------------------

# (version, size, total_data_codewords, ec_codewords_per_block, num_blocks, alignment_centers)
_QR_SPECS: tuple[tuple[int, int, int, int, int, tuple[int, ...]], ...] = (
    (1, 21, 19, 7, 1, ()),
    (2, 25, 34, 10, 1, (6, 18)),
    (3, 29, 55, 15, 1, (6, 22)),
    (4, 33, 80, 20, 1, (6, 26)),
    (5, 37, 108, 26, 1, (6, 30)),
    (6, 41, 136, 18, 2, (6, 34)),
)

_GF_EXP = [0] * 512
_GF_LOG = [0] * 256


def _init_gf() -> None:
    x = 1
    for i in range(255):
        _GF_EXP[i] = x
        _GF_LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= 0x11D
    for i in range(255, 512):
        _GF_EXP[i] = _GF_EXP[i - 255]


_init_gf()


def _gf_mul(a: int, b: int) -> int:
    if a == 0 or b == 0:
        return 0
    return _GF_EXP[_GF_LOG[a] + _GF_LOG[b]]


def _rs_generator_poly(degree: int) -> list[int]:
    poly = [1]
    for i in range(degree):
        next_poly = [0] * (len(poly) + 1)
        root = _GF_EXP[i]
        for j, coeff in enumerate(poly):
            next_poly[j] ^= coeff
            next_poly[j + 1] ^= _gf_mul(coeff, root)
        poly = next_poly
    return poly


def _rs_encode(data: list[int], ec_len: int) -> list[int]:
    gen = _rs_generator_poly(ec_len)
    reg = [0] * ec_len
    for byte in data:
        factor = byte ^ reg[0]
        reg = reg[1:] + [0]
        if factor != 0:
            for j in range(ec_len):
                reg[j] ^= _gf_mul(gen[j + 1], factor)
    return reg


def _encode_qr_matrix(payload: bytes) -> list[list[int]]:
    spec = None
    for candidate in _QR_SPECS:
        ver, size, data_cw, ec_cw, blocks, align = candidate
        if len(payload) + 2 <= data_cw:
            spec = candidate
            break
    if spec is None:
        raise ValueError("QR payload too long for built-in encoder")

    ver, size, data_cw, ec_cw, blocks, align = spec
    bits: list[int] = [0, 1, 0, 0]  # Byte mode (0100)
    for i in range(7, -1, -1):
        bits.append((len(payload) >> i) & 1)
    for byte in payload:
        for i in range(7, -1, -1):
            bits.append((byte >> i) & 1)

    max_bits = data_cw * 8
    for _ in range(min(4, max_bits - len(bits))):
        bits.append(0)
    while len(bits) % 8 != 0:
        bits.append(0)

    codewords: list[int] = []
    for i in range(0, len(bits), 8):
        val = 0
        for b in bits[i : i + 8]:
            val = (val << 1) | b
        codewords.append(val)

    pad_bytes = (0xEC, 0x11)
    idx = 0
    while len(codewords) < data_cw:
        codewords.append(pad_bytes[idx % 2])
        idx += 1

    if blocks == 1:
        ec = _rs_encode(codewords, ec_cw)
        final_cw = codewords + ec
    else:
        blk_size = data_cw // blocks
        d_blocks = [codewords[i * blk_size : (i + 1) * blk_size] for i in range(blocks)]
        e_blocks = [_rs_encode(b, ec_cw) for b in d_blocks]
        final_cw = []
        for col in range(blk_size):
            for b in d_blocks:
                final_cw.append(b[col])
        for col in range(ec_cw):
            for eb in e_blocks:
                final_cw.append(eb[col])

    matrix = [[0] * size for _ in range(size)]
    reserved = [[False] * size for _ in range(size)]

    def place_finder(row: int, col: int) -> None:
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = row + r, col + c
                if 0 <= rr < size and 0 <= cc < size:
                    in_outer = 0 <= r <= 6 and (r in (0, 6) or c in (0, 6)) and 0 <= c <= 6
                    in_inner = 2 <= r <= 4 and 2 <= c <= 4
                    matrix[rr][cc] = 1 if (in_outer or in_inner) else 0
                    reserved[rr][cc] = True

    place_finder(0, 0)
    place_finder(0, size - 7)
    place_finder(size - 7, 0)

    for i in range(8, size - 8):
        matrix[6][i] = (i + 1) % 2
        reserved[6][i] = True
        matrix[i][6] = (i + 1) % 2
        reserved[i][6] = True

    for ar in align:
        for ac in align:
            if reserved[ar][ac]:
                continue
            for r in range(-2, 3):
                for c in range(-2, 3):
                    val = 1 if (abs(r) == 2 or abs(c) == 2 or (r == 0 and c == 0)) else 0
                    matrix[ar + r][ac + c] = val
                    reserved[ar + r][ac + c] = True

    # Reserve format info areas & dark module
    for i in range(9):
        if i < size:
            reserved[8][i] = True
            reserved[i][8] = True
    for i in range(8):
        reserved[8][size - 1 - i] = True
        reserved[size - 1 - i][8] = True
    matrix[size - 8][8] = 1
    reserved[size - 8][8] = True

    stream_bits: list[int] = []
    for byte in final_cw:
        for i in range(7, -1, -1):
            stream_bits.append((byte >> i) & 1)
    # Remainder bits (7 bits for versions 2..6)
    if ver >= 2:
        stream_bits.extend([0] * 7)

    bit_idx = 0
    col = size - 1
    upward = True
    while col > 0:
        if col == 6:
            col -= 1
        row_iter = range(size - 1, -1, -1) if upward else range(size)
        for row in row_iter:
            for c_off in (0, -1):
                cc = col + c_off
                if not reserved[row][cc]:
                    bit = stream_bits[bit_idx] if bit_idx < len(stream_bits) else 0
                    bit_idx += 1
                    # Mask pattern 0: (row + cc) % 2 == 0
                    if (row + cc) % 2 == 0:
                        bit ^= 1
                    matrix[row][cc] = bit
        upward = not upward
        col -= 2

    # Format bits for ECC Level L (01) + Mask 0 (000) -> 0x77C4 (15 bits: 111011111000100)
    fmt_bits = [(0x77C4 >> (14 - i)) & 1 for i in range(15)]
    fmt_coords_a = [
        (8, 0), (8, 1), (8, 2), (8, 3), (8, 4), (8, 5), (8, 7), (8, 8),
        (7, 8), (5, 8), (4, 8), (3, 8), (2, 8), (1, 8), (0, 8),
    ]
    for idx_f, (r, c) in enumerate(fmt_coords_a):
        matrix[r][c] = fmt_bits[idx_f]
    for idx_f in range(7):
        matrix[size - 1 - idx_f][8] = fmt_bits[idx_f]
    for idx_f in range(7, 15):
        matrix[8][size - 15 + idx_f] = fmt_bits[idx_f]

    return matrix


def render_qr_svg(data: str, *, scale: int = 6, border: int = 4) -> str:
    """Render a camera-scannable ISO 18004 QR code as an SVG string."""
    if not isinstance(data, str) or not data or len(data) > 2048:
        raise ValueError("invalid QR content")
    raw = data.encode("utf-8")
    try:
        matrix = _encode_qr_matrix(raw)
        n = len(matrix)
        dim = (n + border * 2) * scale
        rects: list[str] = []
        for r, row in enumerate(matrix):
            for c, val in enumerate(row):
                if val:
                    x = (c + border) * scale
                    y = (r + border) * scale
                    rects.append(f'<rect x="{x}" y="{y}" width="{scale}" height="{scale}"/>')
        body = "".join(rects)
        return (
            f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {dim} {dim}" '
            f'width="{dim}" height="{dim}" shape-rendering="crispEdges">'
            f'<rect width="100%" height="100%" fill="#ffffff"/>'
            f'<g fill="#000000">{body}</g></svg>'
        )
    except ValueError:
        return (
            '<svg xmlns="http://www.w3.org/2000/svg" width="210" height="80">'
            '<rect width="100%" height="100%" fill="#fff"/>'
            '<text x="10" y="35" fill="#101820" font-size="11" font-family="monospace">'
            f"{escape(data[:32])}</text>"
            '<text x="10" y="55" fill="#101820" font-size="11" font-family="monospace">'
            f"{escape(data[32:64])}</text></svg>"
        )
