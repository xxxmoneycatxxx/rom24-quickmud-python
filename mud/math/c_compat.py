"""C-compatibility helpers (division/modulo/clamp).

Matches C integer division semantics (truncate toward zero), unlike Python's
"//" which floors toward negative infinity.
"""

from __future__ import annotations


def c_div(a: int, b: int) -> int:
    """C-style integer division (truncate toward zero)."""
    if b == 0:
        raise ZeroDivisionError("c_div by zero")
    q = abs(a) // abs(b)
    return q if (a >= 0) == (b >= 0) else -q


def c_mod(a: int, b: int) -> int:
    """C-style modulo consistent with c_div: a == b * c_div(a,b) + c_mod(a,b)."""
    if b == 0:
        raise ZeroDivisionError("c_mod by zero")
    return a - b * c_div(a, b)


def urange(low: int, val: int, high: int) -> int:
    """Clamp to [low, high] inclusive, like ROM's URANGE macro."""
    return max(low, min(val, high))


def rom_is_number(arg: str) -> bool:
    """ROM ``is_number`` (src/interp.c:696).

    True when ``arg`` is a run of digits with an optional single leading
    ``+``/``-``. Differs from ``str.isdigit()``: ``rom_is_number("-5")`` is
    True (a signed integer) and ``rom_is_number("")`` is False. Used to gate
    ROM's "numeric coin" command branches (e.g. ``drop -5 coins``).
    """
    if not arg:
        return False
    if arg[0] in "+-":
        arg = arg[1:]
    if not arg:
        return False
    return all(ch.isdigit() and ch.isascii() for ch in arg)


def rom_atoi(arg: str) -> int:
    """ROM/C ``atoi``.

    Parses an optional leading ``+``/``-`` followed by decimal digits, stopping
    at the first non-digit — so ``rom_atoi("12x") == 12`` and
    ``rom_atoi("x") == 0``. Differs from Python ``int()``, which raises on any
    trailing garbage. Non-numeric input yields 0.
    """
    if not arg:
        return 0
    i = 0
    sign = 1
    if arg[0] in "+-":
        sign = -1 if arg[0] == "-" else 1
        i = 1
    start = i
    while i < len(arg) and arg[i].isdigit() and arg[i].isascii():
        i += 1
    if i == start:
        return 0
    return sign * int(arg[start:i])
