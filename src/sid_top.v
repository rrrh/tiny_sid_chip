`timescale 1ns / 1ps
//==============================================================================
// SID Top Level — Single Voice
//==============================================================================

module sid_top (
    input  wire        clk,
    input  wire        rst,

    // Voice controls
    input  wire [15:0] frequency,
    input  wire [7:0]  duration,
    input  wire [7:0]  attack,
    input  wire [7:0]  sustain,
    input  wire [7:0]  waveform,

    // Audio output
    output wire [7:0]  audio_out
);

    sid_voice #(.IS_8580(0)) u_voice (
        .clk                (clk),
        .rst                (rst),
        .frequency          (frequency),
        .duration           (duration),
        .attack             (attack),
        .sustain            (sustain),
        .waveform           (waveform),
        .accumulator_msb_in (1'b0),
        .voice              (audio_out),
        .accumulator_msb_out()
    );

endmodule
