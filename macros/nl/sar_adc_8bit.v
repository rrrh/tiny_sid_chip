// Blackbox: 8-bit SAR ADC (analog hard macro)
// Scalar pin names (dout0..dout7) to match LEF for OpenROAD compatibility
// Power (vdd/vss) connected via PDN, not RTL ports
(* blackbox *)
module sar_adc_8bit (
    input  wire clk,
    input  wire rst_n,
    input  wire vin,
    input  wire start,
    output wire eoc,
    output wire dout0, dout1, dout2, dout3,
    output wire dout4, dout5, dout6, dout7
);
endmodule
