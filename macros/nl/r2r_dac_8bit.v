// 8-bit R-2R DAC (analog hard macro)
// Scalar pin names (d0..d7) to match LEF for OpenROAD compatibility
// Power (vdd/vss) connected via PDN, not RTL ports

`ifdef BEHAVIORAL_SIM
//----------------------------------------------------------------------
// Behavioral model: captures 8-bit digital input as sim_data_out[7:0].
// Parent connects sim_data_out to downstream SVF via hierarchical ref.
// vout drives MSB (d7) as a 1-bit approximation on the analog wire.
//----------------------------------------------------------------------
module r2r_dac_8bit (
    input  wire d0, d1, d2, d3, d4, d5, d6, d7,
    output wire vout
);
    reg [7:0] sim_data_out;
    always @* sim_data_out = {d7, d6, d5, d4, d3, d2, d1, d0};
    assign vout = d7;
endmodule

`else
(* blackbox *)
module r2r_dac_8bit (
    input  wire d0, d1, d2, d3, d4, d5, d6, d7,
    output wire vout
);
endmodule
`endif
