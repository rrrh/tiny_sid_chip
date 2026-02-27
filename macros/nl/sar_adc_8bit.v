// Blackbox: 8-bit SAR ADC (analog hard macro)
// Dynamic latch comparator + binary-weighted capacitive DAC + SAR logic
// 8–10 clock cycles per conversion
// Power (vdd/vss) connected via PDN, not RTL ports
(* blackbox *)
module sar_adc_8bit (
    input  wire       clk,     // conversion clock
    input  wire       rst_n,   // active-low reset
    input  wire       vin,     // analog input
    input  wire       start,   // start conversion
    output wire       eoc,     // end-of-conversion
    output wire [7:0] dout     // 8-bit digital output
);
endmodule
