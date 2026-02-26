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
//   alpha1 [10:0] — frequency: alpha = fc[10:5] / 1024 (6-term shift-add)
//                   fc ≈ fc[10:5] × fs / (2π × 1024) ≈ fc[10:5] × 249 Hz
//                   Range: ~249 Hz (fc[10:5]=1) to ~15.7 kHz (fc[10:5]=63)
//   alpha2 [1:0]  — damping (2-bit, shift-add /4)
//
// Internal: 9-bit signed Q8.1.  Outputs: 8-bit signed (combinational).
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
    // State — Q8.1 (8 integer bits incl. sign, 1 fractional bit, 9-bit signed)
    //==========================================================================
    reg signed [8:0] bp_state, lp_state;

    // --- Frequency shift-add: val * fc[10:5] / 1024 (6 terms, >>>5..>>>10) ---
    function signed [8:0] f_mul;
        input signed [8:0] val;
        input        [10:0] c;
        begin
            f_mul = (c[10] ? (val >>> 5)  : 9'sd0) +
                    (c[9]  ? (val >>> 6)  : 9'sd0) +
                    (c[8]  ? (val >>> 7)  : 9'sd0) +
                    (c[7]  ? (val >>> 8)  : 9'sd0) +
                    (c[6]  ? (val >>> 9)  : 9'sd0) +
                    (c[5]  ? (val >>> 10) : 9'sd0);
        end
    endfunction

    // --- Damping shift-add: val * alpha2 / 4 (2 terms) ---
    function signed [8:0] q_mul;
        input signed [8:0] val;
        input        [1:0]  c;
        begin
            q_mul = (c[1] ? (val >>> 1) : 9'sd0) +
                    (c[0] ? (val >>> 2) : 9'sd0);
        end
    endfunction

    // --- Saturation: 10-bit signed → 9-bit signed ---
    function signed [8:0] sat9;
        input signed [9:0] v;
        begin
            sat9 = (v[9] != v[8]) ?
                   (v[9] ? 9'sh100 : 9'sh0FF) : v[8:0];
        end
    endfunction

    //==========================================================================
    // Filter Datapath (combinational)
    //==========================================================================

generate if (ENABLE_HP || ENABLE_BP || ENABLE_LP) begin : gen_filter

    // Scale input to Q8.1
    wire signed [8:0] in_scaled = {audio_in, 1'b0};

    // HP = in - lp - q*bp
    wire signed [8:0] q_bp = q_mul(bp_state, alpha2);
    wire signed [8:0] hp   = sat9({in_scaled[8], in_scaled} -
                                    {lp_state[8], lp_state} -
                                    {q_bp[8], q_bp});

    // BP_new = bp + f*hp
    wire signed [8:0] f_hp   = f_mul(hp, alpha1);
    wire signed [8:0] bp_new = sat9({bp_state[8], bp_state} +
                                      {f_hp[8], f_hp});

    // LP_new = lp + f*bp_new
    wire signed [8:0] f_bp   = f_mul(bp_new, alpha1);
    wire signed [8:0] lp_new = sat9({lp_state[8], lp_state} +
                                      {f_bp[8], f_bp});

    // 8-bit outputs (integer part of Q8.1)
    if (ENABLE_HP) begin : gen_hp_out assign audio_out_hp = hp[8:1]; end
    if (ENABLE_BP) begin : gen_bp_out assign audio_out_bp = bp_new[8:1]; end
    if (ENABLE_LP) begin : gen_lp_out assign audio_out_lp = lp_new[8:1]; end

    //==========================================================================
    // State Update
    //==========================================================================
    always @(posedge clk) begin
        if (rst) begin
            bp_state <= 9'd0;
            lp_state <= 9'd0;
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
                    bp_state <= 9'd0;
                    lp_state <= 9'd0;
                end
            end
        end
    endgenerate

endmodule
