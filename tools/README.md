# tools

Build, program, and bring-up scripts.

Planned entry points:

- synthesis and place-and-route through Yosys and nextpnr-himbaechel
- SPI flash programming over the separate programming header, driven by
  openFPGALoader and an external FTDI adapter. The FPGA loads itself from flash
  at reset in SPI Active mode, so normal operation needs no programmer. See
  [0006](../docs/decisions/0006-configuration-from-spi-flash.md)
- cocotb test runner, including the modulator quality measurement described in
  [hdl/README.md](../hdl/README.md)
- host driver build against D3XX
