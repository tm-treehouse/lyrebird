// Decodes one bus word from the FT601Q into a sample or a control word.
//
// Wire format is defined in docs/decisions/0010-192khz-and-control-word.md.
// The tag byte occupies DATA[31:24]. An unrecognised tag raises bad_tag_o,
// which the resync logic upstream uses to hunt for alignment; it must see
// several consecutive well-formed words before declaring lock, because real
// audio can contain the tag values in the sample bits.
//
// SystemVerilog restricted to the subset Yosys accepts: logic, always_ff,
// localparam. No interfaces, no packed structs.

module lyrebird_tag_decode (
    input  logic        clk_i,
    input  logic        rst_ni,

    input  logic [31:0] word_i,
    input  logic        valid_i,

    // Audio path
    output logic        sample_valid_o,
    output logic        sample_right_o,   // 0 = left, 1 = right
    output logic [23:0] sample_o,

    // Control path
    output logic        ctrl_valid_o,
    output logic [7:0]  ctrl_opcode_o,
    output logic [15:0] ctrl_payload_o,

    // Framing
    output logic        bad_tag_o
);

    localparam logic [7:0] TagLeft  = 8'hA5;
    localparam logic [7:0] TagRight = 8'h5A;
    localparam logic [7:0] TagCtrl  = 8'hC3;

    logic [7:0] tag;
    logic       is_left, is_right, is_ctrl, is_known;

    assign tag      = word_i[31:24];
    assign is_left  = (tag == TagLeft);
    assign is_right = (tag == TagRight);
    assign is_ctrl  = (tag == TagCtrl);
    assign is_known = is_left | is_right | is_ctrl;

    always_ff @(posedge clk_i) begin
        if (!rst_ni) begin
            sample_valid_o <= 1'b0;
            sample_right_o <= 1'b0;
            sample_o       <= 24'd0;
            ctrl_valid_o   <= 1'b0;
            ctrl_opcode_o  <= 8'd0;
            ctrl_payload_o <= 16'd0;
            bad_tag_o      <= 1'b0;
        end else begin
            sample_valid_o <= valid_i & (is_left | is_right);
            sample_right_o <= is_right;
            sample_o       <= word_i[23:0];
            ctrl_valid_o   <= valid_i & is_ctrl;
            ctrl_opcode_o  <= word_i[23:16];
            ctrl_payload_o <= word_i[15:0];
            bad_tag_o      <= valid_i & ~is_known;
        end
    end

endmodule
