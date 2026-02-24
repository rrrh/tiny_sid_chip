`timescale 1ns / 1ps
//==============================================================================
// State Variable Filter (SVF) - 8-bit Audio, Area-Optimized
//==============================================================================
//
// Chamberlin SVF:  hp = in - lp - q*bp
//                  bp = bp + f*hp
//                  lp = lp + f*bp_new
//
// Coefficients:
//   alpha1 [4:0] — frequency (5-bit, shift-add /32)
//   alpha2 [3:0] — damping   (4-bit, shift-add /8, exact for SID q_damp)
//
// Internal: 10-bit signed Q8.2.  Outputs: 8-bit signed (combinational).
//
//==============================================================================

module SVF_8bit (
    input  wire        clk,
    input  wire        rst,
    input  wire signed [7:0] audio_in,
    input  wire        sample_valid,
    input  wire [4:0]  alpha1,
    input  wire [3:0]  alpha2,
    output wire signed [7:0] audio_out_hp,
    output wire signed [7:0] audio_out_lp,
    output wire signed [7:0] audio_out_bp
);

    //==========================================================================
    // State — Q8.2 (8 integer, 2 fractional)
    //==========================================================================
    reg signed [9:0] bp_state, lp_state;

    // --- Frequency shift-add: val * alpha1 / 32 (5 terms) ---
    function signed [9:0] f_mul;
        input signed [9:0] val;
        input        [4:0]  c;
        begin
            f_mul = (c[4] ? (val >>> 1) : 10'sd0) +
                    (c[3] ? (val >>> 2) : 10'sd0) +
                    (c[2] ? (val >>> 3) : 10'sd0) +
                    (c[1] ? (val >>> 4) : 10'sd0) +
                    (c[0] ? (val >>> 5) : 10'sd0);
        end
    endfunction

    // --- Damping shift-add: val * alpha2 / 8 (4 terms, exact) ---
    function signed [9:0] q_mul;
        input signed [9:0] val;
        input        [3:0]  c;
        begin
            q_mul = (c[3] ? val          : 10'sd0) +
                    (c[2] ? (val >>> 1)  : 10'sd0) +
                    (c[1] ? (val >>> 2)  : 10'sd0) +
                    (c[0] ? (val >>> 3)  : 10'sd0);
        end
    endfunction

    // --- Saturation: 11-bit signed → 10-bit signed ---
    function signed [9:0] sat10;
        input signed [10:0] v;
        begin
            sat10 = (v[10] != v[9]) ?
                    (v[10] ? 10'sh200 : 10'sh1FF) : v[9:0];
        end
    endfunction

    //==========================================================================
    // Filter Datapath (combinational)
    //==========================================================================

    // Scale input to Q8.2
    wire signed [9:0] in_scaled = {audio_in, 2'b0};

    // HP = in - lp - q*bp
    wire signed [9:0] q_bp = q_mul(bp_state, alpha2);
    wire signed [9:0] hp   = sat10({in_scaled[9], in_scaled} -
                                     {lp_state[9], lp_state} -
                                     {q_bp[9], q_bp});

    // BP_new = bp + f*hp
    wire signed [9:0] f_hp   = f_mul(hp, alpha1);
    wire signed [9:0] bp_new = sat10({bp_state[9], bp_state} +
                                       {f_hp[9], f_hp});

    // LP_new = lp + f*bp_new
    wire signed [9:0] f_bp   = f_mul(bp_new, alpha1);
    wire signed [9:0] lp_new = sat10({lp_state[9], lp_state} +
                                       {f_bp[9], f_bp});

    // 8-bit outputs (integer part of Q8.2)
    assign audio_out_hp = hp[9:2];
    assign audio_out_bp = bp_new[9:2];
    assign audio_out_lp = lp_new[9:2];

    //==========================================================================
    // State Update
    //==========================================================================
    always @(posedge clk) begin
        if (rst) begin
            bp_state <= 10'd0;
            lp_state <= 10'd0;
        end else if (sample_valid) begin
            bp_state <= bp_new;
            lp_state <= lp_new;
        end
    end

endmodule
