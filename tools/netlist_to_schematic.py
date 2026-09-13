#!/usr/bin/env python3
"""Build a reviewable KiCad schematic from a netlist.

    ./.venv/bin/python tools/netlist_to_schematic.py <netlist.net> <out.kicad_sch>

Symbols are placed on a grid and every pin gets a net label. There are no
drawn wires: connectivity is read from the labels, which is how a generated
schematic stays legible and is why SKiDL's own schematic generator, which
tries to route wires, never completes on the 324-ball part.

The result opens in the schematic editor and is meant for reading the circuit,
not for driving layout. The netlist remains the source of truth.
"""

import sys
from collections import defaultdict
from pathlib import Path

SYMDIRS = [
    Path(__file__).resolve().parent.parent / "hardware" / "symbols",
    Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"),
]

GRID = 2.54
SHEET_W, SHEET_H = 1600.0, 1200.0


# ---------------------------------------------------------------- s-expr
class Q(str):
    """A token that was quoted in the source and must be quoted again.

    Without this the round trip loses the distinction between a bare keyword
    like `yes` and a string like "Device:C", and KiCad rejects the file.
    """


def parse(text):
    tok, out, cur = [], [], []
    i, n = 0, len(text)
    buf = []
    while i < n:
        c = text[i]
        if c == '"':
            j = i + 1
            s = []
            while j < n:
                if text[j] == "\\":
                    s.append(text[j + 1]); j += 2; continue
                if text[j] == '"':
                    break
                s.append(text[j]); j += 1
            tok.append(("str", Q("".join(s)))); i = j + 1; continue
        if c in "()":
            if buf:
                tok.append(("sym", "".join(buf))); buf = []
            tok.append(("par", c)); i += 1; continue
        if c.isspace():
            if buf:
                tok.append(("sym", "".join(buf))); buf = []
            i += 1; continue
        buf.append(c); i += 1
    if buf:
        tok.append(("sym", "".join(buf)))

    def build(k):
        node = []
        while k < len(tok):
            kind, val = tok[k]
            if kind == "par" and val == "(":
                sub, k = build(k + 1); node.append(sub)
            elif kind == "par" and val == ")":
                return node, k + 1
            else:
                node.append(val); k += 1
        return node, k
    return build(0)[0]


def kids(node, key):
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def val(node, key, default=""):
    for c in kids(node, key):
        return c[1] if len(c) > 1 else default
    return default


def dump(node, indent=1):
    """Re-serialise a parsed node, preserving which tokens were quoted."""
    if isinstance(node, Q):
        return '"' + node.replace("\\", "\\\\").replace('"', '\\"') + '"'
    if isinstance(node, str):
        return node
    return "(" + " ".join(dump(c, indent) for c in node) + ")"


# ------------------------------------------------------------- symbols
_libcache = {}


def load_lib(lib):
    if lib in _libcache:
        return _libcache[lib]
    for d in SYMDIRS:
        p = d / f"{lib}.kicad_sym"
        if p.is_file():
            root = parse(p.read_text())[0]
            # A symbol's own name is its second element. Its children are
            # sub-units named like "C_0_1", so looking for a child called
            # "symbol" finds the sub-unit and loses the real name.
            _libcache[lib] = {s[1]: s for s in kids(root, "symbol")
                              if len(s) > 1 and isinstance(s[1], str)}
            return _libcache[lib]
    _libcache[lib] = {}
    return _libcache[lib]


def collect_pins(node, out):
    """Every pin anywhere under this symbol, with its connection point."""
    for c in node:
        if isinstance(c, list):
            if c and c[0] == "pin":
                at = kids(c, "at")
                num = ""
                for nb in kids(c, "number"):
                    num = nb[1]
                if at:
                    x, y = float(at[0][1]), float(at[0][2])
                    ang = float(at[0][3]) if len(at[0]) > 3 else 0.0
                    out.append((num, x, y, ang))
            else:
                collect_pins(c, out)
    return out


