#!/usr/bin/env python3
"""Import a KiCad netlist into a new board, without the GUI.

    <kicad python> tools/netlist_to_pcb.py <netlist.net> <out.kicad_pcb>

KiCad exposes no netlist reader to Python and kicad-cli's "import" is for
foreign PCB formats, not netlists, so this does the job the GUI's
File > Import > Netlist would do: load each footprint, place it, and attach
pads to nets.

Footprints are laid out on a grid outside the origin. That is deliberate and
is not layout: ball escape, controlled-impedance pairs and the analog section
all need a person. This only gets you to a board worth opening.

Must run under KiCad's bundled Python, which is the only one with pcbnew.
"""

import sys
from pathlib import Path

import pcbnew

STOCK = Path("/Applications/KiCad/KiCad.app/Contents/SharedSupport/footprints")
PROJECT = Path(__file__).resolve().parent.parent / "hardware" / "footprints"


def parse(text):
    """Minimal s-expression reader. Returns nested lists of str."""
    tok = text.replace("(", " ( ").replace(")", " ) ").split()
    def build(i):
        out = []
        while i < len(tok):
            t = tok[i]
            if t == "(":
                sub, i = build(i + 1)
                out.append(sub)
            elif t == ")":
                return out, i + 1
            else:
                out.append(t.strip('"'))
                i += 1
        return out, i
    return build(0)[0][0]


def find_all(node, key):
    """Every direct child list whose head is `key`."""
    return [c for c in node if isinstance(c, list) and c and c[0] == key]


def first_val(node, key, default=""):
    for c in find_all(node, key):
        return c[1] if len(c) > 1 else default
    return default


def load_footprint(spec):
    lib, name = spec.split(":", 1)
    for root in (PROJECT, STOCK):
        path = root / f"{lib}.pretty"
        if path.is_dir():
            fp = pcbnew.FootprintLoad(str(path), name)
            if fp:
                return fp
    return None


def main(netlist, out):
    root = parse(Path(netlist).read_text())

    comps = []
    for block in find_all(root, "components"):
        for c in find_all(block, "comp"):
            comps.append((first_val(c, "ref"), first_val(c, "value"),
                          first_val(c, "footprint")))

    nets = []
    for block in find_all(root, "nets"):
        for n in find_all(block, "net"):
            nodes = [(first_val(nd, "ref"), first_val(nd, "pin"))
                     for nd in find_all(n, "node")]
            nets.append((first_val(n, "name"), nodes))

    print(f"  {len(comps)} components, {len(nets)} nets")

    board = pcbnew.CreateEmptyBoard()
    placed, failed = {}, []

    # Grid placement, widest part first so rows stay tidy.
    x = y = 0.0
    row_h = 0.0
    LIMIT = 260.0
    for ref, value, fpspec in sorted(comps, key=lambda c: c[0]):
        fp = load_footprint(fpspec)
        if fp is None:
            failed.append((ref, fpspec))
            continue
        fp.SetReference(ref)
        fp.SetValue(value)
        bb = fp.GetBoundingBox()
        w = pcbnew.ToMM(bb.GetWidth()) + 2.0
        h = pcbnew.ToMM(bb.GetHeight()) + 2.0
        if x + w > LIMIT:
            x, y, row_h = 0.0, y + row_h, 0.0
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(x + w / 2),
                                       pcbnew.FromMM(y + h / 2)))
        board.Add(fp)
        placed[ref] = fp
        x += w
        row_h = max(row_h, h)

    attached = orphan = 0
    for name, nodes in nets:
        ni = pcbnew.NETINFO_ITEM(board, name)
        board.Add(ni)
        for ref, pin in nodes:
            fp = placed.get(ref)
            pad = fp.FindPadByNumber(pin) if fp else None
            if pad is None:
                orphan += 1
            else:
                pad.SetNet(ni)
                attached += 1

    pcbnew.SaveBoard(out, board)
    print(f"  placed {len(placed)}, pads on nets {attached}")
    if failed:
        print(f"  FOOTPRINT NOT FOUND for {len(failed)}: {failed[:4]}")
    if orphan:
        print(f"  pads not matched: {orphan}")
    print(f"  wrote {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
