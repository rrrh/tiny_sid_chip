/* verilator lint_off UNUSEDSIGNAL */
`timescale 1ns / 1ps
//==============================================================================
// SID Filter Wrapper — delegates to SVF_8bit core
//==============================================================================
// Keeps the SID-compatible interface (fc, res, filt, mode, vol, bypass, mode
// mixing, volume scaling) but replaces the filter math with SVF_8bit.
//
// Coefficient mapping:
//   alpha1 (frequency) = fc[10:6] — 5-bit, shift-add /32
//   alpha2 (damping)   = 15 - res — 4-bit, shift-add /8 (exact)
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

    // --- Bypass condition ---
    wire bypass = (filt[2:0] == 3'd0) || (mode[2:0] == 3'd0);

    // --- Signed input: unsigned 8-bit sample → signed (subtract 128) ---
    wire signed [7:0] s_in = sample_in - 8'd128;

    // --- Coefficient mapping ---
    // alpha1: fc[10:6] — 5-bit frequency coefficient (shift-add /32)
    wire [4:0] alpha1 = fc[10:6];

    // alpha2: q_damp = 15 - res — 4-bit damping (shift-add /8, exact)
    wire [3:0] alpha2 = 4'd15 - res;

    // --- SVF_8bit core ---
    wire signed [7:0] hp_out, bp_out, lp_out;

    SVF_8bit u_svf (
        .clk          (clk),
        .rst          (~rst_n),
        .audio_in     (s_in),
        .audio_out_hp (hp_out),
        .audio_out_lp (lp_out),
        .audio_out_bp (bp_out),
        .sample_valid (sample_valid & ~bypass),
        .alpha1       (alpha1),
        .alpha2       (alpha2)
    );

    // --- Mode output: sum selected filter outputs (SID-compatible) ---
    wire signed [7:0] mode_lp = mode[0] ? lp_out : 8'sd0;
    wire signed [7:0] mode_bp = mode[1] ? bp_out : 8'sd0;
    wire signed [7:0] mode_hp = mode[2] ? hp_out : 8'sd0;

    wire signed [9:0] mode_sum = {mode_lp[7], mode_lp[7], mode_lp} +
                                  {mode_bp[7], mode_bp[7], mode_bp} +
                                  {mode_hp[7], mode_hp[7], mode_hp};
    // Saturate to 8-bit signed
    wire signed [7:0] mode_out = (mode_sum > 10'sd127)  ? 8'sd127 :
                                  (mode_sum < -10'sd128) ? -8'sd128 :
                                  mode_sum[7:0];

    // --- Select filtered or bypass ---
    wire signed [7:0] pre_vol = bypass ? s_in : mode_out;

    // --- Convert to unsigned, then scale by volume ---
    // Unsigned first so vol=0 → output 0 (true silence), matching real SID DAC.
    wire [7:0] pre_u = pre_vol ^ 8'sh80;

    // Volume scaling: pre_u * vol / 16 (shift-add on unsigned, exact)
    wire [7:0] scaled = (vol[3] ? {1'b0, pre_u[7:1]} : 8'd0) +
                         (vol[2] ? {2'b0, pre_u[7:2]} : 8'd0) +
                         (vol[1] ? {3'b0, pre_u[7:3]} : 8'd0) +
                         (vol[0] ? {4'b0, pre_u[7:4]} : 8'd0);

    assign sample_out = scaled;

    wire _unused = &{filt[3], mode[3], 1'b0};

endmodule
