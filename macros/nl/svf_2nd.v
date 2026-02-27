// Blackbox: 2nd-order gm-C State Variable Filter (analog hard macro)
// Active filter using 4 OTAs + 2 MIM caps, IHP SG13G2
// OTA1/2/3: summing + integrators (fc controlled via ibias_fc)
// OTA4: damping (Q controlled via ibias_q)
// Provides LP/BP/HP/bypass outputs via 4:1 analog mux
// Power (vdd/vss) connected via PDN, not RTL ports
(* blackbox *)
module svf_2nd (
    input  wire       vin,       // analog input
    output wire       vout,      // mux-selected analog output
    input  wire [1:0] sel,       // filter mode: 00=LP, 01=BP, 10=HP, 11=bypass
    input  wire       ibias_fc,  // bias current input for fc (integrator OTAs)
    input  wire       ibias_q    // bias current input for Q (damping OTA)
);
endmodule
