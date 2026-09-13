// FPGA-side master of the FT601Q 245 synchronous FIFO bus, receive direction.
//
// Bus and mode are per docs/decisions/0005-ft601q-bridge-io-voltage.md: 32-bit
// DATA with four byte enables at 66.67 MHz. The FPGA is the master, so this
// module drives RD_N and OE_N while the bridge drives RXF_N and DATA. Only the
// receive direction carries audio; the transmit direction belongs to a
// separate module and is not touched here.
//
// The handshake has one rule that is easy to get wrong. OE_N must lead RD_N by
// a clock: the bridge only drives DATA once OE_N is low, so asserting RD_N in
// the same cycle samples a bus nobody owns. A word then transfers on every
// rising edge where RXF_N, RD_N and OE_N are all low.
//
// Backpressure deasserts RD_N but holds OE_N. That pauses a burst without
// giving the bus back, so resuming costs one clock instead of the three a full
// OE_N re-arbitration would. Because RD_N is registered, ready_i is one clock
// late: a word already committed still transfers after ready_i falls, so the
// consumer must have room for one more word at the moment it deasserts.
// lyrebird_elastic deasserts on the FIFO's almost-full flag, which leaves
// several words of slack rather than one.
//
// Byte enables are checked, not assumed. The wire format in
// docs/decisions/0010-192khz-and-control-word.md puts one padded sample in one
// word with all four BE asserted, so a partial BE is a fragment rather than a
// sample. Such a word is counted and dropped: word_o never carries it, because
// a fragment that reaches the tag decoder is a sample with a plausible tag and
// three wrong bytes.
//
// SystemVerilog restricted to the subset Yosys accepts: logic, always_ff,
// always_comb, localparam. No interfaces, no packed structs.

module lyrebird_ft601q_read (
    input  logic        clk_i,          // FT601Q CLK, 66.67 MHz on the board
    input  logic        rst_ni,

    // FT601Q 245 synchronous FIFO, receive direction.
    input  logic [31:0] fifo_data_i,
    input  logic [3:0]  fifo_be_i,
    input  logic        fifo_rxf_ni,
    output logic        fifo_rd_no,
    output logic        fifo_oe_no,

    // Downstream flow control. Deassert with one word of slack; see above.
    input  logic        ready_i,

    // One accepted word per valid strobe.
    output logic [31:0] word_o,
    output logic        word_valid_o,

    // For the status word, and for tests.
    output logic [15:0] word_count_o,
    output logic [15:0] be_error_count_o
);

    localparam logic [1:0] StIdle  = 2'd0;  // bus released
    localparam logic [1:0] StLead  = 2'd1;  // OE_N asserted, RD_N still high
    localparam logic [1:0] StRead  = 2'd2;  // transferring
    localparam logic [1:0] StPause = 2'd3;  // bus held, RD_N deasserted

    logic [1:0] state_q;
    logic       take, be_ok;

    // All four byte enables, or the word is a fragment.
    assign be_ok = (fifo_be_i == 4'hF);

    // The transfer condition, written out rather than inferred from the state,
    // because it is the bus rule: RXF_N, RD_N and OE_N all low at a rising
    // edge moves one word.
    assign take = (state_q == StRead) && !fifo_rxf_ni
                  && !fifo_rd_no && !fifo_oe_no;

    always_ff @(posedge clk_i) begin
        if (!rst_ni) begin
            state_q    <= StIdle;
            fifo_oe_no <= 1'b1;
            fifo_rd_no <= 1'b1;
        end else begin
            case (state_q)
                StIdle: begin
                    if (!fifo_rxf_ni && ready_i) begin
                        fifo_oe_no <= 1'b0;
                        state_q    <= StLead;
                    end
                end

                // Exactly one clock of OE_N ahead of RD_N. RXF_N may have gone
                // away again in the meantime, which costs nothing: no transfer
                // happens with RXF_N high and StRead falls back to StIdle.
                StLead: begin
                    fifo_rd_no <= 1'b0;
                    state_q    <= StRead;
                end

                StRead: begin
                    if (fifo_rxf_ni) begin
                        fifo_rd_no <= 1'b1;
                        fifo_oe_no <= 1'b1;
                        state_q    <= StIdle;
                    end else if (!ready_i) begin
                        fifo_rd_no <= 1'b1;   // OE_N stays low: the bus is ours
                        state_q    <= StPause;
                    end
                end

                default: begin  // StPause
                    if (fifo_rxf_ni) begin
                        fifo_oe_no <= 1'b1;
                        state_q    <= StIdle;
                    end else if (ready_i) begin
                        fifo_rd_no <= 1'b0;   // OE_N never left, so no lead
                        state_q    <= StRead;
                    end
                end
            endcase
        end
    end

    always_ff @(posedge clk_i) begin
        if (!rst_ni) begin
            word_o           <= 32'd0;
            word_valid_o     <= 1'b0;
            word_count_o     <= 16'd0;
            be_error_count_o <= 16'd0;
        end else begin
            word_valid_o <= take && be_ok;
            if (take && be_ok) begin
                word_o       <= fifo_data_i;
                word_count_o <= word_count_o + 16'd1;
            end
            if (take && !be_ok) begin
                be_error_count_o <= be_error_count_o + 16'd1;
            end
        end
    end

endmodule
