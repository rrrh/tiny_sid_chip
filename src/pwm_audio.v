`default_nettype none
`timescale 1ns / 1ps
//==============================================================================
// PWM Audio Output (12-bit)
//==============================================================================
// 12-bit PWM with 4095-clock period.
// Output is high for `sample` clocks out of every 4095 clocks.
// sample=0 → always off, sample=4095 → always on.
//
// At 50 MHz clock: PWM frequency = 50 MHz / 4095 ≈ 12.2 kHz.
//
// Based on MichaelBell/tt08-pwm-example (extended to 12-bit).
//==============================================================================

module pwm_audio (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [11:0] sample,
    output reg         pwm
);

    reg [11:0] count;

    always @(posedge clk) begin
        if (!rst_n) count <= 0;
        else begin
            pwm <= count < sample;
            count <= count + 1;
            if (count == 12'hffe) count <= 0;
        end
    end

endmodule
