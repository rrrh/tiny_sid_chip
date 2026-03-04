/* verilator lint_off UNUSEDSIGNAL */
//==========================================================================
// output_lpf — Single-pole IIR lowpass, fc ≈ 1244 Hz @ 1 MHz sample rate
//
//   y[n] = y[n-1] + (x[n] - y[n-1]) >>> 7     (alpha ≈ 1/128)
//   fc = -fs·ln(1-1/128)/(2π) ≈ 1244 Hz
//
//   16-bit unsigned accumulator (8.8 fixed-point), 8-bit output.
//   8 fractional bits eliminate the quantization dead zone.
//==========================================================================
module output_lpf (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       sample_valid,
    input  wire [7:0] sample_in,
    output wire [7:0] sample_out
);

    reg  [15:0] acc;                                          // 8.8 unsigned

    wire [15:0]        x_ext = {sample_in, 8'b0};            // input << 8
    wire signed [16:0] diff = {1'b0, x_ext} - {1'b0, acc};   // signed subtract
    wire signed [16:0] step = diff >>> 7;                     // alpha = 1/128

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            acc <= 16'd0;
        else if (sample_valid)
            acc <= acc + step[15:0];
    end

    assign sample_out = acc[15:8];

endmodule
