// Blackbox: 2nd-order gm-C State Variable Filter (analog hard macro)
// Scalar pin names to match LEF for OpenROAD compatibility
// Power (vdd/vss) connected via PDN, not RTL ports
(* blackbox *)
module svf_2nd (
    input  wire vin,
    output wire vout,
    input  wire sel0, sel1,
    input  wire ibias_fc,
    input  wire ibias_q
);
endmodule
