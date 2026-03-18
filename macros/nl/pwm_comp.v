// PWM Comparator (analog hard macro)
// Simple OTA + inverter: 7 transistors total
// Scalar pin names to match LEF for OpenROAD compatibility
// Power (vdd/vss) connected via PDN, not RTL ports

`ifdef BEHAVIORAL_SIM
//----------------------------------------------------------------------
// Behavioral model: comparator for analog PWM generation.
// Parent writes sim_data_in[7:0] (from SVF) and sim_ramp_in[7:0]
// (from ramp DAC) via hierarchical references.
// Output is high when vinp > vinn (i.e., SVF output > ramp).
//----------------------------------------------------------------------
module pwm_comp (
    input  wire vinp,    // + input (SVF output)
    input  wire vinn,    // - input (ramp reference)
    output wire out      // high when vinp > vinn
);
    // Simulation data buses (written by parent via hier ref)
    reg [7:0] sim_data_in;   // SVF output (8-bit digital equivalent)
    reg [7:0] sim_ramp_in;   // Ramp DAC output (8-bit digital equivalent)

    initial begin
        sim_data_in = 8'd128;
        sim_ramp_in = 8'd0;
    end

    assign out = (sim_data_in > sim_ramp_in) ? 1'b1 : 1'b0;
endmodule

`else
(* blackbox *)
module pwm_comp (
    input  wire vinp,
    input  wire vinn,
    output wire out
);
endmodule
`endif
