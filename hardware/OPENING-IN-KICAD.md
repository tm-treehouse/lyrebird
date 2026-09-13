# Opening this in KiCad

The boards are described as code, so nothing here was drawn by hand. Both a
**schematic** and a **board** are generated from the netlist, and both open in
KiCad.

## To review the circuitry, open the schematic

- `lyrebird-main-reva/lyrebird-main.kicad_sch` — 133 symbols
- `lyrebird-dac-reva/lyrebird-dac.kicad_sch` — 42 symbols

Every part appears as its real symbol with its reference and value.

**Nets of two or three pins are drawn as wires**, and parts sharing one are
placed next to each other so the wire is short. 119 of the main board's 125
nets and 68 of the module's 82 are wired this way. Only ground, the supply
rails and the element bus stay as labels, which is what a person does by hand:
nobody draws a wire joining 245 ground pins.

There is no global routing, which is the part that cannot be automated and
where SKiDL's own schematic generator hangs on the 324-ball part. Two-pin nets
route as an L, three-pin nets as a comb to a shared vertical.

Regenerate after the netlist changes:

```sh
./.venv/bin/python tools/netlist_to_schematic.py \
    hardware/lyrebird-main-reva/lyrebird-main.net \
    hardware/lyrebird-main-reva/lyrebird-main.kicad_sch
```

A PDF of each is committed beside its board, and regenerates with:

```sh
/Applications/KiCad/KiCad.app/Contents/MacOS/kicad-cli sch export pdf \
    --output hardware/lyrebird-main-reva/lyrebird-main-schematic.pdf \
    hardware/lyrebird-main-reva/lyrebird-main.kicad_sch
```

The netlist stays the source of truth. The schematic is generated for reading,
so edits to it will be overwritten.

What you can open is a **board**, generated from the netlist. Both already
exist:

- `lyrebird-main-reva/lyrebird-main.kicad_pcb` — 133 footprints, 721 pads on
  125 nets
- `lyrebird-dac-reva/lyrebird-dac.kicad_pcb` — 42 footprints, 308 pads on
  82 nets

Open either directly. KiCad 10 is a single application, so there is no separate
PCB editor binary to launch; opening the board file routes to the right editor.

Parts are dropped on a grid, which is placement for legibility and not layout.

## Regenerating a board after the netlist changes

```sh
KPY=/Applications/KiCad/KiCad.app/Contents/Frameworks/Python.framework/Versions/Current/bin/python3
$KPY tools/netlist_to_pcb.py \
    hardware/lyrebird-main-reva/lyrebird-main.net \
    hardware/lyrebird-main-reva/lyrebird-main.kicad_pcb
```

That script exists because KiCad exposes no netlist reader to Python, and
`kicad-cli pcb import` handles foreign PCB formats rather than netlists. It
does what the GUI's File, Import, Netlist would do. **It rebuilds the board
from scratch, so any manual layout is lost** — once routing starts, use the
GUI's importer instead, which updates a board in place.

## Doing it by hand instead

1. Generate the netlist, if it is not current:

   ```sh
   export KICAD10_SYMBOL_DIR="/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
   ./.venv/bin/python hardware/netlist/main_board.py      # or output_module.py
   ```

2. Open KiCad, then the **PCB Editor** on its own. There is no project file to
   open first, which is the part that trips people up.

3. **File, Import, Netlist**, and pick
   `hardware/lyrebird-main-reva/lyrebird-main.net` or
   `hardware/lyrebird-dac-reva/lyrebird-dac.net`.

4. Save the resulting board inside its own board directory.

Every component in both netlists carries a footprint, and all 21 distinct
footprints resolve: 20 from the stock libraries and one drawn here.

## The project libraries

`fp-lib-table` and `sym-lib-table` in this directory register the two
project-local libraries, so `lyrebird:` prefixes resolve:

- `symbols/lyrebird.kicad_sym` — the LTM4622, which has no stock symbol.
- `footprints/lyrebird.pretty` — its LGA-25 land pattern, a 5 by 5 grid of
  0.635 mm pads on a 1.27 mm pitch, taken from the suggested PCB layout in the
  datasheet.

If KiCad does not see them, point it at this directory as the project path, or
add the two libraries by hand in **Preferences, Manage Footprint Libraries**.

## What layout still needs a person

Ball escape on a 324-ball package, USB 3.0 pairs with controlled impedance, and
the precision analog section. None of that is usefully automatic, which is the
reason the generated flow stops at the netlist rather than pretending to
produce a board.
