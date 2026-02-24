`timescale 1ns / 1ps
//==============================================================================
// State-Variable Filter (SVF) — SID 6581 topology
//==============================================================================
// HP = in - lp - bp * (15-res) / 8
// BP = bp + fc * HP / 2048
// LP = lp + fc * BP_new / 2048
//
// Bypass when no voices filtered (filt[2:0]==0) or no mode selected (mode[2:0]==0).
// Mode output: sum of selected {LP, BP, HP} (combinable like real SID).
// Master volume: output * vol / 16, clamped to unsigned 8-bit.
//==============================================================================
module filter (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  sample_in,
    input  wire        sample_valid,
    input  wire [10:0] fc,
    input  wire [3:0]  res,
    input  wire [3:0]  filt,
    input  wire [3:0]  mode,
    input  wire [3:0]  vol,
    output wire [7:0]  sample_out
);

    // --- Saturation helper: clamp 32-bit signed to 16-bit signed ---
    function [15:0] sat16;
        input signed [31:0] v;
        begin
            if (v > 32'sd32767)
                sat16 = 16'sd32767;
            else if (v < -32'sd32768)
                sat16 = -16'sd32768;
            else
                sat16 = v[15:0];
        end
    endfunction

    // --- State registers ---
    reg signed [15:0] bp, lp;

    // --- Bypass condition ---
    wire bypass = (filt[2:0] == 3'd0) || (mode[2:0] == 3'd0);

    // --- Damping coefficient: q_damp = 15 - res (range 0..15) ---
    wire [3:0] q_damp = 4'd15 - res;

    // --- Signed input: unsigned 8-bit sample → signed (subtract 128) ---
    wire signed [15:0] s_in = {1'b0, sample_in} - 16'sd128;

    // --- Combinatorial SVF equations ---
    // bp * q_damp: 16s × 5u → need enough bits
    wire signed [20:0] bp_q   = bp * $signed({1'b0, q_damp});
    wire signed [15:0] bp_q16 = bp_q[18:3];  // divide by 8

    // HP = in - lp - bp*q/8
    wire signed [31:0] hp_wide = {s_in[15], s_in, 15'd0} -
                                 {lp[15], lp, 15'd0} -
                                 {bp_q16[15], bp_q16, 15'd0};
    wire signed [15:0] hp = sat16(hp_wide >>> 15);

    // BP_new = bp + fc * hp / 2048
    wire signed [27:0] fc_hp  = $signed({1'b0, fc}) * hp;
    wire signed [31:0] bp_new_wide = {bp, 16'd0} + {fc_hp, 4'd0};
    wire signed [15:0] bp_new = sat16(bp_new_wide >>> 16);

    // LP_new = lp + fc * bp_new / 2048
    wire signed [27:0] fc_bp  = $signed({1'b0, fc}) * bp_new;
    wire signed [31:0] lp_new_wide = {lp, 16'd0} + {fc_bp, 4'd0};
    wire signed [15:0] lp_new = sat16(lp_new_wide >>> 16);

    // --- State update ---
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            bp <= 16'sd0;
            lp <= 16'sd0;
        end else if (sample_valid && !bypass) begin
            bp <= bp_new;
            lp <= lp_new;
        end
    end

    // --- Mode output: sum selected filter outputs ---
    wire signed [15:0] mode_lp = mode[0] ? lp_new : 16'sd0;
    wire signed [15:0] mode_bp = mode[1] ? bp_new : 16'sd0;
    wire signed [15:0] mode_hp = mode[2] ? hp     : 16'sd0;

    wire signed [17:0] mode_sum = {mode_lp[15], mode_lp[15], mode_lp} +
                                  {mode_bp[15], mode_bp[15], mode_bp} +
                                  {mode_hp[15], mode_hp[15], mode_hp};
    // Saturate mode_sum to 16-bit signed
    wire signed [15:0] mode_out = (mode_sum > 18'sd32767)  ? 16'sd32767 :
                                  (mode_sum < -18'sd32768) ? -16'sd32768 :
                                  mode_sum[15:0];

    // --- Select filtered or bypass ---
    wire signed [15:0] pre_vol = bypass ? s_in : mode_out;

    // --- Volume scaling: pre_vol * vol / 16 ---
    wire signed [19:0] vol_prod = pre_vol * $signed({1'b0, vol});
    wire signed [15:0] scaled   = vol_prod[19:4];

    // --- Convert back to unsigned 8-bit with clamping ---
    wire signed [15:0] shifted = scaled + 16'sd128;
    wire [7:0] clamped = (shifted < 16'sd0)   ? 8'd0 :
                          (shifted > 16'sd255) ? 8'd255 :
                          shifted[7:0];

    assign sample_out = clamped;

    wire _unused = &{filt[3], mode[3], 1'b0};

endmodule
