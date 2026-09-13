// SIMULATION SCAFFOLDING. NOT DESIGN RTL.
//
// The receive path wired end to end so hdl/sim/bfm_ft601q.py can drive it:
//
//   FT601Q bus -> lyrebird_ft601q_read -> lyrebird_unpack -> lyrebird_elastic
//
// All three are the real modules. This wrapper exists for three reasons, none
// of which belong in design RTL:
//
//   1. The BFM models the whole bus, including the transmit direction. The
//      receive path does not drive that, so it is tied off idle here and
//      TXE_N is exposed as an observable, which keeps the BFM's default signal
//      map working unchanged.
//   2. hdl/sim/run.py registers a suite as a toplevel and a source list, with
//      no way to override parameters, and the elastic buffer's real sizing --
//      25 blocks, a 6,400-word prefill -- would mean pushing 19,200 samples
//      through every test. Three blocks and a nine-word prefill exercise the
//      same round-robin, packing and threshold logic in a few hundred.
//   3. throttle_i gives a test direct control of the bus reader's backpressure
//      input, which in the real design comes from the buffer's almost-full
//      flag and is therefore not reachable from outside.
//
// The SET_RATE and RESET control words are routed to the buffer's flush input,
// which is what docs/decisions/0010-192khz-and-control-word.md requires of the
// real toplevel: samples already buffered belong to the old rate.

module lyrebird_sim_rx (
    // ---- FT601Q bus, 66.67 MHz domain -------------------------------------
    input  logic        clk_i,
    input  logic        rst_ni,

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

    // Force backpressure on the bus reader.
    input  logic        throttle_i,

    // ---- bus-domain observability -----------------------------------------
    output logic [31:0] word_o,
    output logic        word_valid_o,
    output logic [15:0] word_count_o,
    output logic [15:0] be_error_count_o,
    output logic        ready_o,
    output logic        locked_o,
    output logic [15:0] bad_tag_count_o,
    output logic [15:0] resync_count_o,
    output logic        ctrl_valid_o,
    output logic [7:0]  ctrl_opcode_o,
    output logic [15:0] ctrl_payload_o,
    output logic [15:0] overrun_count_o,
    output logic        tx_ready_o,       // TXE_N; the transmit side is idle

    // ---- audio clock domain ------------------------------------------------
    input  logic        mclk_i,
    input  logic        mrst_ni,
    input  logic        tick_i,
    output logic        sample_valid_o,
    output logic        sample_right_o,
    output logic [23:0] sample_o,
    output logic        mute_o,
    output logic        buf_locked_o,
    output logic [15:0] underrun_count_o,
    output logic [15:0] seq_error_count_o
);

    localparam logic [7:0] OpSetRate = 8'h01;
    localparam logic [7:0] OpReset   = 8'h04;

    // The transmit direction belongs to a module that does not exist yet.
    assign fifo_wr_no   = 1'b1;
    assign fifo_data_o  = 32'd0;
    assign fifo_be_o    = 4'hF;
    assign fifo_siwu_no = 1'b1;
    assign tx_ready_o   = ~fifo_txe_ni;

    logic buf_ready, read_ready, flush;

    assign read_ready = buf_ready & ~throttle_i;
    assign ready_o    = read_ready;

    lyrebird_ft601q_read u_read (
        .clk_i            (clk_i),
        .rst_ni           (rst_ni),
        .fifo_data_i      (fifo_data_i),
        .fifo_be_i        (fifo_be_i),
        .fifo_rxf_ni      (fifo_rxf_ni),
        .fifo_rd_no       (fifo_rd_no),
        .fifo_oe_no       (fifo_oe_no),
        .ready_i          (read_ready),
        .word_o           (word_o),
        .word_valid_o     (word_valid_o),
        .word_count_o     (word_count_o),
        .be_error_count_o (be_error_count_o)
    );

    logic        sample_valid, sample_right;
    logic [23:0] sample;

    lyrebird_unpack u_unpack (
        .clk_i           (clk_i),
        .rst_ni          (rst_ni),
        .word_i          (word_o),
        .valid_i         (word_valid_o),
        .sample_valid_o  (sample_valid),
        .sample_right_o  (sample_right),
        .sample_o        (sample),
        .ctrl_valid_o    (ctrl_valid_o),
        .ctrl_opcode_o   (ctrl_opcode_o),
        .ctrl_payload_o  (ctrl_payload_o),
        .locked_o        (locked_o),
        .bad_tag_count_o (bad_tag_count_o),
        .resync_count_o  (resync_count_o)
    );

    assign flush = ctrl_valid_o
                   && ((ctrl_opcode_o == OpSetRate) || (ctrl_opcode_o == OpReset));

    lyrebird_elastic #(
        .Blocks       (3),
        .PrefillWords (9),    // three words per block, so prefill is 12 words
        .ResetHold    (16)
    ) u_elastic (
        .wr_clk_i             (clk_i),
        .wr_rst_ni            (rst_ni),
        .wr_valid_i           (sample_valid),
        .wr_right_i           (sample_right),
        .wr_sample_i          (sample),
        .wr_flush_i           (flush),
        .wr_ready_o           (buf_ready),
        .wr_overrun_count_o   (overrun_count_o),
        .rd_clk_i             (mclk_i),
        .rd_rst_ni            (mrst_ni),
        .rd_tick_i            (tick_i),
        .rd_valid_o           (sample_valid_o),
        .rd_right_o           (sample_right_o),
        .rd_sample_o          (sample_o),
        .rd_mute_o            (mute_o),
        .rd_locked_o          (buf_locked_o),
        .rd_underrun_count_o  (underrun_count_o),
        .rd_seq_error_count_o (seq_error_count_o)
    );

endmodule
