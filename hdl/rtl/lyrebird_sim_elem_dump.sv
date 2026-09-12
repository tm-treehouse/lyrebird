// SIMULATION SCAFFOLDING. NOT DESIGN RTL.
//
// Never synthesised, never on the board. It uses $fopen and $fwrite, which
// Yosys does not accept, and it is deliberately kept out of any toplevel that
// is handed to tools/synth.sh.
//
// Writes the element lines to a flat binary file so the long audio measurement
// can be analysed afterwards in numpy. This exists because
// docs/decisions/0013-simulation-and-build-toolchain.md is explicit that the
// measurement must not read 28 element lines from Python on every cycle: the
// language binding becomes the bottleneck rather than the simulator, at around
// 350,000 ns of simulated time per wall second. Dumping from the simulation
// instead inverts a useful ratio -- simulate once, analyse many times.
//
// FILE FORMAT
//
//   No header. A flat sequence of 4-byte records, little-endian, one record
//   per clock edge on which en_i and sample_i are both high. Each record is
//   the 32-bit element vector ELEM[31:0] as allocated in
//   hardware/interface.md, bit 0 in the least significant bit of the first
//   byte.
//
//   numpy reads it in one call:
//
//       records = numpy.fromfile(path, dtype="<u4")
//
//   hdl/sim/sink_elements.py has the reader and the decode helpers, and
//   hdl/sim/README.md documents the format again next to them.
//
// The path comes from the DumpPath parameter, overridden by a +elemdump=<path>
// plusarg when the caller can pass one. The file is opened when en_i rises and
// closed when en_i falls, so a testbench can read it back mid-simulation by
// dropping en_i; it is also closed in a final block in case the simulation
// ends with en_i still high.

module lyrebird_sim_elem_dump #(
    parameter string DumpPath = "elem_dump.bin"
) (
    input  logic        clk_i,
    input  logic        en_i,      // file open while high
    input  logic        sample_i,  // write one record per high cycle
    input  logic [31:0] elem_i
);

    // File I/O needs blocking assignment inside the clocked process, because
    // the descriptor from $fopen has to be usable in the same evaluation.
    // Both warnings below are that, and nothing else.
    // verilator lint_off BLKSEQ
    // verilator lint_off PROCASSINIT
    int    fd = 0;
    string path;
    logic  open_q = 1'b0;

    always_ff @(posedge clk_i) begin
        if (en_i) begin
            if (!open_q) begin
                if (!$value$plusargs("elemdump=%s", path)) path = DumpPath;
                fd     = $fopen(path, "wb");
                open_q <= 1'b1;
                if (fd == 0) begin
                    $display("%m: cannot open '%s' for writing, element dump disabled", path);
                end else begin
                    $display("%m: element dump -> %s", path);
                end
            end
            if (fd != 0 && sample_i) begin
                $fwrite(fd, "%c%c%c%c",
                        elem_i[7:0], elem_i[15:8], elem_i[23:16], elem_i[31:24]);
            end
        end else if (open_q) begin
            if (fd != 0) $fclose(fd);
            fd     = 0;
            open_q <= 1'b0;
        end
    end

    final begin
        if (fd != 0) $fclose(fd);
    end
    // verilator lint_on PROCASSINIT
    // verilator lint_on BLKSEQ

endmodule
