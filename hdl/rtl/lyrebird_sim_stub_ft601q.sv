// SIMULATION SCAFFOLDING. NOT DESIGN RTL.
//
// Never synthesised, never on the board. This is the stub DUT that
// hdl/sim/test_bfm.py drives, and it exists only to give the FT601Q bus
// functional model and the element sink something to talk to. The real
// receive path -- elastic buffer, interpolator, modulator, DWA -- replaces it
// module by module, and each replacement should be able to reuse
// hdl/sim/bfm_ft601q.py unchanged.
//
// What it does, end to end:
//
//   1. Masters the FT601Q 245 synchronous FIFO read handshake: OE_N one clock
//      ahead of RD_N, one word per clock while RXF_N stays low.
//   2. Requires all four byte enables, per the wire format in
//      docs/decisions/0010-192khz-and-control-word.md, and counts words that
//      arrive with a partial BE rather than accepting them.
//   3. Decodes each word with the real lyrebird_tag_decode.
//   4. Tracks left/right alternation, so a word the bridge drops shows up as a
//      resync event. That is the whole point of the drop injection in the BFM.
//   5. Generates 28 element lines from the top three bits of each sample, with
//      a rotation, so the sink has a constant-loading thermometer pattern to
//      decode and cannot assume a stable code-to-line mapping.
//   6. Writes status words back on the transmit direction while status_en_i is
//      high, so TXE_N back-pressure is exercised too.
//
// DATA is split into fifo_data_i and fifo_data_o because a Verilator toplevel
// cannot usefully expose an inout. On the board it is one bidirectional pad,
// and fifo_oe_no / fifo_wr_no say which end is driving it.
//
// Element generation here is arbitrary scaffolding, not the design's DWA. It
// only honours the two properties the sink relies on: exactly seven lines high
// per channel at every code, and a rotation that moves which lines carry it.

