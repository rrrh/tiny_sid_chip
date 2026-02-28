/* verilator lint_off UNUSEDSIGNAL */
`timescale 1ns / 1ps
//==============================================================================
// TT Top-Level — On-Chip Analog DAC + ADC with Internal Signal Path
//==============================================================================
// 8-bit digital input → R-2R DAC → gm-C SVF (LP/BP/HP/bypass) → SAR ADC → 8-bit digital output
// SPI shift register loads fc/Q bias DAC registers via uio_in[4:2]
// All analog signals stay on-chip. No analog pins used.
// Target: IHP SG13G2 130nm, Tiny Tapeout 1×2 tile (202.08 × 313.74 µm)
//==============================================================================

module tt_um_rrrh_svf (
    input  wire [7:0] ui_in,      // 8-bit digital input → DAC
    output wire [7:0] uo_out,     // 8-bit digital output ← ADC
    input  wire [7:0] uio_in,     // control/config
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

    //==========================================================================
    // Internal analog wires (routed as metal interconnect)
    //==========================================================================
    wire dac_out;          // DAC analog output (single wire)
    wire filter_out;       // Filter analog output
    wire bias_fc;          // fc bias voltage from bias DAC
    wire bias_q;           // Q bias voltage from bias DAC

    //==========================================================================
    // SPI shift register for bias DAC control
    //==========================================================================
    // uio_in[4] = SDI (serial data in)
    // uio_in[3] = SCK (serial clock)
    // uio_in[2] = LOAD (latch data to output registers)
    //==========================================================================
    wire sdi  = uio_in[4];
    wire sck  = uio_in[3];
    wire load = uio_in[2];

    reg [7:0] spi_sr;        // 8-bit shift register
    reg [3:0] fc_reg;        // fc DAC register (bits [3:0] of latched data)
    reg [3:0] q_reg;         // Q DAC register (bits [7:4] of latched data)
    reg       sck_prev;      // SCK edge detect
    reg       load_prev;     // LOAD edge detect

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            spi_sr    <= 8'b0;
            fc_reg    <= 4'b0;
            q_reg     <= 4'b0;
            sck_prev  <= 1'b0;
            load_prev <= 1'b0;
        end else begin
            sck_prev  <= sck;
            load_prev <= load;

            // Shift on SCK rising edge (MSB first)
            if (sck && !sck_prev) begin
                spi_sr <= {spi_sr[6:0], sdi};
            end

            // Latch on LOAD rising edge
            if (load && !load_prev) begin
                fc_reg <= spi_sr[3:0];
                q_reg  <= spi_sr[7:4];
            end
        end
    end

    //==========================================================================
    // SAR ADC control signals
    //==========================================================================
    wire       adc_eoc;   // end-of-conversion
    wire [7:0] adc_result;

    //==========================================================================
    // Conversion start control
    //==========================================================================
    reg adc_busy;
    reg adc_start;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            adc_busy  <= 1'b0;
            adc_start <= 1'b0;
        end else begin
            if (adc_eoc) begin
                adc_busy  <= 1'b0;
                adc_start <= 1'b1;   // auto-restart
            end else if (adc_start) begin
                adc_start <= 1'b0;
                adc_busy  <= 1'b1;
            end else if (!adc_busy) begin
                adc_start <= 1'b1;   // initial start after reset
            end
        end
    end

    //==========================================================================
    // Hard macro instantiations
    //==========================================================================

    // 8-bit R-2R DAC — converts digital input to analog voltage
    r2r_dac_8bit u_dac (
        .d    (ui_in),
        .vdd  (1'b1),
        .vss  (1'b0),
        .vout (dac_out)
    );

    // Dual-channel 4-bit bias DAC — generates fc and Q bias voltages
    bias_dac_2ch u_bias_dac (
        .d_fc    (fc_reg),
        .d_q     (q_reg),
        .vout_fc (bias_fc),
        .vout_q  (bias_q),
        .vdd     (1'b1),
        .vss     (1'b0)
    );

    // 2nd-order gm-C state variable filter — LP/BP/HP/bypass selectable
    svf_2nd u_filter (
        .vin      (dac_out),
        .vout     (filter_out),
        .sel      (uio_in[1:0]),    // 00=LP, 01=BP, 10=HP, 11=bypass
        .ibias_fc (bias_fc),
        .ibias_q  (bias_q),
        .vdd      (1'b1),
        .vss      (1'b0)
    );

    // 8-bit SAR ADC — converts filtered analog signal back to digital
    sar_adc_8bit u_adc (
        .clk   (clk),
        .rst_n (rst_n),
        .vin   (filter_out),
        .start (adc_start),
        .vdd   (1'b1),
        .vss   (1'b0),
        .eoc   (adc_eoc),
        .dout  (adc_result)
    );

    //==========================================================================
    // Output assignments
    //==========================================================================
    assign uo_out  = adc_result;
    assign uio_out = {7'b0, adc_eoc};
    assign uio_oe  = 8'b0000_0001;    // uio[0] = eoc output

    wire _unused = &{ena, uio_in[7:5], adc_busy, 1'b0};

endmodule
