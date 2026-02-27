// Blackbox: 8-bit R-2R DAC (analog hard macro)
// R-2R resistor ladder using IHP SG13G2 rsil (7 Ω/sq)
// 8 CMOS switches controlled by digital input bits
// Output: single analog voltage on vout
// Power (vdd/vss) connected via PDN, not RTL ports
(* blackbox *)
module r2r_dac_8bit (
    input  wire [7:0] d,       // 8-bit digital input
    output wire       vout     // analog output
);
endmodule
