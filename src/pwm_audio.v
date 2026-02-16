`timescale 1ns / 1ps
`default_nettype none
//==============================================================================
// PWM Audio Output (8-bit)
//==============================================================================
// 8-bit PWM with 255-clock period.
// Output is high for `sample` clocks out of every 255 clocks.
// sample=0 → always off, sample=255 → always on.
//
// At 50 MHz clock: PWM frequency = 50 MHz / 255 ≈ 196 kHz.
//
// Based on MichaelBell/tt08-pwm-example.
//==============================================================================

module pwm_audio (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [7:0]  sample,
    output reg         pwm
);

    reg [7:0] count;

    always @(posedge clk) begin
        if (!rst_n) count <= 0;
        else begin
            pwm <= count < sample;
            count <= count + 1;
            if (count == 8'hfe) count <= 0;
        end
    end

endmodule
