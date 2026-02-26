// Blackbox: Dual-channel 4-bit R-2R bias DAC (analog hard macro)
// Two independent 4-bit R-2R ladders for SVF bias control
// Channel 1: d_fc[3:0] → vout_fc (fc bias for integrator OTAs)
// Channel 2: d_q[3:0]  → vout_q  (Q bias for damping OTA)
(* blackbox *)
module bias_dac_2ch (
    input  wire [3:0] d_fc,     // 4-bit fc DAC digital input
    input  wire [3:0] d_q,      // 4-bit Q DAC digital input
    output wire       vout_fc,  // fc bias voltage output
    output wire       vout_q,   // Q bias voltage output
    input  wire       vdd,      // power supply
    input  wire       vss       // ground
);
endmodule
