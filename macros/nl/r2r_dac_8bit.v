// Blackbox: 8-bit R-2R DAC (analog hard macro)
// Scalar pin names (d0..d7) to match LEF for OpenROAD compatibility
// Power (vdd/vss) connected via PDN, not RTL ports
(* blackbox *)
module r2r_dac_8bit (
    input  wire d0, d1, d2, d3, d4, d5, d6, d7,
    output wire vout
);
endmodule
