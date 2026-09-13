// Framing and resync around the tag decoder.
//
// The stream is alternating left and right samples with control words
// interspersed. Control words are self-identifying and do not disturb the
// left/right alternation. Wire format is in
// docs/decisions/0010-192khz-and-control-word.md.
//
// On a 32-bit bus with word-aligned transfers the interface preserves word
// boundaries, so misalignment can only ever be a whole word, never a byte.
// That means a tag mismatch is the signal to resynchronise, and the tag itself
// says which channel a word belongs to.
//
// Lock still requires several consecutive well-formed words. That guard is not
// against byte misalignment, which cannot happen here, but against a corrupted
// or mid-burst stream where one plausible word is chance. LockWords defaults to
// four, two complete stereo frames, which at 192 kHz costs about 10 us.
//
// Samples are suppressed while hunting, so mis-framed audio never reaches the
// modulator.
//
// SystemVerilog restricted to the subset Yosys accepts.

module lyrebird_unpack #(
    parameter int unsigned LockWords = 4
) (
    input  logic        clk_i,
    input  logic        rst_ni,

    input  logic [31:0] word_i,
    input  logic        valid_i,

    output logic        sample_valid_o,
    output logic        sample_right_o,
    output logic [23:0] sample_o,

    output logic        ctrl_valid_o,
    output logic [7:0]  ctrl_opcode_o,
    output logic [15:0] ctrl_payload_o,

    output logic        locked_o,
    output logic [15:0] bad_tag_count_o,
    output logic [15:0] resync_count_o
);

    localparam int unsigned RunWidth = $clog2(LockWords + 1);

    logic        d_sample_valid, d_sample_right, d_ctrl_valid, d_bad_tag;
    logic [23:0] d_sample;
    logic [7:0]  d_ctrl_opcode;
    logic [15:0] d_ctrl_payload;

    lyrebird_tag_decode u_decode (
        .clk_i          (clk_i),
        .rst_ni         (rst_ni),
        .word_i         (word_i),
        .valid_i        (valid_i),
        .sample_valid_o (d_sample_valid),
        .sample_right_o (d_sample_right),
        .sample_o       (d_sample),
        .ctrl_valid_o   (d_ctrl_valid),
        .ctrl_opcode_o  (d_ctrl_opcode),
        .ctrl_payload_o (d_ctrl_payload),
        .bad_tag_o      (d_bad_tag)
    );

    logic                expect_right;
    logic [RunWidth-1:0] run;
    logic                match;

    // A sample is in sequence when its tag agrees with what we expect next.
    assign match = d_sample_valid && (d_sample_right == expect_right);

    always_ff @(posedge clk_i) begin
        if (!rst_ni) begin
            locked_o        <= 1'b0;
            expect_right    <= 1'b0;
            run             <= '0;
            sample_valid_o  <= 1'b0;
            sample_right_o  <= 1'b0;
            sample_o        <= 24'd0;
            ctrl_valid_o    <= 1'b0;
            ctrl_opcode_o   <= 8'd0;
            ctrl_payload_o  <= 16'd0;
            bad_tag_count_o <= 16'd0;
            resync_count_o  <= 16'd0;
        end else begin
            // Control words are self-identifying, so they pass through in any
            // state and leave the left/right expectation untouched.
            ctrl_valid_o   <= d_ctrl_valid;
            ctrl_opcode_o  <= d_ctrl_opcode;
            ctrl_payload_o <= d_ctrl_payload;

            sample_valid_o <= 1'b0;
            sample_right_o <= d_sample_right;
            sample_o       <= d_sample;

            if (d_bad_tag) begin
                bad_tag_count_o <= bad_tag_count_o + 16'd1;
                if (locked_o) resync_count_o <= resync_count_o + 16'd1;
                locked_o     <= 1'b0;
                run          <= '0;
                expect_right <= 1'b0;
            end else if (d_sample_valid) begin
                if (locked_o) begin
                    if (match) begin
                        sample_valid_o <= 1'b1;
                        expect_right   <= ~expect_right;
                    end else begin
                        // Out of sequence. Trust the tag, re-anchor on it.
                        resync_count_o <= resync_count_o + 16'd1;
                        locked_o       <= 1'b0;
                        run            <= {{(RunWidth-1){1'b0}}, 1'b1};
                        expect_right   <= ~d_sample_right;
                    end
                end else begin
                    // Hunting. Anchor on a left sample, then require a run of
                    // correct alternation before trusting the framing.
                    if (run == '0) begin
                        if (!d_sample_right) begin
                            run          <= {{(RunWidth-1){1'b0}}, 1'b1};
                            expect_right <= 1'b1;
                        end
                    end else if (match) begin
                        expect_right <= ~expect_right;
                        if (run == RunWidth'(LockWords - 1)) begin
                            locked_o <= 1'b1;
                            run      <= RunWidth'(LockWords);
                        end else begin
                            run <= run + {{(RunWidth-1){1'b0}}, 1'b1};
                        end
                    end else begin
                        // Broke the run; re-anchor if this is a left sample.
                        run          <= d_sample_right
                                      ? '0 : {{(RunWidth-1){1'b0}}, 1'b1};
                        expect_right <= ~d_sample_right;
                    end
                end
            end
        end
    end

endmodule
