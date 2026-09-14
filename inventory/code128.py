"""Code 128-B for inventory numbers (ISO/IEC 15417 module widths)."""

from __future__ import annotations

# Six run-lengths per symbol (bar/space), summing to 11 modules. Index 106 is Stop (13).
_CODES = (
    "212222", "222122", "222221", "121223", "121322", "131222", "122213",
    "122312", "132212", "221213", "221312", "231212", "112232", "122132",
    "122231", "113222", "123122", "123221", "223211", "221132", "221231",
    "213212", "223112", "312131", "311222", "321122", "321221", "312212",
    "322112", "322211", "212123", "212321", "232121", "111323", "131123",
    "131321", "112313", "132113", "132311", "211313", "231113", "231311",
    "112133", "112331", "132131", "113123", "113321", "133121", "313121",
    "211331", "231131", "213113", "213311", "213131", "311123", "311321",
    "331121", "312113", "312311", "332111", "314111", "221411", "431111",
    "111224", "111422", "121124", "121421", "141122", "141221", "112214",
    "112412", "122114", "122411", "142112", "142211", "241211", "221114",
    "413111", "241112", "134111", "111242", "121142", "121241", "114212",
    "124112", "124211", "411212", "421112", "421211", "212141", "214121",
    "412121", "111143", "111341", "131141", "114113", "114311", "411113",
    "411311", "113141", "114131", "311141", "411131", "211412", "211214",
    "211232", "2331112",
)
_START_B = 104
_STOP = 106


def _symbol_bits(index: int) -> str:
    runs = _CODES[index]
    bits = []
    color = "1"
    for ch in runs:
        bits.append(color * int(ch))
        color = "0" if color == "1" else "1"
    return "".join(bits)


def code128_bits(data: str) -> str:
    """Return a 0/1 module string (no quiet zone) for Code 128-B."""
    text = data or ""
    values = [_START_B]
    checksum = _START_B
    for i, ch in enumerate(text, start=1):
        code = ord(ch) - 32
        if code < 0 or code > 94:
            raise ValueError(f"Character {ch!r} cannot be encoded in Code 128-B.")
        values.append(code)
        checksum += i * code
    values.append(checksum % 103)
    values.append(_STOP)
    return "".join(_symbol_bits(v) for v in values)
