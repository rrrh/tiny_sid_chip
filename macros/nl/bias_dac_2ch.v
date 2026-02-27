// Blackbox: Dual-channel 4-bit R-2R bias DAC (analog hard macro)
// Scalar pin names to match LEF for OpenROAD compatibility
// Power (vdd/vss) connected via PDN, not RTL ports
(* blackbox *)
module bias_dac_2ch (
    input  wire dfc0, dfc1, dfc2, dfc3,
    input  wire dq0, dq1, dq2, dq3,
    output wire vout_fc,
    output wire vout_q
);
endmodule