def main(netlist, outpath):
    root = parse(Path(netlist).read_text())[0]

    comps = []
    for b in kids(root, "components"):
        for c in kids(b, "comp"):
            ls = kids(c, "libsource")
            comps.append({
                "ref": val(c, "ref"), "value": val(c, "value"),
                "lib": val(ls[0], "lib") if ls else "",
                "part": val(ls[0], "part") if ls else "",
            })

    pinnet = defaultdict(dict)
    for b in kids(root, "nets"):
        for nnode in kids(b, "net"):
            name = val(nnode, "name")
            for nd in kids(nnode, "node"):
                pinnet[val(nd, "ref")][val(nd, "pin")] = name

    used, missing = {}, []
    for c in comps:
        key = f'{c["lib"]}:{c["part"]}'
        if key not in used:
            sym = load_lib(c["lib"]).get(c["part"])
            if sym is None:
                missing.append(key)
            else:
                used[key] = sym

    body = []
    uid = [0]

    def nid():
        uid[0] += 1
        return f"00000000-0000-0000-0000-{uid[0]:012d}"

    # lib_symbols, renamed to Lib:Part as the schematic format requires.
    libblock = ["\t(lib_symbols"]
    for key, sym in used.items():
        s = list(sym)
        s[1] = Q(key)
        libblock.append("\t\t" + dump(s))
    libblock.append("\t)")
    body.append("\n".join(libblock))

    # Place, widest first so rows stay even.
    sized = []
    for c in comps:
        key = f'{c["lib"]}:{c["part"]}'
        if key not in used:
            continue
        pins = collect_pins(used[key], [])
        w = (max((p[1] for p in pins), default=0) -
             min((p[1] for p in pins), default=0))
        h = (max((p[2] for p in pins), default=0) -
             min((p[2] for p in pins), default=0))
        sized.append((c, key, pins, w, h))
    sized.sort(key=lambda t: (-t[4], t[0]["ref"]))

    x, y, rowh = 30.0, 30.0, 0.0
    placed = 0
    for c, key, pins, w, h in sized:
        cell_w = max(w + 40.0, 50.0)
        cell_h = max(h + 30.0, 30.0)
        if x + cell_w > SHEET_W:
            x, y, rowh = 30.0, y + rowh, 0.0
        cx = round((x + cell_w / 2) / GRID) * GRID
        cy = round((y + cell_h / 2) / GRID) * GRID

        body.append(
            f'\t(symbol (lib_id "{key}") (at {cx} {cy} 0) (unit 1)\n'
            f'\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) '
            f'(dnp no) (fields_autoplaced yes)\n'
            f'\t\t(uuid "{nid()}")\n'
            f'\t\t(property "Reference" "{c["ref"]}" (at {cx} {cy - h/2 - 5} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27))))\n'
            f'\t\t(property "Value" "{c["value"]}" (at {cx} {cy + h/2 + 5} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27))))\n'
            f'\t\t(instances (project "" (path "/" (reference "{c["ref"]}") '
            f'(unit 1))))\n\t)')

        for num, px, py, ang in pins:
            net = pinnet.get(c["ref"], {}).get(num)
            if not net:
                continue
            lx = round((cx + px) / GRID) * GRID
            ly = round((cy - py) / GRID) * GRID
            just = "right" if ang == 0 else "left"
            body.append(
                f'\t(global_label "{net}" (shape passive) (at {lx} {ly} {int(ang)})\n'
                f'\t\t(effects (font (size 1.0 1.0)) (justify {just}))\n'
                f'\t\t(uuid "{nid()}"))')
        placed += 1
        x += cell_w
        rowh = max(rowh, cell_h)

    out = ('(kicad_sch\n\t(version 20231120)\n\t(generator "lyrebird")\n'
           f'\t(uuid "{nid()}")\n\t(paper "User" {SHEET_W} {SHEET_H})\n'
           + "\n".join(body) + "\n)\n")
    Path(outpath).write_text(out)
    print(f"  {placed} symbols placed, {len(comps)} in netlist")
    if missing:
        print(f"  symbol not found: {sorted(set(missing))}")
    print(f"  wrote {outpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