module lyrebird_sim_stub_ft601q (
    input  logic        clk_i,     // FT601Q CLK, 66.67 MHz on the board
    input  logic        rst_ni,

    // FT601Q 245 synchronous FIFO. The FPGA is the bus master.
    input  logic [31:0] fifo_data_i,
    input  logic [3:0]  fifo_be_i,
    input  logic        fifo_rxf_ni,
    input  logic        fifo_txe_ni,
    output logic        fifo_rd_no,
    output logic        fifo_oe_no,
    output logic        fifo_wr_no,
    output logic [31:0] fifo_data_o,
    output logic [3:0]  fifo_be_o,
    output logic        fifo_siwu_no,

    // Stub controls, driven from the testbench.
    input  logic        status_en_i,  // emit status words on the transmit channel
    input  logic        dump_en_i,    // element dump file open while high

    // Observability.
    output logic [31:0] word_o,
    output logic        word_valid_o,
    output logic [31:0] word_count_o,
    output logic [31:0] be_error_count_o,
    output logic [31:0] bad_tag_count_o,
    output logic [31:0] resync_count_o,
    output logic        sample_valid_o,
    output logic        sample_right_o,
    output logic [23:0] sample_o,
    output logic        ctrl_valid_o,
    output logic [7:0]  ctrl_opcode_o,
    output logic [15:0] ctrl_payload_o,
    output logic [31:0] ctrl_count_o,
    output logic [27:0] elem_o,
    output logic        elem_valid_o
);

    localparam logic [7:0] TagStatus = 8'h3C;

    localparam logic [1:0] StIdle = 2'd0;
    localparam logic [1:0] StOe   = 2'd1;
    localparam logic [1:0] StRead = 2'd2;

    // ------------------------------------------------------------------
    // Read handshake
    //
    // OE_N has to lead RD_N by a clock: the bridge only drives DATA once OE_N
    // is low, so asserting RD_N in the same cycle would read the bus before
    // the bridge owns it. A word transfers on every rising edge where RXF_N,
    // RD_N and OE_N are all low.
    // ------------------------------------------------------------------
    logic [1:0] state_q;
    logic       take, be_ok;

    assign be_ok = (fifo_be_i == 4'hF);
    assign take  = (state_q == StRead) && !fifo_rxf_ni && !fifo_rd_no && !fifo_oe_no;

    always_ff @(posedge clk_i) begin
        if (!rst_ni) begin
            state_q    <= StIdle;
            fifo_oe_no <= 1'b1;
            fifo_rd_no <= 1'b1;
        end else begin
            case (state_q)
                StIdle: begin
                    if (!fifo_rxf_ni) begin
                        fifo_oe_no <= 1'b0;
                        state_q    <= StOe;
                    end
                end
                StOe: begin
                    fifo_rd_no <= 1'b0;
                    state_q    <= StRead;
                end
                default: begin
                    if (fifo_rxf_ni) begin
                        fifo_rd_no <= 1'b1;
                        fifo_oe_no <= 1'b1;
                        state_q    <= StIdle;
                    end
                end
            endcase
        end
    end

    always_ff @(posedge clk_i) begin
        if (!rst_ni) begin
            word_o           <= 32'd0;
            word_valid_o     <= 1'b0;
            word_count_o     <= 32'd0;
            be_error_count_o <= 32'd0;
        end else begin
            // Latch only on an accepted transfer. Holding the last word means
            // the decoder's registered outputs stay readable after the stream
            // stops, which is what a test wants to assert against.
            if (take) begin
                word_o <= fifo_data_i;
            end
            word_valid_o <= take && be_ok;
            if (take && be_ok) begin
                word_count_o <= word_count_o + 32'd1;
            end
            if (take && !be_ok) begin
                be_error_count_o <= be_error_count_o + 32'd1;
            end
        end
    end

    // ------------------------------------------------------------------
    // Decode, with the real module
    // ------------------------------------------------------------------
    logic bad_tag_o_int;

    lyrebird_tag_decode u_decode (
        .clk_i          (clk_i),
        .rst_ni         (rst_ni),
        .word_i         (word_o),
        .valid_i        (word_valid_o),
        .sample_valid_o (sample_valid_o),
        .sample_right_o (sample_right_o),
        .sample_o       (sample_o),
        .ctrl_valid_o   (ctrl_valid_o),
        .ctrl_opcode_o  (ctrl_opcode_o),
        .ctrl_payload_o (ctrl_payload_o),
        .bad_tag_o      (bad_tag_o_int)
    );

    always_ff @(posedge clk_i) begin
        if (!rst_ni) begin
            bad_tag_count_o <= 32'd0;
            ctrl_count_o    <= 32'd0;
        end else begin
            if (bad_tag_o_int) bad_tag_count_o <= bad_tag_count_o + 32'd1;
            if (ctrl_valid_o)  ctrl_count_o    <= ctrl_count_o + 32'd1;
        end
    end

    // ------------------------------------------------------------------
    // Left/right framing
    //
    // The tags exist to recover alignment when a whole word is lost, per
    // docs/decisions/0005-ft601q-bridge-io-voltage.md. Expect strict
    // alternation and count every break. One dropped sample word gives exactly
    // one resync event.
    // ------------------------------------------------------------------
    logic expect_right_q;

    always_ff @(posedge clk_i) begin
        if (!rst_ni) begin
            expect_right_q <= 1'b0;
            resync_count_o <= 32'd0;
        end else if (sample_valid_o) begin
            if (sample_right_o != expect_right_q) begin
                resync_count_o <= resync_count_o + 32'd1;
            end
            expect_right_q <= ~sample_right_o;
        end
    end

    // ------------------------------------------------------------------
    // Element lines
    //
    // Allocation is hardware/interface.md: ELEM[6:0] left positive,
    // ELEM[13:7] left negative, ELEM[20:14] right positive, ELEM[27:21] right
    // negative. For code k the positive side carries k ones and the negative
    // side 7-k, so exactly seven lines per channel are high at every code and
    // the module's reference loading is constant.
    // ------------------------------------------------------------------
    logic [2:0] left_code_q, right_code;
    logic [2:0] rot_q;
    logic [3:0] rot_index;

    assign right_code = sample_o[23:21];
    assign rot_index  = {1'b0, rot_q};

    // k ones in the low bits, then rotated by rot_index.
    function automatic logic [6:0] therm(logic [2:0] code, logic [3:0] rot);
        logic [6:0]  bits;
        logic [13:0] doubled;
        bits    = 7'h7F >> (4'd7 - {1'b0, code});
        doubled = {bits, bits};
        return doubled[rot +: 7];
    endfunction

    always_ff @(posedge clk_i) begin
        if (!rst_ni) begin
            left_code_q  <= 3'd0;
            rot_q        <= 3'd0;
            elem_o       <= 28'd0;
            elem_valid_o <= 1'b0;
        end else begin
            elem_valid_o <= 1'b0;
            if (sample_valid_o && !sample_right_o) begin
                left_code_q <= sample_o[23:21];
            end
            if (sample_valid_o && sample_right_o) begin
                elem_o <= {therm(3'd7 - right_code,  rot_index),   // right negative
                           therm(right_code,         rot_index),   // right positive
                           therm(3'd7 - left_code_q, rot_index),   // left negative
                           therm(left_code_q,        rot_index)};  // left positive
                elem_valid_o <= 1'b1;
                rot_q        <= (rot_q == 3'd6) ? 3'd0 : rot_q + 3'd1;
            end
        end
    end

    lyrebird_sim_elem_dump #(
        // Relative to the simulation working directory, which hdl/sim/run.py
        // sets to hdl/sim. sim_build/ is git-ignored, so the dump does not
        // leave a stray file in the tree.
        .DumpPath("sim_build/lyrebird_elem_dump.bin")
    ) u_dump (
        .clk_i    (clk_i),
        .en_i     (dump_en_i),
        .sample_i (elem_valid_o),
        .elem_i   ({4'b0000, elem_o})
    );

    // ------------------------------------------------------------------
    // Transmit direction: status words
    //
    // TXE_N low means the bridge has room. WR_N stays asserted across a TXE_N
    // deassertion and DATA is held, which is what the bridge requires and what
    // the BFM checks.
    // ------------------------------------------------------------------
    logic [15:0] status_seq_q;

    assign fifo_siwu_no = 1'b1;  // send-immediate unused; the stream is continuous

    always_ff @(posedge clk_i) begin
        if (!rst_ni) begin
            fifo_wr_no   <= 1'b1;
            fifo_data_o  <= 32'd0;
            fifo_be_o    <= 4'hF;
            status_seq_q <= 16'd0;
        end else begin
            fifo_be_o <= 4'hF;
            if (!status_en_i) begin
                fifo_wr_no <= 1'b1;
            end else if (fifo_wr_no) begin
                fifo_data_o <= {TagStatus, 8'd0, status_seq_q};
                fifo_wr_no  <= 1'b0;
            end else if (!fifo_txe_ni) begin
                // The word on DATA transfers at this edge; present the next.
                status_seq_q <= status_seq_q + 16'd1;
                fifo_data_o  <= {TagStatus, 8'd0, status_seq_q + 16'd1};
            end
        end
    end

endmodule
