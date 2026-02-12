`timescale 1ns / 1ps
//==============================================================================
// First-Order Delta-Sigma DAC
//==============================================================================
// Converts a 12-bit unsigned audio input to a 1-bit PDM output stream.
// The carry bit of a 12-bit accumulator produces the pulse-density modulated
// output. At 50 MHz clock with 20 kHz audio bandwidth (OSR ≈ 1250), the
// first-order noise shaping yields ~99 dB theoretical SNR.
//
// External circuit: single RC low-pass filter on pdm_out.
//==============================================================================

module delta_sigma_dac (
    input  wire        clk,
    input  wire        rst,
    input  wire [11:0] din,
    output reg         pdm_out
);

    reg [11:0] acc;

    always @(posedge clk) begin
        if (rst) begin
            acc     <= 12'd0;
            pdm_out <= 1'b0;
        end else begin
            {pdm_out, acc} <= acc + din;
        end
    end

endmodule
