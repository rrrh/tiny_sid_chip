`timescale 1ns / 1ps
//==============================================================================
// TT10 Wrapper — Triple SID Voice Synthesizer
//==============================================================================
// Instantiates:
//   - Three sid_voice instances with independent register banks
//   - pwm_audio:       8-bit PWM audio output (255-clock period, ~196 kHz)
//
// Flat Memory-Mapped Register Interface:
//   ui_in[2:0]  = register address (3-bit)
//   ui_in[4:3]  = voice select (0=voice1, 1=voice2, 2=voice3)
//   ui_in[7]    = write enable (active high, rising-edge triggered)
//   ui_in[6:5]  = unused
//   uio[7:0]    = data input (all inputs, directly driven by controller)
//   uo_out[0]   = pwm_out (8-bit PWM audio output)
//   uo_out[7:1] = 0
//
// Register Map (per voice):
//   0: freq_lo  — frequency[7:0]
//   1: freq_hi  — frequency[15:8]
//   2: pw       — duration[7:0] (pulse width)
//   3: (unused)
//   4: attack   — attack[7:0]
//   5: sustain  — sustain[7:0]
//   6: waveform — waveform[7:0]
//
// Mixing: sum three 8-bit voice outputs to 10-bit, right-shift by 2.
//==============================================================================

module tt_um_sid (
    input  wire [7:0] ui_in,
    output wire [7:0] uo_out,
    input  wire [7:0] uio_in,
    output wire [7:0] uio_out,
    output wire [7:0] uio_oe,
    input  wire       ena,
    input  wire       clk,
    input  wire       rst_n
);

    //==========================================================================
    // Input assignments
    //==========================================================================
    wire [2:0] reg_addr  = ui_in[2:0];
    wire [1:0] voice_sel = ui_in[4:3];
    wire       wr_en     = ui_in[7];
    wire [7:0] wr_data   = uio_in;

    wire rst = !rst_n;

    //==========================================================================
    // Write enable edge detection
    //==========================================================================
    reg wr_en_d;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) wr_en_d <= 1'b0;
        else        wr_en_d <= wr_en;
    wire wr_en_rise = wr_en && !wr_en_d;

    //==========================================================================
    // Voice 1 register bank
    //==========================================================================
    reg [15:0] v1_frequency;
    reg [7:0]  v1_duration;
    reg [7:0]  v1_attack, v1_sustain, v1_waveform;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v1_frequency <= 0; v1_duration <= 0;
            v1_attack <= 0; v1_sustain <= 0; v1_waveform <= 0;
        end else if (wr_en_rise && voice_sel == 2'd0) begin
            case (reg_addr)
                3'd0: v1_frequency[7:0]  <= wr_data;
                3'd1: v1_frequency[15:8] <= wr_data;
                3'd2: v1_duration         <= wr_data;
                3'd4: v1_attack          <= wr_data;
                3'd5: v1_sustain         <= wr_data;
                3'd6: v1_waveform        <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Voice 2 register bank
    //==========================================================================
    reg [15:0] v2_frequency;
    reg [7:0]  v2_duration;
    reg [7:0]  v2_attack, v2_sustain, v2_waveform;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v2_frequency <= 0; v2_duration <= 0;
            v2_attack <= 0; v2_sustain <= 0; v2_waveform <= 0;
        end else if (wr_en_rise && voice_sel == 2'd1) begin
            case (reg_addr)
                3'd0: v2_frequency[7:0]  <= wr_data;
                3'd1: v2_frequency[15:8] <= wr_data;
                3'd2: v2_duration         <= wr_data;
                3'd4: v2_attack          <= wr_data;
                3'd5: v2_sustain         <= wr_data;
                3'd6: v2_waveform        <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Voice 3 register bank
    //==========================================================================
    reg [15:0] v3_frequency;
    reg [7:0]  v3_duration;
    reg [7:0]  v3_attack, v3_sustain, v3_waveform;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v3_frequency <= 0; v3_duration <= 0;
            v3_attack <= 0; v3_sustain <= 0; v3_waveform <= 0;
        end else if (wr_en_rise && voice_sel == 2'd2) begin
            case (reg_addr)
                3'd0: v3_frequency[7:0]  <= wr_data;
                3'd1: v3_frequency[15:8] <= wr_data;
                3'd2: v3_duration         <= wr_data;
                3'd4: v3_attack          <= wr_data;
                3'd5: v3_sustain         <= wr_data;
                3'd6: v3_waveform        <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Shared ADSR prescaler (free-running 23-bit counter)
    //==========================================================================
    reg [22:0] adsr_prescaler;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) adsr_prescaler <= 23'd0;
        else        adsr_prescaler <= adsr_prescaler + 1'b1;

    //==========================================================================
    // SID Voice 1
    //==========================================================================
    wire [7:0] voice1_out;

    sid_voice #(.IS_8580(0)) u_voice1 (
        .clk                (clk),
        .rst                (rst),
        .frequency          (v1_frequency),
        .duration           (v1_duration),
        .attack             (v1_attack),
        .sustain            (v1_sustain),
        .waveform           (v1_waveform),
        .prescaler          (adsr_prescaler),
        .voice              (voice1_out)
    );

    //==========================================================================
    // SID Voice 2
    //==========================================================================
    wire [7:0] voice2_out;

    sid_voice #(.IS_8580(0)) u_voice2 (
        .clk                (clk),
        .rst                (rst),
        .frequency          (v2_frequency),
        .duration           (v2_duration),
        .attack             (v2_attack),
        .sustain            (v2_sustain),
        .waveform           (v2_waveform),
        .prescaler          (adsr_prescaler),
        .voice              (voice2_out)
    );

    //==========================================================================
    // SID Voice 3
    //==========================================================================
    wire [7:0] voice3_out;

    sid_voice #(.IS_8580(0)) u_voice3 (
        .clk                (clk),
        .rst                (rst),
        .frequency          (v3_frequency),
        .duration           (v3_duration),
        .attack             (v3_attack),
        .sustain            (v3_sustain),
        .waveform           (v3_waveform),
        .prescaler          (adsr_prescaler),
        .voice              (voice3_out)
    );

    //==========================================================================
    // Mix: sum three voices to 10-bit, right-shift by 2
    //==========================================================================
    wire [9:0] mix = {2'b0, voice1_out} + {2'b0, voice2_out} + {2'b0, voice3_out};
    wire [7:0] mix_out = mix[9:2];

    //==========================================================================
    // PWM Audio Output (8-bit, ~196 kHz)
    //==========================================================================
    wire pwm_out;

    pwm_audio u_pwm (
        .clk    (clk),
        .rst_n  (rst_n),
        .sample (mix_out),
        .pwm    (pwm_out)
    );

    //==========================================================================
    // Output Pin Mapping
    //==========================================================================
    assign uo_out  = {7'b0, pwm_out};
    assign uio_out = 8'b0;
    assign uio_oe  = 8'b0;  // all inputs

    // Suppress unused input warnings
    wire _unused = &{ena, ui_in[6:5], 1'b0};

endmodule
