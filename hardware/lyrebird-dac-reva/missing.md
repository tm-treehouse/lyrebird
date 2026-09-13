# What is missing, output module

**This is deliberately not a snapshot.** The netlist is the authority on
completeness, and it changes. Regenerate the audit rather than trusting a list
someone wrote down and stopped updating:

```sh
export KICAD10_SYMBOL_DIR="/Applications/KiCad/KiCad.app/Contents/SharedSupport/symbols"
./.venv/bin/python hardware/netlist/output_module.py
```

An unconnected pin is a missing part. That is the whole reason the boards are
described as code: something nobody remembered to add shows up as an open pin
instead of as an omission from a document.

To list them:

```sh
./.venv/bin/python - <<'PY'
import sys, os
sys.path.insert(0, "hardware/netlist")
os.chdir("hardware/lyrebird-dac-reva"); sys.path.insert(0, "../netlist")
import output_module as b
for part in b.build():
    open_pins = [str(p.name) for p in part.pins if not p.is_connected()]
    print(f"{part.ref}: {len(open_pins)} unconnected of {len(part.pins)}")
    if open_pins:
        print("   ", sorted(set(open_pins)))
PY
```

## Known gaps, and where they are tracked

The current list, with reasoning, is in
[../../docs/open-items.md](../../docs/open-items.md) under "Blocking a
schematic". It separates parts that are selected but not yet wired from parts
that were never chosen, and from values still undetermined.

Four symbols in the netlist are deliberate placeholders carrying the intended
part in their value field; [../netlist/README.md](../netlist/README.md) lists
them. A placeholder is not a selected part.
