# Opening this in KiCad

**There are no schematic files.** Not missing, not lost: the boards are
described as code and never drawn. `netlist/` generates KiCad netlists
directly, so there is nothing for the schematic editor to open, and there will
not be unless someone decides to draw them. See
[netlist/README.md](netlist/README.md) for why, including the note that SKiDL's
own schematic generator was tried and does not complete on a 324-ball part.

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
