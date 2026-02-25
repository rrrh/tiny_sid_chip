//==========================================================================
// lpf_1500 — Single-pole IIR lowpass, fc ≈ 2000 Hz @ 800 kHz sample rate
//
//   y[n] = y[n-1] + (x[n] - y[n-1]) >>> 6     (alpha ≈ 1/64)
//   fc = -fs·ln(1-1/64)/(2π) ≈ 2005 Hz
//
//   10-bit unsigned accumulator (8.2 fixed-point), 8-bit output.
//   Tracking granularity: ~16 LSB (6%). Minimal area for 1×2 tile.
//==========================================================================
module lpf_1500 (
    input  wire       clk,
    input  wire       rst_n,
    input  wire       sample_valid,
    input  wire [7:0] sample_in,
    output wire [7:0] sample_out
);

    reg  [9:0] acc;                                         // 8.2 unsigned

    wire [9:0]        x_ext = {sample_in, 2'b0};           // input << 2
    wire signed [10:0] diff = {1'b0, x_ext} - {1'b0, acc}; // signed subtract
    wire signed [10:0] step = diff >>> 6;                   // alpha = 1/64

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            acc <= 10'd0;
        else if (sample_valid)
            acc <= acc + step[9:0];
    end

    assign sample_out = acc[9:2];

endmodule
