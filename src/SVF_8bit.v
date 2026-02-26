/* verilator lint_off WIDTHTRUNC */
`timescale 1ns / 1ps
//==============================================================================
// State Variable Filter (SVF) - 8-bit Audio
//==============================================================================
//
// Chamberlin SVF:  hp = in - lp - q*bp
//                  bp = bp + f*hp
//                  lp = lp + f*bp_new
//
// Coefficients:
//   alpha1 [10:0] — frequency: alpha = fc[10:3] / 2048 (8-term shift-add)
//                   fc ≈ fc[10:3] × fs / (2π × 2048) ≈ fc[10:3] × 124.4 Hz
//                   Range: ~124 Hz (fc[10:3]=1) to ~31.7 kHz (fc[10:3]=255)
//   alpha2 [1:0]  — damping (2-bit, shift-add /4)
//
// Internal: 13-bit signed Q8.5.  Outputs: 8-bit signed (combinational).
//
//==============================================================================

module SVF_8bit #(
    parameter ENABLE_HP = 1,
    parameter ENABLE_BP = 1,
    parameter ENABLE_LP = 1
) (
    input  wire        clk,
    input  wire        rst,
    input  wire signed [7:0] audio_in,
    input  wire        sample_valid,
    input  wire [10:0] alpha1,
    input  wire [1:0]  alpha2,
    output wire signed [7:0] audio_out_hp,
    output wire signed [7:0] audio_out_lp,
    output wire signed [7:0] audio_out_bp
);

    //==========================================================================
    // State — Q8.5 (8 integer bits incl. sign, 5 fractional bits, 13-bit signed)
    //==========================================================================
    reg signed [12:0] bp_state, lp_state;

    // --- Frequency shift-add: val * fc[10:3] / 2048 (8 terms, >>>4..>>>11) ---
    function signed [12:0] f_mul;
        input signed [12:0] val;
        input        [10:0] c;
        begin
            f_mul = (c[10] ? (val >>> 4)  : 13'sd0) +
                    (c[9]  ? (val >>> 5)  : 13'sd0) +
                    (c[8]  ? (val >>> 6)  : 13'sd0) +
                    (c[7]  ? (val >>> 7)  : 13'sd0) +
                    (c[6]  ? (val >>> 8)  : 13'sd0) +
                    (c[5]  ? (val >>> 9)  : 13'sd0) +
                    (c[4]  ? (val >>> 10) : 13'sd0) +
                    (c[3]  ? (val >>> 11) : 13'sd0);
        end
    endfunction

    // --- Damping shift-add: val * alpha2 / 4 (2 terms) ---
    function signed [12:0] q_mul;
        input signed [12:0] val;
        input        [1:0]  c;
        begin
            q_mul = (c[1] ? (val >>> 1) : 13'sd0) +
                    (c[0] ? (val >>> 2) : 13'sd0);
        end
    endfunction

    // --- Saturation: 14-bit signed → 13-bit signed ---
    function signed [12:0] sat13;
        input signed [13:0] v;
        begin
            sat13 = (v[13] != v[12]) ?
                    (v[13] ? 13'sh1000 : 13'sh0FFF) : v[12:0];
        end
    endfunction

    //==========================================================================
    // Filter Datapath (combinational)
    //==========================================================================

generate if (ENABLE_HP || ENABLE_BP || ENABLE_LP) begin : gen_filter

    // Scale input to Q8.5
    wire signed [12:0] in_scaled = {audio_in, 5'b0};

    // HP = in - lp - q*bp
    wire signed [12:0] q_bp = q_mul(bp_state, alpha2);
    wire signed [12:0] hp   = sat13({in_scaled[12], in_scaled} -
                                     {lp_state[12], lp_state} -
                                     {q_bp[12], q_bp});

    // BP_new = bp + f*hp
    wire signed [12:0] f_hp   = f_mul(hp, alpha1);
    wire signed [12:0] bp_new = sat13({bp_state[12], bp_state} +
                                       {f_hp[12], f_hp});

    // LP_new = lp + f*bp_new
    wire signed [12:0] f_bp   = f_mul(bp_new, alpha1);
    wire signed [12:0] lp_new = sat13({lp_state[12], lp_state} +
                                       {f_bp[12], f_bp});

    // 8-bit outputs (integer part of Q8.5)
    if (ENABLE_HP) begin : gen_hp_out assign audio_out_hp = hp[12:5]; end
    if (ENABLE_BP) begin : gen_bp_out assign audio_out_bp = bp_new[12:5]; end
    if (ENABLE_LP) begin : gen_lp_out assign audio_out_lp = lp_new[12:5]; end

    //==========================================================================
    // State Update
    //==========================================================================
    always @(posedge clk) begin
        if (rst) begin
            bp_state <= 13'd0;
            lp_state <= 13'd0;
        end else if (sample_valid) begin
            bp_state <= bp_new;
            lp_state <= lp_new;
        end
    end

end endgenerate

    // Tie off disabled outputs
    generate
        if (!ENABLE_HP) begin : gen_hp_tie assign audio_out_hp = 8'sd0; end
        if (!ENABLE_BP) begin : gen_bp_tie assign audio_out_bp = 8'sd0; end
        if (!ENABLE_LP) begin : gen_lp_tie assign audio_out_lp = 8'sd0; end
        if (!(ENABLE_HP || ENABLE_BP || ENABLE_LP)) begin : gen_no_filter
            always @(posedge clk) begin
                if (rst) begin
                    bp_state <= 13'd0;
                    lp_state <= 13'd0;
                end
            end
        end
    endgenerate

endmodule
