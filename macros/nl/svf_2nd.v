// 2nd-order SC+OTA State Variable Filter (analog hard macro)
// Tow-Thomas biquad with switched-cap resistors and OTA integrators.
// Scalar pin names to match LEF for OpenROAD compatibility.
// Power (vdd/vss) connected via PDN, not RTL ports.
//
// SC+OTA topology — fc set by sc_clk, Q set by cap ratio (q[3:0]):
//   sc_clk : switched-cap clock (from NCO phase accumulator MSB)
//   q[3:0] : Q select — enables binary-weighted Csw_q unit caps
//   sel0/sel1 : output mux (00=LP, 01=BP, 10=HP, 11=bypass)

`ifdef BEHAVIORAL_SIM
//----------------------------------------------------------------------
// Behavioral model: 2nd-order SVF using real arithmetic.
// Parent writes sim_data_in[7:0] (from DAC) and reads sim_data_out[7:0]
// (to comparator) via hierarchical references.
//
// SVF topology (Tow-Thomas, one iteration per sample_clk posedge):
//   hp = input - (1/Q)*bp - lp
//   bp += alpha * hp
//   lp += alpha * bp
//
// alpha ≈ 0.0673 (fixed for behavioral model)
// sel = {sel1,sel0}: 00=LP, 01=BP, 10=HP, 11=bypass
//----------------------------------------------------------------------
module svf_2nd (
    input  wire vin,
    output wire vout,
    input  wire sel0, sel1,
    input  wire sc_clk,
    input  wire q0, q1, q2, q3
);
    // Simulation data bus (written/read by parent via hier ref)
    reg [7:0] sim_data_in;
    reg [7:0] sim_data_out;

    // Filter state
    real lp, bp;
    real hp_r, in_r, out_r, damp_r;

    // Internal sample clock for behavioral sim (not a real pin)
    reg sample_clk;
    initial begin
        lp = 0.0;
        bp = 0.0;
        sim_data_in  = 8'd128;
        sim_data_out = 8'd128;
        sample_clk = 0;
        forever #500 sample_clk = ~sample_clk; // 1 MHz sample rate
    end

    localparam real ALPHA = 0.0673;   // Csw*fclk / (2*pi*Cint) normalized

    always @(posedge sample_clk) begin : svf_update
        integer out_i;
        integer q_val;

        // Q from binary-weighted caps: q_val = q3*8 + q2*4 + q1*2 + q0
        // Q = Csw_in / (q_val * Cq_unit), damping = 1/Q
        q_val = q3*8 + q2*4 + q1*2 + q0;
        if (q_val == 0)
            damp_r = 0.067;  // near self-oscillation
        else
            damp_r = q_val / 15.0;  // 1/15 to 1.0

        // AC-couple: center 0-255 around zero
        in_r = (sim_data_in - 128.0) / 128.0;

        // SVF iteration (blocking assigns for correct topology)
        hp_r = in_r - damp_r * bp - lp;
        bp   = bp + ALPHA * hp_r;
        lp   = lp + ALPHA * bp;

        case ({sel1, sel0})
            2'b00:   out_r = lp;
            2'b01:   out_r = bp;
            2'b10:   out_r = hp_r;
            default: out_r = in_r;
        endcase

        // Convert back to 0-255
        out_i = $rtoi(out_r * 128.0 + 128.5);
        if (out_i < 0)   sim_data_out = 8'd0;
        else if (out_i > 255) sim_data_out = 8'd255;
        else              sim_data_out = out_i[7:0];
    end

    assign vout = sim_data_out[7];
endmodule

`else
(* blackbox *)
module svf_2nd (
    input  wire vin,
    output wire vout,
    input  wire sel0, sel1,
    input  wire sc_clk,
    input  wire q0, q1, q2, q3
);
endmodule
`endif
