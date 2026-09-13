// Elastic buffer: the clock-domain crossing between the FT601Q bus and the
// audio clock, and the prefill that absorbs host scheduling jitter.
//
// Storage is the GateMate block RAM hard FIFO, CC_FIFO_40K, in the geometry
// docs/decisions/0011-pack-three-samples-per-fifo-word.md settles: SDP 40K
// mode, 80 bits wide, 512 deep, three 24-bit samples per word. Seventy-two of
// the 80 bits carry audio, so the packing is 90 percent efficient, where one
// sample per 40-bit word would waste 40 percent and would not fit the
// requirement.
//
// The hard FIFO is the whole point. It runs its two ports on separate clocks
// with its own pointer synchronisers and fill flags, so the crossing is a hard
// block rather than fabric to write and verify -- which 0011 calls the part of
// this design most likely to hide a subtle bug.
//
// Packing costs a packer on the write side and an unpacker on the read side,
// and makes the read granularity three samples: the Fs side reads a word every
// third sample tick. A word is one and a half stereo frames, so left versus
// right is tracked by a counter rather than by word boundaries.
//
// **Depth needs more than one block, and the blocks go in parallel rather than
// in series.** One block holds 512 words, 1,536 samples, 4 ms at 192 kHz. The
// requirement is 100 ms, so 25 blocks (hdl/README.md). They are written and
// read round-robin, one word each, in the same order on both sides: order is
// preserved exactly and every block's fill stays within one word of every
// other's. That is what makes the prefill threshold expressible. 0011 notes
// that SDP mode offers only *static* almost-full and almost-empty offsets,
// which is what a fixed threshold wants, and with balanced blocks a static
// per-block almost-empty offset of PrefillWords/Blocks makes "no block is
// almost empty" mean "the buffer holds the prefill". No fill counter has to
// cross the clock domains.
//
// Cascading the blocks instead would save the read multiplexer, which is the
// larger half of this module's logic, but it would put the total fill out of
// reach of the hard flags entirely, since no single block's flag can express a
// threshold larger than its own 512 words. It would take a fill counter in the
// read domain in its place, and that is only exact because both of its events
// would be in that domain -- an accident of the topology rather than something
// the hard block gives you.
//
// **Prefill is half the buffer, not all of it.** 25 blocks hold 100 ms at
// 192 kHz; the threshold defaults to 50 ms of that. Prefill is latency, and
// the buffer has to absorb jitter in both directions: a host late by more than
// the prefill underruns, and a host early by more than the remaining headroom
// overruns. Splitting the buffer in half makes those two tolerances equal,
// which is the right answer when nothing says the jitter is skewed.
// docs/open-items.md lists the threshold as open and 50 to 100 ms as a range;
// this is the low end of that range, chosen because prefill is pure latency.
//
// The state machine is the mute, drain, prefill, resume sequence that
// docs/decisions/0010-192khz-and-control-word.md gives only in prose:
//
//   StDrain  hard FIFOs held in reset, incoming audio discarded, muted
//   StFill   writes accepted, reads held off, muted
//   StRun    one buffered sample per tick, unmuted
//
// A SET_RATE or RESET control word drives wr_flush_i and returns the buffer to
// StDrain, because samples already buffered belong to the old rate. An
// underrun returns to StFill without discarding: that data is still good,
// there is just not enough of it.
//
// SystemVerilog restricted to the subset Yosys accepts: logic, always_ff,
// always_comb, localparam. No interfaces, no packed structs.

