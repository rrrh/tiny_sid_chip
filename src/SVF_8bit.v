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
//   alpha1 [6:0] — frequency (7-bit, shift-add /128)
//   alpha2 [3:0] — damping   (4-bit, shift-add /8, exact for SID q_damp)
//
// Internal: 12-bit signed Q8.4.  Outputs: 8-bit signed (combinational).
//
//==============================================================================

module SVF_8bit (
    input  wire        clk,
    input  wire        rst,
    input  wire signed [7:0] audio_in,
    input  wire        sample_valid,
    input  wire [6:0]  alpha1,
    input  wire [3:0]  alpha2,
    output wire signed [7:0] audio_out_hp,
    output wire signed [7:0] audio_out_lp,
    output wire signed [7:0] audio_out_bp
);

    //==========================================================================
    // State — Q8.4 (8 integer, 4 fractional)
    //==========================================================================
    reg signed [11:0] bp_state, lp_state;

    // --- Frequency shift-add: val * alpha1 / 128 (7 terms) ---
    function signed [11:0] f_mul;
        input signed [11:0] val;
        input        [6:0]  c;
        begin
            f_mul = (c[6] ? (val >>> 1) : 12'sd0) +
                    (c[5] ? (val >>> 2) : 12'sd0) +
                    (c[4] ? (val >>> 3) : 12'sd0) +
                    (c[3] ? (val >>> 4) : 12'sd0) +
                    (c[2] ? (val >>> 5) : 12'sd0) +
                    (c[1] ? (val >>> 6) : 12'sd0) +
                    (c[0] ? (val >>> 7) : 12'sd0);
        end
    endfunction

    // --- Damping shift-add: val * alpha2 / 8 (4 terms, exact) ---
    function signed [11:0] q_mul;
        input signed [11:0] val;
        input        [3:0]  c;
        begin
            q_mul = (c[3] ? val          : 12'sd0) +
                    (c[2] ? (val >>> 1)  : 12'sd0) +
                    (c[1] ? (val >>> 2)  : 12'sd0) +
                    (c[0] ? (val >>> 3)  : 12'sd0);
        end
    endfunction

    // --- Saturation: 13-bit signed → 12-bit signed ---
    function signed [11:0] sat12;
        input signed [12:0] v;
        begin
            sat12 = (v[12] != v[11]) ?
                    (v[12] ? 12'sh800 : 12'sh7FF) : v[11:0];
        end
    endfunction

    //==========================================================================
    // Filter Datapath (combinational)
    //==========================================================================

    // Scale input to Q8.4
    wire signed [11:0] in_scaled = {audio_in, 4'b0};

    // HP = in - lp - q*bp
    wire signed [11:0] q_bp = q_mul(bp_state, alpha2);
    wire signed [11:0] hp   = sat12({in_scaled[11], in_scaled} -
                                     {lp_state[11], lp_state} -
                                     {q_bp[11], q_bp});

    // BP_new = bp + f*hp
    wire signed [11:0] f_hp   = f_mul(hp, alpha1);
    wire signed [11:0] bp_new = sat12({bp_state[11], bp_state} +
                                       {f_hp[11], f_hp});

    // LP_new = lp + f*bp_new
    wire signed [11:0] f_bp   = f_mul(bp_new, alpha1);
    wire signed [11:0] lp_new = sat12({lp_state[11], lp_state} +
                                       {f_bp[11], f_bp});

    // 8-bit outputs (integer part of Q8.4)
    assign audio_out_hp = hp[11:4];
    assign audio_out_bp = bp_new[11:4];
    assign audio_out_lp = lp_new[11:4];

    //==========================================================================
    // State Update
    //==========================================================================
    always @(posedge clk) begin
        if (rst) begin
            bp_state <= 12'd0;
            lp_state <= 12'd0;
        end else if (sample_valid) begin
            bp_state <= bp_new;
            lp_state <= lp_new;
        end
    end

endmodule
