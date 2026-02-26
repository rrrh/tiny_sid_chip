/* verilator lint_off UNUSEDSIGNAL */
/* verilator lint_off WIDTHTRUNC */
`timescale 1ns / 1ps
//==============================================================================
// SID Filter Wrapper — delegates to SVF_8bit core
//==============================================================================
// Keeps the SID-compatible interface (fc, res, filt, mode, vol, bypass, mode
// mixing, volume scaling) but replaces the filter math with SVF_8bit.
//
// Coefficient mapping:
//   alpha1 (frequency) = fc[10:5] — 6-bit shift-add, alpha = fc[10:5]/512
//                        fc ≈ fc[10:5] × 497 Hz (range ~497 Hz to ~32 kHz)
//   alpha2 (damping)   = (15 - res) >> 2 — 2-bit, shift-add /4
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
    // alpha1: full 11-bit fc — alpha = fc / 16384
    wire [10:0] alpha1 = fc;

    // alpha2: (15 - res) >> 2 — 2-bit damping (shift-add /4)
    wire [1:0] alpha2 = (4'd15 - res) >> 2;

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

    // --- Mode output: priority mux (HP > BP > LP) ---
    wire signed [7:0] mode_out = mode[2] ? hp_out :
                                  mode[1] ? bp_out :
                                  mode[0] ? lp_out : 8'sd0;

    // --- Select filtered or bypass ---
    // Bypass: pass sample_in unchanged (unattenuated, no volume scaling)
    // Active: apply volume scaling to filtered output
    wire signed [7:0] pre_vol = mode_out;
    wire [7:0] pre_u = pre_vol ^ 8'sh80;

    // Volume scaling: pre_u * vol / 16 (shift-add on unsigned, exact)
    wire [7:0] scaled = (vol[3] ? {1'b0, pre_u[7:1]} : 8'd0) +
                         (vol[2] ? {2'b0, pre_u[7:2]} : 8'd0) +
                         (vol[1] ? {3'b0, pre_u[7:3]} : 8'd0) +
                         (vol[0] ? {4'b0, pre_u[7:4]} : 8'd0);

    assign sample_out = bypass ? sample_in : scaled;

    wire _unused = &{filt[3], mode[3], res, 1'b0};

endmodule
