// Blackbox: 2nd-order Switched-Capacitor State Variable Filter (analog hard macro)
// Scalar pin names to match LEF for OpenROAD compatibility
// Power (vdd/vss) connected via PDN, not RTL ports
//
// SC SVF replaces gm-C topology:
//   sc_clk  : switching clock (from programmable divider), sets fc
//   q0..q3  : 4-bit binary-weighted C_Q array switches, sets Q
(* blackbox *)
module svf_2nd (
    input  wire vin,
    output wire vout,
    input  wire sel0, sel1,
    input  wire sc_clk,
    input  wire q0, q1, q2, q3
);
endmodule
