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
//   alpha1 [10:0] — frequency: alpha = alpha1 / 16384
//                   fc ≈ alpha1 × fs / (2π × 16384) ≈ alpha1 × 15.5 Hz
//                   Range: ~15.5 Hz (alpha1=1) to ~31.7 kHz (alpha1=2047)
//   alpha2 [1:0]  — damping (2-bit, shift-add /4)
//
// Internal: 16-bit signed Q8.8.  Outputs: 8-bit signed (combinational).
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
    // State — Q8.8 (8 integer bits, 8 fractional bits, signed)
    //==========================================================================
    reg signed [15:0] bp_state, lp_state;

    // --- Frequency multiply: val * alpha1 / 16384 ---
    function signed [15:0] f_mul;
        input signed [15:0] val;
        input        [10:0] c;
        reg signed [27:0] prod;
        begin
            prod  = val * $signed({1'b0, c});
            f_mul = prod >>> 14;
        end
    endfunction

    // --- Damping shift-add: val * alpha2 / 4 (2 terms) ---
    function signed [15:0] q_mul;
        input signed [15:0] val;
        input        [1:0]  c;
        begin
            q_mul = (c[1] ? (val >>> 1) : 16'sd0) +
                    (c[0] ? (val >>> 2) : 16'sd0);
        end
    endfunction

    // --- Saturation: 17-bit signed → 16-bit signed ---
    function signed [15:0] sat16;
        input signed [16:0] v;
        begin
            sat16 = (v[16] != v[15]) ?
                    (v[16] ? 16'sh8000 : 16'sh7FFF) : v[15:0];
        end
    endfunction

    //==========================================================================
    // Filter Datapath (combinational)
    //==========================================================================

generate if (ENABLE_HP || ENABLE_BP || ENABLE_LP) begin : gen_filter

    // Scale input to Q8.8
    wire signed [15:0] in_scaled = {audio_in, 8'b0};

    // HP = in - lp - q*bp
    wire signed [15:0] q_bp = q_mul(bp_state, alpha2);
    wire signed [15:0] hp   = sat16({in_scaled[15], in_scaled} -
                                     {lp_state[15], lp_state} -
                                     {q_bp[15], q_bp});

    // BP_new = bp + f*hp
    wire signed [15:0] f_hp   = f_mul(hp, alpha1);
    wire signed [15:0] bp_new = sat16({bp_state[15], bp_state} +
                                       {f_hp[15], f_hp});

    // LP_new = lp + f*bp_new
    wire signed [15:0] f_bp   = f_mul(bp_new, alpha1);
    wire signed [15:0] lp_new = sat16({lp_state[15], lp_state} +
                                       {f_bp[15], f_bp});

    // 8-bit outputs (integer part of Q8.8)
    if (ENABLE_HP) assign audio_out_hp = hp[15:8];
    if (ENABLE_BP) assign audio_out_bp = bp_new[15:8];
    if (ENABLE_LP) assign audio_out_lp = lp_new[15:8];

    //==========================================================================
    // State Update
    //==========================================================================
    always @(posedge clk) begin
        if (rst) begin
            bp_state <= 16'd0;
            lp_state <= 16'd0;
        end else if (sample_valid) begin
            bp_state <= bp_new;
            lp_state <= lp_new;
        end
    end

end endgenerate

    // Tie off disabled outputs
    generate
        if (!ENABLE_HP) assign audio_out_hp = 8'sd0;
        if (!ENABLE_BP) assign audio_out_bp = 8'sd0;
        if (!ENABLE_LP) assign audio_out_lp = 8'sd0;
        if (!(ENABLE_HP || ENABLE_BP || ENABLE_LP)) begin : gen_no_filter
            always @(posedge clk) begin
                if (rst) begin
                    bp_state <= 16'd0;
                    lp_state <= 16'd0;
                end
            end
        end
    endgenerate

endmodule
