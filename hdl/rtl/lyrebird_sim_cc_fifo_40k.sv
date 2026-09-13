// SIMULATION SCAFFOLDING. NOT DESIGN RTL.
//
// Behavioural model of the GateMate CC_FIFO_40K block RAM hard FIFO, in the
// configuration lyrebird_elastic uses: SDP, 80 bits wide, 512 deep, write and
// read ports on separate clocks. Never synthesised: Yosys treats CC_FIFO_40K
// as a black box and nextpnr-himbaechel configures the real block, so this
// file must never be passed to tools/synth.sh. Pass sources explicitly.
//
// **Why it exists.** Yosys ships a model of the primitive in
// $(yosys-config --datdir)/gatemate/cells_sim.v and that model cannot be used
// here. Its memory addressing is `{wr_pointer[tp-1:0], {(15-tp){1'b0}}}`,
// which for the 80-bit geometry strides 64 bits per entry while writing 80,
// so consecutive entries overlap and every word loses its top 16 bits to the
// one written after it. Writing four distinct 80-bit words and reading them
// back returns the low 16 bits of word n+1 in the top 16 bits of word n, and
// only the last word written survives intact. The same off-by-stride hits
// every width from 5 bits up, because 40,960 divides by 5, 10, 20, 40 and 80
// and the model addresses in powers of two.
//
// What is modelled, because the design depends on it:
//
//   - A read is registered and takes a clock. A_EN with the FIFO non-empty
//     puts the word on A_DO/B_DO at the *next* edge, and advances the pointer.
//   - A read while empty and a write while full are ignored, exactly as the
//     hard block ignores them; no data moves and no pointer advances.
//   - The flags cross domains through two flops, so F_EMPTY and
//     F_ALMOST_EMPTY lag a write by two read clocks and F_ALMOST_FULL lags a
//     read by two write clocks. Both err towards more-empty and more-full,
//     which is the safe direction and the one the design has to tolerate.
//   - The offsets are static parameters. SDP mode has no dynamic offset
//     inputs, per docs/decisions/0011-pack-three-samples-per-fifo-word.md.
//
// The hard block carries its pointers across the domains in Gray code. This
// model synchronises them in binary, which is identical in a zero-delay
// two-state simulator -- both give a cleanly stale value -- and differs only
// on silicon, where Gray coding is what makes a multi-bit crossing safe.
//
// Ports are the subset lyrebird_elastic connects. Connecting one this model
// does not declare is an error rather than a silent difference, which is the
// behaviour worth having.