module lyrebird_elastic #(
    // Hard FIFO blocks. 25 of the part's 32 is 100 ms at 192 kHz; see
    // hdl/README.md. Must be at least two.
    parameter int unsigned Blocks = 25,

    // Prefill threshold in 80-bit words, three samples each. 6,400 words is
    // 19,200 samples: 50 ms at 192 kHz, 100 ms at 96 kHz. Rounded down to a
    // whole number of words per block by the static almost-empty offset.
    parameter int unsigned PrefillWords = 6400,

    // Write clocks the hard FIFO reset is held for on a flush. It has to span
    // at least three read clocks so the read side sees it through a two-flop
    // synchroniser; 32 bus clocks is 480 ns against a 41 ns MCLK.
    parameter int unsigned ResetHold = 32
) (
    // ---- write side: the FT601Q bus clock domain --------------------------
    input  logic        wr_clk_i,
    input  logic        wr_rst_ni,

    input  logic        wr_valid_i,
    input  logic        wr_right_i,     // 0 = left, 1 = right
    input  logic [23:0] wr_sample_i,
    input  logic        wr_flush_i,     // SET_RATE / RESET: discard the buffer

    output logic        wr_ready_o,
    output logic [15:0] wr_overrun_count_o,

    // ---- read side: the MCLK domain ---------------------------------------
    input  logic        rd_clk_i,
    input  logic        rd_rst_ni,
    input  logic        rd_tick_i,      // one-clock sample-rate enable

    output logic        rd_valid_o,     // registered: the clock after the tick
    output logic        rd_right_o,
    output logic [23:0] rd_sample_o,
    output logic        rd_mute_o,
    output logic        rd_locked_o,
    output logic [15:0] rd_underrun_count_o,
    output logic [15:0] rd_seq_error_count_o
);

    // Almost-empty offset per block. "No block is almost empty" then means
    // every block holds more than this, so the buffer holds more than
    // Blocks * AlmostEmptyOffset words.
    localparam int unsigned AlmostEmptyOffset = PrefillWords / Blocks;

    // Almost-full offset per block, in words. The write side stops on this
    // flag, so it is the slack covering words already committed: one in the
    // bus reader's registered RD_N and one in its registered valid, which
    // together are well under a single three-sample word. Four words is
    // comfortable and costs 4 of 512 per block.
    localparam int unsigned AlmostFullOffset = 4;

    localparam int unsigned RstWidth = $clog2(ResetHold + 1);

    localparam logic [1:0] StDrain = 2'd0;
    localparam logic [1:0] StFill  = 2'd1;
    localparam logic [1:0] StRun   = 2'd2;

    // ----------------------------------------------------------------------
    // Write domain: flush sequencing
    //
    // One registered reset line drives every block's F_RST_N, which is
    // asynchronous to both ports. Registering it keeps a comparator glitch off
    // a reset input, and holding it for ResetHold clocks makes the pulse wide
    // enough for the read domain to catch through its synchroniser.
    // ----------------------------------------------------------------------
    logic [RstWidth-1:0] rst_cnt_q;
    logic                fifo_rst_nq;
    logic                discard;       // draining: throw incoming audio away
    logic                overrun;
    logic                flush;

    assign discard = ~fifo_rst_nq;
    assign flush   = wr_flush_i | overrun;

    always_ff @(posedge wr_clk_i) begin
        if (!wr_rst_ni) begin
            rst_cnt_q   <= RstWidth'(ResetHold);
            fifo_rst_nq <= 1'b0;
        end else if (flush) begin
            rst_cnt_q   <= RstWidth'(ResetHold);
            fifo_rst_nq <= 1'b0;
        end else if (rst_cnt_q != '0) begin
            rst_cnt_q   <= rst_cnt_q - RstWidth'(1);
            fifo_rst_nq <= 1'b0;
        end else begin
            fifo_rst_nq <= 1'b1;
        end
    end

    // ----------------------------------------------------------------------
    // Write domain: the packer
    //
    // Three samples shift in, then one 80-bit word goes to the block the
    // round-robin selector points at. A partial word is never written: it
    // would break the three-sample alignment the read side counts on, so up to
    // two samples wait in the shift register for the stream to continue.
    //
    // The first sample after a flush has to be a left one. That anchors the
    // whole buffer, because from there the read side derives left versus right
    // by counting rather than from anything in the data. lyrebird_unpack only
    // emits once it has locked on a left sample, so the anchor normally costs
    // nothing; it is here so a mid-frame start cannot swap the channels.
    //
    // The eight bits the packing leaves over carry a word sequence number. It
    // costs nothing, and the read side checking it is the only direct evidence
    // that 25 independently clocked blocks stayed in step.
    // ----------------------------------------------------------------------
    logic [47:0]        pack_sr_q;
    logic [1:0]         pack_idx_q;
    logic               anchored_q;
    logic [7:0]         wr_seq_q;
    logic [79:0]        push_word_q;
    logic               push_q;
    logic [Blocks-1:0]  wr_sel_q;

    logic [Blocks-1:0]  almost_full_v, empty_v, almost_empty_v;

    assign wr_ready_o = ~(|almost_full_v);

    // A sample offered with no room is a fault rather than a rate error: the
    // bus reader stops on wr_ready_o, so reaching here means the host is
    // running ahead of the sample clock. Flush and re-lock, which also
    // re-anchors the left/right phase that dropping samples would corrupt.
    assign overrun = wr_valid_i & ~discard & ~wr_ready_o;

    always_ff @(posedge wr_clk_i) begin
        if (!wr_rst_ni) begin
            pack_sr_q          <= 48'd0;
            pack_idx_q         <= 2'd0;
            anchored_q         <= 1'b0;
            wr_seq_q           <= 8'd0;
            push_word_q        <= 80'd0;
            push_q             <= 1'b0;
            wr_sel_q           <= {{(Blocks-1){1'b0}}, 1'b1};
            wr_overrun_count_o <= 16'd0;
        end else begin
            push_q <= 1'b0;

            // The selector advances with the write it belongs to: push_q is
            // high exactly for the cycle the block takes the word.
            if (push_q) begin
                wr_sel_q <= {wr_sel_q[Blocks-2:0], wr_sel_q[Blocks-1]};
            end

            if (discard) begin
                pack_idx_q <= 2'd0;
                anchored_q <= 1'b0;
                wr_seq_q   <= 8'd0;
                wr_sel_q   <= {{(Blocks-1){1'b0}}, 1'b1};
            end else if (wr_valid_i) begin
                if (overrun) begin
                    wr_overrun_count_o <= wr_overrun_count_o + 16'd1;
                end else if (anchored_q || !wr_right_i) begin
                    anchored_q <= 1'b1;
                    pack_sr_q  <= {wr_sample_i, pack_sr_q[47:24]};
                    pack_idx_q <= (pack_idx_q == 2'd2) ? 2'd0
                                                       : pack_idx_q + 2'd1;
                    if (pack_idx_q == 2'd2) begin
                        // Oldest sample in the low bits, so the read side
                        // unpacks 0, 1, 2 in arrival order.
                        push_word_q <= {wr_seq_q, wr_sample_i, pack_sr_q[47:0]};
                        push_q      <= 1'b1;
                        wr_seq_q    <= wr_seq_q + 8'd1;
                    end
                end
            end
        end
    end

    // ----------------------------------------------------------------------
    // Read domain: the flush as seen from here
    // ----------------------------------------------------------------------
    logic [1:0]        rd_rst_sync_q;
    logic              rd_fifo_ready;
    logic [Blocks-1:0] rd_sel_q, rd_sel_dq;

    assign rd_fifo_ready = rd_rst_sync_q[1];

    // fifo_rst_nq is an asynchronous reset to the hard blocks and, here, data
    // to be synchronised. That is a reset-domain crossing, and exactly what
    // the SYNCASYNCNET lint check exists to find. It is safe for the one
    // reason that makes any such crossing safe: the level is held for
    // ResetHold write clocks, far longer than the two read clocks this
    // synchroniser needs, so the read side cannot miss the flush. Seeing it a
    // clock late is harmless, because the blocks it resets are already empty.
    /* verilator lint_off SYNCASYNCNET */
    always_ff @(posedge rd_clk_i) begin
        if (!rd_rst_ni) rd_rst_sync_q <= 2'b00;
        else            rd_rst_sync_q <= {rd_rst_sync_q[0], fifo_rst_nq};
    end
    /* verilator lint_on SYNCASYNCNET */

    // ----------------------------------------------------------------------
    // The blocks
    // ----------------------------------------------------------------------
    logic [Blocks*80-1:0] dout_v;
    logic [79:0]          rd_dout;
    logic                 rd_fetch;

    // The selector is one-hot and registered, so this reduces to a
    // multiplexer: the block popped last cycle drives the word. It is what
    // parallel blocks cost, about 95 CPE_LT per block, and the only part of
    // this module a cascade would save.
    always_comb begin
        rd_dout = 80'd0;
        for (int i = 0; i < int'(Blocks); i = i + 1) begin
            if (rd_sel_dq[i]) rd_dout = dout_v[i*80 +: 80];
        end
    end

    genvar b;
    generate
        for (b = 0; b < int'(Blocks); b = b + 1) begin : gen_block
            CC_FIFO_40K #(
                .RAM_MODE            ("SDP"),    // 80 bits wide, 512 deep
                .FIFO_MODE           ("ASYNC"),  // separate write and read clocks
                .A_WIDTH             (80),
                .B_WIDTH             (80),
                .ALMOST_FULL_OFFSET  (15'(AlmostFullOffset)),
                .ALMOST_EMPTY_OFFSET (15'(AlmostEmptyOffset))
            ) u_fifo (
                // Push port B, on the bus clock.
                .B_CLK   (wr_clk_i),
                .B_EN    (push_q & wr_sel_q[b]),
                .B_WE    (push_q & wr_sel_q[b]),
                .A_DI    (push_word_q[39:0]),
                .B_DI    (push_word_q[79:40]),
                .A_BM    ({40{1'b1}}),
                .B_BM    ({40{1'b1}}),
                // Pop port A, on the audio clock.
                .A_CLK   (rd_clk_i),
                .A_EN    (rd_fetch & rd_sel_q[b]),
                .A_DO    (dout_v[b*80 +: 40]),
                .B_DO    (dout_v[b*80+40 +: 40]),
                // Control and flags. SDP mode allows only the static offsets
                // given above, which is what a fixed prefill threshold wants.
                .F_RST_N        (fifo_rst_nq),
                .F_EMPTY        (empty_v[b]),
                .F_ALMOST_FULL  (almost_full_v[b]),
                .F_ALMOST_EMPTY (almost_empty_v[b])
            );
        end
    endgenerate

    // ----------------------------------------------------------------------
    // Read domain: the unpacker and the prefill state machine
    // ----------------------------------------------------------------------
    logic [1:0]  rd_state_q;
    logic [71:0] hold_q;
    logic        hold_valid_q;
    logic [1:0]  hold_idx_q;
    logic        fetch_q;
    logic [7:0]  rd_seq_q;
    logic        stream_right_q;   // channel of the next buffered sample
    logic        tick_right_q;     // channel of the next emitted slot
    logic        prefill_done_q;
    logic [23:0] hold_sample;
    logic        rd_empty_sel, prefill_met, run_now;

    always_comb begin
        case (hold_idx_q)
            2'd0:    hold_sample = hold_q[23:0];
            2'd1:    hold_sample = hold_q[47:24];
            default: hold_sample = hold_q[71:48];
        endcase
    end

    assign rd_empty_sel = |(empty_v & rd_sel_q);

    // Every block above its static almost-empty offset, so the buffer holds
    // more than Blocks * AlmostEmptyOffset words. Round-robin keeps the blocks
    // within one word of each other, which is what makes that a threshold.
    //
    // Crossing it is latched, and nothing is fetched until it has been
    // crossed. Both halves matter: a word sitting in the unpacker's holding
    // register is a word the flags cannot see, so a prefetch during prefill
    // would undo the very condition it is waiting for -- with a threshold of
    // twelve words and one word prefetched, the buffer never starts at all.
    // Once running, the level dropping back below the threshold is exactly
    // what the buffer is for, so the latch stands until an underrun.
    assign prefill_met = ~(|almost_empty_v);

    // A pop takes a clock to return its word, so fetch as soon as the holding
    // register empties rather than at the tick. The tick period has to be at
    // least three read clocks; at 192 kHz on a 24.576 MHz MCLK it is 128.
    assign rd_fetch = prefill_done_q && !hold_valid_q && !fetch_q
                      && !rd_empty_sel;

    // Resume only where the emitted channel and the buffered channel agree.
    // They can differ by one after an underrun, because the muted slots keep
    // alternating while the buffered stream stands still.
    assign run_now = (rd_state_q == StFill) && prefill_done_q && hold_valid_q
                     && (tick_right_q == stream_right_q);

    assign rd_locked_o = (rd_state_q == StRun);
    assign rd_mute_o   = (rd_state_q != StRun);

    always_ff @(posedge rd_clk_i) begin
        if (!rd_rst_ni) begin
            rd_state_q           <= StDrain;
            rd_sel_q             <= {{(Blocks-1){1'b0}}, 1'b1};
            rd_sel_dq            <= {{(Blocks-1){1'b0}}, 1'b1};
            hold_q               <= 72'd0;
            hold_valid_q         <= 1'b0;
            hold_idx_q           <= 2'd0;
            fetch_q              <= 1'b0;
            rd_seq_q             <= 8'd0;
            stream_right_q       <= 1'b0;
            tick_right_q         <= 1'b0;
            prefill_done_q       <= 1'b0;
            rd_valid_o           <= 1'b0;
            rd_right_o           <= 1'b0;
            rd_sample_o          <= 24'd0;
            rd_underrun_count_o  <= 16'd0;
            rd_seq_error_count_o <= 16'd0;
        end else begin
            rd_valid_o <= 1'b0;

            // Pop pipeline: enable, then latch the word a clock later.
            if (rd_fetch) begin
                fetch_q   <= 1'b1;
                rd_sel_q  <= {rd_sel_q[Blocks-2:0], rd_sel_q[Blocks-1]};
                rd_sel_dq <= rd_sel_q;
            end else if (fetch_q) begin
                fetch_q      <= 1'b0;
                hold_q       <= rd_dout[71:0];
                hold_valid_q <= 1'b1;
                // Re-anchor on the received number rather than counting on,
                // so one bad word is one error rather than every word after.
                rd_seq_q     <= rd_dout[79:72] + 8'd1;
                if (rd_dout[79:72] != rd_seq_q) begin
                    rd_seq_error_count_o <= rd_seq_error_count_o + 16'd1;
                end
            end

            if ((rd_state_q == StFill) && prefill_met) begin
                prefill_done_q <= 1'b1;
            end

            // One sample per tick, muted or not, so the chain downstream keeps
            // running at a constant rate whatever the buffer is doing.
            if (rd_tick_i) begin
                rd_valid_o   <= 1'b1;
                rd_right_o   <= tick_right_q;
                rd_sample_o  <= 24'd0;
                tick_right_q <= ~tick_right_q;

                if ((rd_state_q == StRun) || run_now) begin
                    if (hold_valid_q) begin
                        rd_sample_o    <= hold_sample;
                        rd_right_o     <= stream_right_q;
                        stream_right_q <= ~stream_right_q;
                        hold_idx_q     <= hold_idx_q + 2'd1;
                        if (hold_idx_q == 2'd2) begin
                            hold_idx_q   <= 2'd0;
                            hold_valid_q <= 1'b0;
                        end
                        if (run_now) rd_state_q <= StRun;
                    end else begin
                        // Underrun. The sample is not late, it is absent, so
                        // emit zero and leave the buffered stream where it is:
                        // the sample that should have played is still the next
                        // one out. Holding the previous sample instead would
                        // put a DC step into the modulator, which clicks;
                        // ramping belongs to the volume stage, which has
                        // rd_mute_o to ramp on.
                        rd_underrun_count_o <= rd_underrun_count_o + 16'd1;
                        rd_state_q          <= StFill;
                        prefill_done_q      <= 1'b0;
                    end
                end
            end

            // A flush outranks everything: the buffer contents are gone.
            // tick_right_q is deliberately left alone, so the emitted stream
            // keeps alternating across the gap.
            if (!rd_fifo_ready) begin
                rd_state_q     <= StDrain;
                rd_sel_q       <= {{(Blocks-1){1'b0}}, 1'b1};
                rd_sel_dq      <= {{(Blocks-1){1'b0}}, 1'b1};
                hold_q         <= 72'd0;
                hold_valid_q   <= 1'b0;
                hold_idx_q     <= 2'd0;
                fetch_q        <= 1'b0;
                rd_seq_q       <= 8'd0;
                stream_right_q <= 1'b0;
                prefill_done_q <= 1'b0;
            end else if (rd_state_q == StDrain) begin
                rd_state_q <= StFill;
            end
        end
    end

endmodule
