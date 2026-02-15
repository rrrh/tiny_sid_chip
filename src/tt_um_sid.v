`timescale 1ns / 1ps
//==============================================================================
// TT10 Wrapper — SID Voice Synthesizer
//==============================================================================
// Instantiates:
//   - spi_regs:        SPI slave → write-only register bank (16-bit frames)
//   - sid_voice:       SID waveform generator with ADSR envelope
//   - pwm_audio:       8-bit PWM audio output (255-clock period, ~196 kHz)
//
// SPI Protocol (CPOL=0, CPHA=0, MSB first):
//   16-bit write frame: [15:13]=addr[2:0]  [12:8]=reserved  [7:0]=data
//   Registers: 0=freq_lo, 1=freq_hi, 2=pw_lo, 3=pw_hi,
//              4=attack, 5=sustain, 6=waveform
//
// Pin Mapping:
//   ui_in[0]    = spi_cs_n      ui_in[3:7] = unused
//   ui_in[1]    = spi_clk
//   ui_in[2]    = spi_mosi
//   uo_out[0]   = spi_miso (tied low, write-only)
//   uo_out[7:1] = 0
//   uio[7]      = pwm_out (8-bit PWM audio output)
//   uio[6:0]    = unused (input, no drive)
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
    wire spi_cs_n_in = ui_in[0];
    wire spi_clk_in  = ui_in[1];
    wire spi_mosi_in = ui_in[2];

    wire rst = !rst_n;

    //==========================================================================
    // SPI Register Bank (write-only)
    //==========================================================================
    wire [15:0] sid_frequency;
    wire [15:0] sid_duration;
    wire [7:0]  sid_attack;
    wire [7:0]  sid_sustain;
    wire [7:0]  sid_waveform;

    spi_regs u_spi_regs (
        .clk           (clk),
        .rst_n         (rst_n),
        .spi_clk       (spi_clk_in),
        .spi_cs_n      (spi_cs_n_in),
        .spi_mosi      (spi_mosi_in),
        .spi_miso      (uo_out[0]),
        .sid_frequency (sid_frequency),
        .sid_duration  (sid_duration),
        .sid_attack    (sid_attack),
        .sid_sustain   (sid_sustain),
        .sid_waveform  (sid_waveform)
    );

    //==========================================================================
    // SID Voice
    //==========================================================================
    wire [7:0]  voice_out;

    sid_voice #(.IS_8580(0)) u_voice (
        .clk                (clk),
        .rst                (rst),
        .frequency          (sid_frequency),
        .duration           (sid_duration),
        .attack             (sid_attack),
        .sustain            (sid_sustain),
        .waveform           (sid_waveform),
        .accumulator_msb_in (1'b0),
        .voice              (voice_out),
        .accumulator_msb_out()
    );

    //==========================================================================
    // PWM Audio Output (8-bit, ~196 kHz)
    //==========================================================================
    wire pwm_out;

    pwm_audio u_pwm (
        .clk    (clk),
        .rst_n  (rst_n),
        .sample (voice_out),
        .pwm    (pwm_out)
    );

    //==========================================================================
    // Output Pin Mapping
    //==========================================================================
    // uo_out[0] = spi_miso (tied low by spi_regs)
    assign uo_out[7:1] = 7'b0;

    // uio[7] = pwm_out (8-bit PWM audio, output enabled)
    // uio[6:0] = unused (inputs, no drive)
    assign uio_out = {pwm_out, 7'b0};
    assign uio_oe  = 8'h80;

    // Suppress unused input warnings
    wire _unused = &{ena, ui_in[7:3], uio_in, 1'b0};

endmodule