module CC_FIFO_40K #(
    parameter        RAM_MODE            = "TDP",
    parameter        FIFO_MODE           = "SYNC",
    parameter int    A_WIDTH             = 0,
    parameter int    B_WIDTH             = 0,
    parameter [14:0] ALMOST_FULL_OFFSET  = 15'd0,
    parameter [14:0] ALMOST_EMPTY_OFFSET = 15'd0
) (
    // Pop port A.
    input  logic        A_CLK,
    input  logic        A_EN,
    output logic [39:0] A_DO,
    output logic [39:0] B_DO,
    // Push port B. In SDP the two data ports are halves of one 80-bit word.
    input  logic        B_CLK,
    input  logic        B_EN,
    input  logic        B_WE,
    input  logic [39:0] A_DI,
    input  logic [39:0] B_DI,
    input  logic [39:0] A_BM,
    input  logic [39:0] B_BM,
    // Control and flags.
    input  logic        F_RST_N,
    output logic        F_EMPTY,
    output logic        F_ALMOST_FULL,
    output logic        F_ALMOST_EMPTY
);

    localparam int Depth = 512;

    initial begin
        if (RAM_MODE != "SDP" || A_WIDTH != 80 || B_WIDTH != 80) begin
            $fatal(1, "lyrebird_sim_cc_fifo_40k models SDP 80-bit only");
        end
    end

    logic [79:0] mem [Depth];
    logic [9:0]  wr_ptr_q, rd_ptr_q;          // 9 address bits plus a wrap bit
    logic [9:0]  wr_ptr_rd_q0, wr_ptr_rd_q1;  // write pointer seen by the reader
    logic [9:0]  rd_ptr_wr_q0, rd_ptr_wr_q1;  // read pointer seen by the writer
    logic [9:0]  wr_ptr_rd, rd_ptr_wr;
    logic [9:0]  fill_rd, fill_wr;
    logic        wr_clk, rd_clk;
    logic        do_push, do_pop;

    // Not a port: lyrebird_elastic flow-controls on F_ALMOST_FULL and never
    // connects F_FULL, and a model that declares only what the design uses
    // turns a future mismatch into an error rather than a silent difference.
    logic        f_full;

    assign wr_clk = (FIFO_MODE == "ASYNC") ? B_CLK : A_CLK;
    assign rd_clk = A_CLK;

    generate
        if (FIFO_MODE == "ASYNC") begin : gen_async
            assign wr_ptr_rd = wr_ptr_rd_q1;
            assign rd_ptr_wr = rd_ptr_wr_q1;

            always_ff @(posedge rd_clk or negedge F_RST_N) begin
                if (!F_RST_N) begin
                    wr_ptr_rd_q0 <= 10'd0;
                    wr_ptr_rd_q1 <= 10'd0;
                end else begin
                    wr_ptr_rd_q0 <= wr_ptr_q;
                    wr_ptr_rd_q1 <= wr_ptr_rd_q0;
                end
            end

            always_ff @(posedge wr_clk or negedge F_RST_N) begin
                if (!F_RST_N) begin
                    rd_ptr_wr_q0 <= 10'd0;
                    rd_ptr_wr_q1 <= 10'd0;
                end else begin
                    rd_ptr_wr_q0 <= rd_ptr_q;
                    rd_ptr_wr_q1 <= rd_ptr_wr_q0;
                end
            end
        end else begin : gen_sync
            assign wr_ptr_rd    = wr_ptr_q;
            assign rd_ptr_wr    = rd_ptr_q;
            assign wr_ptr_rd_q0 = 10'd0;
            assign wr_ptr_rd_q1 = 10'd0;
            assign rd_ptr_wr_q0 = 10'd0;
            assign rd_ptr_wr_q1 = 10'd0;
        end
    endgenerate

    assign fill_rd = wr_ptr_rd - rd_ptr_q;
    assign fill_wr = wr_ptr_q - rd_ptr_wr;

    assign F_EMPTY        = (rd_ptr_q == wr_ptr_rd);
    assign f_full         = (wr_ptr_q[9] != rd_ptr_wr[9])
                            && (wr_ptr_q[8:0] == rd_ptr_wr[8:0]);
    assign F_ALMOST_EMPTY = ({5'd0, fill_rd} <= ALMOST_EMPTY_OFFSET);
    assign F_ALMOST_FULL  = ({5'd0, fill_wr} >= (15'(Depth) - ALMOST_FULL_OFFSET));

    assign do_push = B_EN && B_WE && !f_full;
    assign do_pop  = A_EN && !F_EMPTY;

    always_ff @(posedge wr_clk or negedge F_RST_N) begin
        if (!F_RST_N) begin
            wr_ptr_q <= 10'd0;
        end else if (do_push) begin
            mem[wr_ptr_q[8:0]] <= (mem[wr_ptr_q[8:0]] & ~{B_BM, A_BM})
                                | ({B_DI, A_DI} & {B_BM, A_BM});
            wr_ptr_q <= wr_ptr_q + 10'd1;
        end
    end

    always_ff @(posedge rd_clk or negedge F_RST_N) begin
        if (!F_RST_N) begin
            rd_ptr_q <= 10'd0;
            A_DO     <= 40'd0;
            B_DO     <= 40'd0;
        end else if (do_pop) begin
            A_DO     <= mem[rd_ptr_q[8:0]][39:0];
            B_DO     <= mem[rd_ptr_q[8:0]][79:40];
            rd_ptr_q <= rd_ptr_q + 10'd1;
        end
    end

endmodule
