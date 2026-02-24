`timescale 1ns / 1ps
//==============================================================================
// Pass-through filter (placeholder for future filter implementations)
//==============================================================================
module filter (
    input  wire       clk,
    input  wire       rst_n,
    input  wire [7:0] sample_in,
    output wire [7:0] sample_out
);

    assign sample_out = sample_in;

    wire _unused = &{clk, rst_n, 1'b0};

endmodule
