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

    // Shared prescaler for ADSR
    reg [15:0] prescaler;
    always @(posedge clk) begin
        if (rst)
            prescaler <= 16'd0;
        else
            prescaler <= prescaler + 1'b1;
    end

    sid_voice #(.IS_8580(0)) u_voice (
        .clk                (clk),
        .rst                (rst),
        .frequency          (frequency),
        .duration           (duration),
        .attack             (attack),
        .sustain            (sustain),
        .waveform           (waveform),
        .accumulator_msb_in (1'b0),
        .prescaler          (prescaler),
        .voice              (audio_out),
        .accumulator_msb_out()
    );

endmodule
