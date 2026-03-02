// 8-bit SAR ADC (analog hard macro)
// Scalar pin names (dout0..dout7) to match LEF for OpenROAD compatibility
// Power (vdd/vss) connected via PDN, not RTL ports

`ifdef BEHAVIORAL_SIM
//----------------------------------------------------------------------
// Behavioral model: 8-bit successive approximation ADC.
// Parent writes sim_data_in[7:0] (from SVF) via hierarchical reference.
// On 'start' rising edge, latches input and begins conversion.
// After 9 clock cycles, asserts eoc for 1 cycle and outputs result.
//----------------------------------------------------------------------
module sar_adc_8bit (
    input  wire clk,
    input  wire rst_n,
    input  wire vin,
    input  wire start,
    output wire eoc,
    output wire dout0, dout1, dout2, dout3,
    output wire dout4, dout5, dout6, dout7
);
    // Simulation data bus (written by parent via hier ref)
    reg [7:0] sim_data_in;

    reg [7:0] result;
    reg [3:0] count;
    reg        converting;
    reg        eoc_r;
    reg        start_d;

    initial begin
        sim_data_in = 8'd128;
        result      = 8'd0;
        count       = 4'd0;
        converting  = 1'b0;
        eoc_r       = 1'b0;
        start_d     = 1'b0;
    end

    wire start_rise = start && !start_d;

    assign eoc   = eoc_r;
    assign dout0 = result[0];
    assign dout1 = result[1];
    assign dout2 = result[2];
    assign dout3 = result[3];
    assign dout4 = result[4];
    assign dout5 = result[5];
    assign dout6 = result[6];
    assign dout7 = result[7];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            result     <= 8'd0;
            count      <= 4'd0;
            converting <= 1'b0;
            eoc_r      <= 1'b0;
            start_d    <= 1'b0;
        end else begin
            start_d <= start;
            eoc_r   <= 1'b0;

            if (start_rise && !converting) begin
                converting <= 1'b1;
                count      <= 4'd0;
                result     <= sim_data_in;
            end else if (converting) begin
                if (count == 4'd9) begin
                    converting <= 1'b0;
                    eoc_r      <= 1'b1;
                end else begin
                    count <= count + 4'd1;
                end
            end
        end
    end
endmodule

`else
(* blackbox *)
module sar_adc_8bit (
    input  wire clk,
    input  wire rst_n,
    input  wire vin,
    input  wire start,
    output wire eoc,
    output wire dout0, dout1, dout2, dout3,
    output wire dout4, dout5, dout6, dout7
);
endmodule
`endif
