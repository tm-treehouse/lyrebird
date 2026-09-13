#!/usr/bin/env python3
"""Build a reviewable KiCad schematic from a netlist.

    ./.venv/bin/python tools/netlist_to_schematic.py <netlist.net> <out.kicad_sch>

Nets of two or three pins are drawn as wires, and parts that share one are
placed next to each other so the wire is short. Everything else gets a net
label. That split is what a person does by hand: a decoupling capacitor is
wired to the pin it decouples, and ground is a label, because a wire from 245
ground pins to each other is not a drawing anyone can read.

It also happens to cover almost everything. On these two boards 83 and 95
percent of nets connect two or three pins; the rest are ground, the supply
rails and the element bus.

Wires are routed as an L between the two pins, or as a comb to a shared
vertical for three. No attempt is made at global routing, which is the part
that cannot be automated and where SKiDL's own schematic generator hangs on
the 324-ball part.

The result opens in the schematic editor and is meant for reading the circuit.
The netlist remains the source of truth, so edits here are overwritten.
"""

import math
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


def resolve(lib, part, depth=0):
    """A symbol with its inheritance flattened.

    KiCad symbols may carry `(extends "BASE")`, inheriting the base's graphics
    and pins while overriding properties. 74HCT574 does exactly this, and a
    naive reader sees a symbol with no pins at all.
    """
    table = load_lib(lib)
    sym = table.get(part)
    if sym is None or depth > 4:
        return sym
    ext = kids(sym, "extends")
    if not ext:
        return sym
    base = resolve(lib, ext[0][1], depth + 1)
    if base is None:
        return sym
    # Base geometry and pins, under the derived name, with the derived
    # symbol's own properties taking precedence.
    own = {c[1] for c in kids(sym, "property") if len(c) > 1}
    merged = [base[0], Q(part)]
    for c in base[2:]:
        if isinstance(c, list) and c and c[0] == "property" and \
                len(c) > 1 and c[1] in own:
            continue
        if isinstance(c, list) and c and c[0] == "symbol" and len(c) > 1:
            c = list(c)
            c[1] = Q(str(c[1]).replace(str(base[1]), part, 1))
        merged.append(c)
    for c in kids(sym, "property"):
        merged.append(c)
    return merged


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

    nets = []
    for b in kids(root, "nets"):
        for nnode in kids(b, "net"):
            nets.append((val(nnode, "name"),
                         [(val(nd, "ref"), val(nd, "pin"))
                          for nd in kids(nnode, "node")]))

    used, missing = {}, []
    for c in comps:
        key = f'{c["lib"]}:{c["part"]}'
        if key not in used:
            sym = resolve(c["lib"], c["part"])
            if sym is None:
                missing.append(key)
            else:
                used[key] = sym

    byref = {c["ref"]: c for c in comps}
    pins_of = {}
    for c in comps:
        key = f'{c["lib"]}:{c["part"]}'
        pins_of[c["ref"]] = collect_pins(used[key], []) if key in used else []

    # A net is drawn as a wire when it joins two or three pins and is not a
    # supply. Supplies and buses stay as labels; nobody draws 245 ground pins
    # joined by wire.
    wire_nets, label_nets = [], []
    for name, nodes in nets:
        supply = name.startswith(("+", "GND", "VBUS", "N$")) is False and False
        is_supply = name.startswith(("+", "VBUS")) or name.startswith("GND")
        if 2 <= len(nodes) <= 3 and not is_supply:
            wire_nets.append((name, nodes))
        else:
            label_nets.append((name, nodes))

    # Cluster parts joined by wired nets, so a wire stays short.
    adj = defaultdict(set)
    for _, nodes in wire_nets:
        refs = [r for r, _ in nodes if r in pins_of]
        for a in refs:
            for b in refs:
                if a != b:
                    adj[a].add(b)
    seen, clusters = set(), []
    for c in comps:
        r = c["ref"]
        if r in seen or r not in pins_of:
            continue
        stack, group = [r], []
        seen.add(r)
        while stack:
            cur = stack.pop()
            group.append(cur)
            for nb in sorted(adj[cur]):
                if nb not in seen:
                    seen.add(nb)
                    stack.append(nb)
        clusters.append(group)
    clusters.sort(key=len, reverse=True)

    def extent(ref):
        ps = pins_of[ref]
        if not ps:
            return 10.0, 10.0
        return (max(p[1] for p in ps) - min(p[1] for p in ps),
                max(p[2] for p in ps) - min(p[2] for p in ps))

    # A cluster is laid out as a compact block rather than a row. A row of
    # twenty parts is a strip nobody can read; roughly square keeps a cluster
    # scannable and keeps its wires short.
    PAD_X, PAD_Y = 30.0, 26.0

    def cluster_block(group):
        n = len(group)
        cols = max(1, int(math.ceil(math.sqrt(n))))
        cells = [(r, *extent(r)) for r in group]
        colw = [0.0] * cols
        rowh = []
        for i in range(0, n, cols):
            row = cells[i:i + cols]
            rowh.append(max(c[2] for c in row) + PAD_Y)
            for j, c in enumerate(row):
                colw[j] = max(colw[j], c[1] + PAD_X)
        placements = []
        yoff = 0.0
        for i in range(0, n, cols):
            row = cells[i:i + cols]
            xoff = 0.0
            for j, (ref, w, h) in enumerate(row):
                placements.append((ref, xoff + colw[j] / 2,
                                   yoff + rowh[i // cols] / 2, w, h))
                xoff += colw[j]
            yoff += rowh[i // cols]
        return placements, sum(colw), yoff

    blocks = []
    for group in clusters:
        pl, bw, bh = cluster_block(group)
        blocks.append((pl, bw, bh))

    # Shelf-pack the blocks to roughly the proportions of a sheet of paper,
    # instead of running off to the right until a fixed width is hit.
    # Shelf packing wastes roughly a third of the area, so aim wider than the
    # bare area would suggest to land near a landscape sheet.
    total = sum(bw * bh for _, bw, bh in blocks)
    target_w = max(math.sqrt(total * 2.0), max(b[1] for b in blocks) + 20.0)

    pos = {}
    x, y, shelf_h = 20.0, 20.0, 0.0
    max_x = 0.0
    for pl, bw, bh in blocks:
        if x + bw > target_w and x > 20.0:
            x, y, shelf_h = 20.0, y + shelf_h + 14.0, 0.0
        for ref, dx, dy, w, h in pl:
            cx = round((x + dx) / GRID) * GRID
            cy = round((y + dy) / GRID) * GRID
            pos[ref] = (cx, cy, w, h)
        x += bw + 14.0
        max_x = max(max_x, x)
        shelf_h = max(shelf_h, bh)

    sheet_w = round(max_x + 20.0)
    sheet_h = round(y + shelf_h + 20.0)

    body, uid = [], [0]

    def nid():
        uid[0] += 1
        return f"00000000-0000-0000-0000-{uid[0]:012d}"

    libblock = ["\t(lib_symbols"]
    for key, sym in used.items():
        t = list(sym)
        t[1] = Q(key)
        libblock.append("\t\t" + dump(t))
    libblock.append("\t)")
    body.append("\n".join(libblock))

    for ref, (cx, cy, w, h) in pos.items():
        c = byref[ref]
        key = f'{c["lib"]}:{c["part"]}'
        body.append(
            f'\t(symbol (lib_id "{key}") (at {cx} {cy} 0) (unit 1)\n'
            f'\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) (dnp no)\n'
            f'\t\t(uuid "{nid()}")\n'
            f'\t\t(property "Reference" "{ref}" (at {cx} {cy - h/2 - 6.5} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27))))\n'
            f'\t\t(property "Value" "{c["value"]}" (at {cx} {cy + h/2 + 6.5} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27))))\n'
            f'\t\t(instances (project "" (path "/" (reference "{ref}") '
            f'(unit 1))))\n\t)')

    def pin_xy(ref, num):
        cx, cy, _, _ = pos[ref]
        for n, px, py, _ in pins_of[ref]:
            if n == num:
                return (round((cx + px) / GRID) * GRID,
                        round((cy - py) / GRID) * GRID)
        return None

    def wire(a, b):
        body.append(f'\t(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]}))\n'
                    f'\t\t(stroke (width 0) (type default)) (uuid "{nid()}"))')

    def junction(pt):
        body.append(f'\t(junction (at {pt[0]} {pt[1]}) (diameter 0)\n'
                    f'\t\t(color 0 0 0 0) (uuid "{nid()}"))')

    drawn = 0
    for name, nodes in wire_nets:
        pts = [pin_xy(r, pn) for r, pn in nodes if r in pos]
        pts = [p for p in pts if p]
        if len(pts) < 2:
            continue
        if len(pts) == 2:
            a, b = pts
            if a[0] == b[0] or a[1] == b[1]:
                wire(a, b)
            else:
                corner = (a[0], b[1])
                wire(a, corner)
                wire(corner, b)
        else:
            # Comb: each pin runs horizontally to a shared vertical.
            bus = round(sum(p[0] for p in pts) / len(pts) / GRID) * GRID
            ys = [p[1] for p in pts]
            wire((bus, min(ys)), (bus, max(ys)))
            for p in pts:
                if p[0] != bus:
                    wire(p, (bus, p[1]))
                junction((bus, p[1]))
        drawn += 1

    labelled = 0
    for name, nodes in label_nets:
        for r, pn in nodes:
            if r not in pos:
                continue
            pt = pin_xy(r, pn)
            if not pt:
                continue
            body.append(
                f'\t(global_label "{name}" (shape passive) (at {pt[0]} {pt[1]} 0)\n'
                f'\t\t(effects (font (size 1.0 1.0)) (justify right))\n'
                f'\t\t(uuid "{nid()}"))')
            labelled += 1

    out = ('(kicad_sch\n\t(version 20231120)\n\t(generator "lyrebird")\n'
           f'\t(uuid "{nid()}")\n\t(paper "User" {sheet_w} {sheet_h})\n'
           + "\n".join(body) + "\n)\n")
    Path(outpath).write_text(out)
    print(f"  {len(pos)} symbols, {drawn} nets wired, {labelled} pin labels, "
          f"{len(clusters)} clusters")
    if missing:
        print(f"  symbol not found: {sorted(set(missing))}")
    print(f"  wrote {outpath}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
