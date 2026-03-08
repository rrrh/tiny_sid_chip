// Dual R-2R bias generator for gm-C SVF
// 11-bit DAC → ibias_fc (filter cutoff bias current)
// 4-bit DAC → ibias_q (filter Q/resonance bias current)
// Power (vdd/vss) connected via PDN, not RTL ports

`ifdef BEHAVIORAL_SIM
module bias_gen (
    input  wire fc0, fc1, fc2, fc3, fc4, fc5, fc6, fc7, fc8, fc9, fc10,
    input  wire q0, q1, q2, q3,
    output wire ibias_fc,
    output wire ibias_q
);
    // Behavioral: ibias outputs approximate digital-to-analog conversion
    // In simulation, the SVF behavioral model uses fixed parameters,
    // so these outputs are just placeholders.
    assign ibias_fc = fc10;  // MSB as 1-bit approximation
    assign ibias_q  = q3;
endmodule

`else
(* blackbox *)
module bias_gen (
    input  wire fc0, fc1, fc2, fc3, fc4, fc5, fc6, fc7, fc8, fc9, fc10,
    input  wire q0, q1, q2, q3,
    output wire ibias_fc,
    output wire ibias_q
);
endmodule
`endif
