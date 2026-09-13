#!/usr/bin/env python3
"""Split a netlist into one schematic sheet per functional block.

    ./.venv/bin/python tools/netlist_to_sheets.py <netlist.net> <out-dir>

Sheets are anchored on the major parts, meaning anything with eight or more
pins: the FPGA, the bridge, the regulators, the connectors. Every other part
joins the major part it actually belongs with.

Association is by shared net, with two refinements that matter. Ground is
ignored, because it touches everything and associates nothing. And a part that
touches only supply rails, which is most decoupling capacitors, joins the
owner of its rail: the major part with the most pins on it. Without that rule
a bypass capacitor lands with whichever part happens to share its rail, and on
this board that put 55 parts on the programming header.

The single-sheet generator remains in netlist_to_schematic.py and shares its
parsing, symbol resolution and routing.
"""

import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from netlist_to_schematic import (  # noqa: E402
    GRID, Q, collect_pins, dump, kids, parse, resolve, val,
)

MAJOR_PINS = 8


def is_supply(name):
    return name.startswith(("+", "VBUS")) or name.startswith("GND")


def sections(genfile):
    """Line number -> functional heading, from the generator's own comments.

    The generators are already divided into labelled sections. Those headings
    are better sheet names than anything inferable from the netlist, and they
    stay correct because they are the source the netlist was built from.
    """
    src = Path(genfile).read_text().splitlines()
    out = []
    for i, line in enumerate(src, 1):
        t = line.strip()
        if t.startswith("# ----"):
            out.append((i, t.lstrip("# -").strip().rstrip(".")))
    return out


def section_of(line_no, secs):
    best = None
    for ln, title in secs:
        if ln <= line_no:
            best = title
        else:
            break
    return best


def read(netlist):
    root = parse(Path(netlist).read_text())[0]
    comps = {}
    for b in kids(root, "components"):
        for c in kids(b, "comp"):
            ls = kids(c, "libsource")
            src = ""
            for fb in kids(c, "fields"):
                for fld in kids(fb, "field"):
                    if val(fld, "name") == "SKiDL Line" and len(fld) > 2:
                        src = fld[2]
            comps[val(c, "ref")] = {
                "ref": val(c, "ref"), "value": val(c, "value"),
                "lib": val(ls[0], "lib") if ls else "",
                "part": val(ls[0], "part") if ls else "",
                "src": src,
            }
    nets = []
    for b in kids(root, "nets"):
        for n in kids(b, "net"):
            nets.append((val(n, "name"),
                         [(val(nd, "ref"), val(nd, "pin"))
                          for nd in kids(n, "node")]))
    return comps, nets


def assign_sheets(comps, nets):
    npins = Counter()
    sig, rail = defaultdict(set), defaultdict(set)
    rail_pins = defaultdict(Counter)
    for name, nodes in nets:
        for r, _ in nodes:
            npins[r] += 1
            if name == "GND":
                continue
            if is_supply(name):
                rail[r].add(name)
                rail_pins[name][r] += 1
            else:
                sig[r].add(name)

    major = sorted(r for r, c in npins.items() if c >= MAJOR_PINS)
    owner = {n: c.most_common(1)[0][0] for n, c in rail_pins.items()
             if c and c.most_common(1)[0][0] in major}

    sheet = {}
    for r in comps:
        if r in major:
            sheet[r] = r
            continue
        hits = Counter({m: len(sig[r] & sig[m]) for m in major})
        hits = Counter({k: v for k, v in hits.items() if v})
        if hits:
            sheet[r] = hits.most_common(1)[0][0]
            continue
        owners = Counter(owner[n] for n in rail[r] if n in owner)
        sheet[r] = owners.most_common(1)[0][0] if owners else "misc"
    return sheet, major


