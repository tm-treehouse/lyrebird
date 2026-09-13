# Opening this in KiCad

**There are no schematic files.** Not missing, not lost: the boards are
described as code and never drawn. `netlist/` generates KiCad netlists
directly, so there is nothing for the schematic editor to open, and there will
not be unless someone decides to draw them. See
[netlist/README.md](netlist/README.md) for why, including the note that SKiDL's
own schematic generator was tried and does not complete on a 324-ball part.

What you can open is the **PCB editor**, driven by the netlist.

## Getting a board to lay out

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
