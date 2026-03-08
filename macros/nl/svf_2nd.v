// 2nd-order gm-C State Variable Filter (analog hard macro)
// Scalar pin names to match LEF for OpenROAD compatibility
// Power (vdd/vss) connected via PDN, not RTL ports
//
// gm-C topology — fc and Q set by analog bias currents:
//   ibias_fc : bias current input for fc-controlling OTAs
//   ibias_q  : bias current input for Q-controlling OTA

`ifdef BEHAVIORAL_SIM
//----------------------------------------------------------------------
// Behavioral model: 2nd-order state variable filter using real arithmetic.
// Parent writes sim_data_in[7:0] (from DAC) and reads sim_data_out[7:0]
// (to comparator) via hierarchical references.
//
// SVF topology (discrete-time, one iteration per sample_clk posedge):
//   hp = input - damping*bp - lp
//   bp += alpha * hp
//   lp += alpha * bp          (uses updated bp — standard SVF)
//
// alpha ≈ 0.0673 (fixed for behavioral model)
// damping = 1.0 (fixed Q for behavioral model)
// sel = {sel1,sel0}: 00=LP, 01=BP, 10=HP, 11=bypass
//----------------------------------------------------------------------
module svf_2nd (
    input  wire vin,
    output wire vout,
    input  wire sel0, sel1,
    input  wire ibias_fc,
    input  wire ibias_q
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

    localparam real ALPHA = 0.0673;   // gm / (2*pi*C) normalized

    always @(posedge sample_clk) begin : svf_update
        integer out_i;

        damp_r = 1.0;  // Fixed Q for behavioral model

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
    input  wire ibias_fc,
    input  wire ibias_q
);
endmodule
`endif