def build_sheet(title, refs, comps, nets, used, pins_of, outpath):
    """One sheet: cluster, place, wire the small nets, label the rest."""
    local = set(refs)
    wire_nets, label_nets = [], []
    for name, nodes in nets:
        here = [(r, p) for r, p in nodes if r in local]
        if not here:
            continue
        whole = len(here) == len(nodes)
        if whole and 2 <= len(here) <= 3 and not is_supply(name):
            wire_nets.append((name, here))
        else:
            label_nets.append((name, here))

    adj = defaultdict(set)
    for _, nodes in wire_nets:
        rs = [r for r, _ in nodes]
        for a in rs:
            for b in rs:
                if a != b:
                    adj[a].add(b)
    seen, clusters = set(), []
    for r in sorted(local):
        if r in seen:
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
        clusters.append(sorted(group))
    clusters.sort(key=len, reverse=True)

    def extent(r):
        ps = pins_of.get(r, [])
        if not ps:
            return 10.0, 10.0
        return (max(p[1] for p in ps) - min(p[1] for p in ps),
                max(p[2] for p in ps) - min(p[2] for p in ps))

    PAD_X, PAD_Y = 30.0, 26.0
    blocks = []
    for group in clusters:
        n = len(group)
        cols = max(1, int(math.ceil(math.sqrt(n))))
        cells = [(r, *extent(r)) for r in group]
        colw = [0.0] * cols
        rows = []
        for i in range(0, n, cols):
            row = cells[i:i + cols]
            rows.append(max(c[2] for c in row) + PAD_Y)
            for j, c in enumerate(row):
                colw[j] = max(colw[j], c[1] + PAD_X)
        pl, yo = [], 0.0
        for i in range(0, n, cols):
            row, xo = cells[i:i + cols], 0.0
            for j, (r, w, h) in enumerate(row):
                pl.append((r, xo + colw[j] / 2, yo + rows[i // cols] / 2, w, h))
                xo += colw[j]
            yo += rows[i // cols]
        blocks.append((pl, sum(colw), yo))

    total = sum(bw * bh for _, bw, bh in blocks) or 1.0
    target = max(math.sqrt(total * 2.0), max(b[1] for b in blocks) + 20.0)
    pos, x, y, shelf, mx = {}, 20.0, 20.0, 0.0, 0.0
    for pl, bw, bh in blocks:
        if x + bw > target and x > 20.0:
            x, y, shelf = 20.0, y + shelf + 14.0, 0.0
        for r, dx, dy, w, h in pl:
            pos[r] = (round((x + dx) / GRID) * GRID,
                      round((y + dy) / GRID) * GRID, w, h)
        x += bw + 14.0
        mx = max(mx, x)
        shelf = max(shelf, bh)

    body, uid = [], [0]

    def nid():
        uid[0] += 1
        return f"00000000-0000-0000-0000-{uid[0]:012d}"

    keys = {f'{comps[r]["lib"]}:{comps[r]["part"]}' for r in local}
    lb = ["\t(lib_symbols"]
    for k in sorted(keys):
        if k in used:
            t = list(used[k])
            t[1] = Q(k)
            lb.append("\t\t" + dump(t))
    lb.append("\t)")
    body.append("\n".join(lb))

    for r, (cx, cy, w, h) in pos.items():
        c = comps[r]
        body.append(
            f'\t(symbol (lib_id "{c["lib"]}:{c["part"]}") (at {cx} {cy} 0) '
            f'(unit 1)\n\t\t(exclude_from_sim no) (in_bom yes) (on_board yes) '
            f'(dnp no)\n\t\t(uuid "{nid()}")\n'
            f'\t\t(property "Reference" "{r}" (at {cx} {cy - h/2 - 6.5} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27))))\n'
            f'\t\t(property "Value" "{c["value"]}" (at {cx} {cy + h/2 + 6.5} 0)\n'
            f'\t\t\t(effects (font (size 1.27 1.27))))\n'
            f'\t\t(instances (project "" (path "/" (reference "{r}") '
            f'(unit 1))))\n\t)')

    def pin_xy(r, num):
        if r not in pos:
            return None
        cx, cy, _, _ = pos[r]
        for n, px, py, _ in pins_of.get(r, []):
            if n == num:
                return (round((cx + px) / GRID) * GRID,
                        round((cy - py) / GRID) * GRID)
        return None

    def wire(a, b):
        body.append(f'\t(wire (pts (xy {a[0]} {a[1]}) (xy {b[0]} {b[1]}))\n'
                    f'\t\t(stroke (width 0) (type default)) (uuid "{nid()}"))')

    drawn = 0
    for name, nodes in wire_nets:
        pts = [p for p in (pin_xy(r, pn) for r, pn in nodes) if p]
        if len(pts) < 2:
            continue
        if len(pts) == 2:
            a, b = pts
            if a[0] == b[0] or a[1] == b[1]:
                wire(a, b)
            else:
                wire(a, (a[0], b[1]))
                wire((a[0], b[1]), b)
        else:
            bus = round(sum(p[0] for p in pts) / len(pts) / GRID) * GRID
            ys = [p[1] for p in pts]
            wire((bus, min(ys)), (bus, max(ys)))
            for p in pts:
                if p[0] != bus:
                    wire(p, (bus, p[1]))
                body.append(f'\t(junction (at {bus} {p[1]}) (diameter 0)\n'
                            f'\t\t(color 0 0 0 0) (uuid "{nid()}"))')
        drawn += 1

    lab = 0
    for name, nodes in label_nets:
        for r, pn in nodes:
            pt = pin_xy(r, pn)
            if not pt:
                continue
            body.append(
                f'\t(global_label "{name}" (shape passive) '
                f'(at {pt[0]} {pt[1]} 0)\n'
                f'\t\t(effects (font (size 1.0 1.0)) (justify right))\n'
                f'\t\t(uuid "{nid()}"))')
            lab += 1

    sw, sh = round(mx + 20.0), round(y + shelf + 20.0)
    Path(outpath).write_text(
        '(kicad_sch\n\t(version 20231120)\n\t(generator "lyrebird")\n'
        f'\t(uuid "{nid()}")\n\t(paper "User" {sw} {sh})\n'
        f'\t(title_block (title "{title}"))\n'
        + "\n".join(body) + "\n)\n")
    return len(pos), drawn, lab


def main(netlist, outdir):
    comps, nets = read(netlist)
    sheet, major = assign_sheets(comps, nets)

    used, pins_of = {}, {}
    for c in comps.values():
        key = f'{c["lib"]}:{c["part"]}'
        if key not in used:
            sym = resolve(c["lib"], c["part"])
            if sym is not None:
                used[key] = sym
        pins_of[c["ref"]] = collect_pins(used[key], []) if key in used else []

    # Name each anchor by the generator section that created it, so several
    # anchors from one section share a sheet. A resistor array on its own is
    # not a functional block; "Element resistors" is.
    gen = None
    for c in comps.values():
        if c["src"]:
            gen = Path(netlist).parent.parent / "netlist" / c["src"].split(":")[0]
            break
    secs = sections(gen) if gen and gen.is_file() else []

    name_of = {}
    for r in set(sheet.values()):
        c = comps.get(r)
        title = None
        if c and c["src"] and secs:
            try:
                title = section_of(int(c["src"].split(":")[1]), secs)
            except ValueError:
                title = None
        # Major parts come from the shared parts library, which has no
        # section comments, so fall back to the part's value. That reads
        # better than a reference designator anyway.
        if not title and c and c["value"]:
            title = f'{r} {c["value"]}'
        name_of[r] = title or (r if c else "Other")

    groups = defaultdict(list)
    for r, s in sheet.items():
        groups[name_of.get(s, s)].append(r)

    out = Path(outdir)
    out.mkdir(parents=True, exist_ok=True)
    order = sorted(groups, key=lambda k: (-len(groups[k]), k))
    print(f"  {len(comps)} parts across {len(order)} sheets")
    for i, s in enumerate(order, 1):
        refs = groups[s]
        safe = "".join(ch if ch.isalnum() or ch in " -" else "" for ch in s)
        safe = "-".join(safe.split())[:48] or f"sheet{i}"
        fn = out / f"{i:02d}-{safe}.kicad_sch"
        n, w, l = build_sheet(s, refs, comps, nets, used, pins_of, fn)
        print(f"    {s[:46]:46} {n:3} parts, {w:3} wired, {l:4} labels")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1], sys.argv[2]))
