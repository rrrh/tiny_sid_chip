`timescale 1ns / 1ps
//==============================================================================
// TT10 Wrapper — SID Voice Synthesizer (2 Voices)
//==============================================================================
// Instantiates:
//   - spi_regs:          SPI slave → write-only register bank (16-bit frames)
//   - sid_sequencer:     Built-in drum+bass pattern (V1=drums, V2=bassline)
//   - sid_voice:         V1 — full SID voice (saw/tri/pulse/noise + ADSR)
//   - sid_noise_voice:   V2 — noise/saw voice (LFSR or saw + ADSR)
//   - pwm_audio:         8-bit PWM audio output (255-clock period, ~196 kHz)
//
// SPI Protocol (CPOL=0, CPHA=0, MSB first):
//   16-bit write frame: [15:13]=addr[2:0]  [12:8]=reserved  [7:0]=data
//   Registers: 0=freq_lo, 1=freq_hi, 2=pw_lo, 3=v2_attack,
//              4=attack, 5=sustain, 6=waveform, 7=v2_gate_freq
//
// Pin Mapping:
//   ui_in[0]    = spi_cs_n      ui_in[3]   = seq_enable (1=sequencer, 0=SPI)
//   ui_in[1]    = spi_clk       ui_in[7:4] = unused
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
    wire seq_enable  = ui_in[3];

    wire rst = !rst_n;

    //==========================================================================
    // Shared 16-bit ADSR prescaler
    //==========================================================================
    reg [15:0] prescaler;
    always @(posedge clk) begin
        if (rst)
            prescaler <= 16'd0;
        else
            prescaler <= prescaler + 1'b1;
    end

    //==========================================================================
    // SPI Register Bank (write-only)
    //==========================================================================
    wire [15:0] sid_frequency;
    wire [7:0]  sid_duration;
    wire [7:0]  sid_attack;
    wire [7:0]  sid_sustain;
    wire [7:0]  sid_waveform;
    wire [7:0]  spi_v2_attack;
    wire [7:0]  spi_v2_gate_freq;

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
        .sid_waveform  (sid_waveform),
        .v2_attack     (spi_v2_attack),
        .v2_gate_freq  (spi_v2_gate_freq)
    );

    //==========================================================================
    // Drum + Bass Sequencer
    //==========================================================================
    wire [15:0] seq_frequency;
    wire [7:0]  seq_duration;
    wire [7:0]  seq_attack;
    wire [7:0]  seq_sustain;
    wire [7:0]  seq_waveform;
    wire [7:0]  seq_v2_attack;
    wire [7:0]  seq_v2_sustain;
    wire        seq_v2_gate;
    wire [6:0]  seq_v2_frequency;
    wire        seq_v2_noise_en;

    sid_sequencer u_seq (
        .clk          (clk),
        .rst          (rst),
        .enable       (seq_enable),
        .frequency    (seq_frequency),
        .duration     (seq_duration),
        .attack       (seq_attack),
        .sustain      (seq_sustain),
        .waveform     (seq_waveform),
        .v2_attack    (seq_v2_attack),
        .v2_sustain   (seq_v2_sustain),
        .v2_gate      (seq_v2_gate),
        .v2_frequency (seq_v2_frequency),
        .v2_noise_en  (seq_v2_noise_en)
    );

    //==========================================================================
    // V1 Source mux: ui_in[3] selects sequencer (1) or SPI (0)
    //==========================================================================
    wire [15:0] voice_frequency = seq_enable ? seq_frequency : sid_frequency;
    wire [7:0]  voice_duration  = seq_enable ? seq_duration  : sid_duration;
    wire [7:0]  voice_attack    = seq_enable ? seq_attack    : sid_attack;
    wire [7:0]  voice_sustain   = seq_enable ? seq_sustain   : sid_sustain;
    wire [7:0]  voice_waveform  = seq_enable ? seq_waveform  : sid_waveform;

    //==========================================================================
    // V2 Source mux: same seq_enable control
    //==========================================================================
    wire [3:0]  v2_attack_rate   = seq_enable ? seq_v2_attack[3:0]     : spi_v2_attack[3:0];
    wire [3:0]  v2_decay_rate    = seq_enable ? seq_v2_attack[7:4]     : spi_v2_attack[7:4];
    wire [3:0]  v2_sustain_value = seq_enable ? seq_v2_sustain[3:0]    : 4'd0;
    wire [3:0]  v2_release_rate  = seq_enable ? seq_v2_sustain[7:4]    : 4'd1;
    wire        v2_gate          = seq_enable ? seq_v2_gate             : spi_v2_gate_freq[0];
    wire [6:0]  v2_frequency     = seq_enable ? seq_v2_frequency        : spi_v2_gate_freq[7:1];
    wire        v2_noise_en      = seq_enable ? seq_v2_noise_en         : 1'b1;

    //==========================================================================
    // V1: SID Voice (full voice with shared prescaler)
    //==========================================================================
    wire [7:0] v1_out;

    sid_voice #(.IS_8580(0)) u_voice (
        .clk                (clk),
        .rst                (rst),
        .frequency          (voice_frequency),
        .duration           (voice_duration),
        .attack             (voice_attack),
        .sustain            (voice_sustain),
        .waveform           (voice_waveform),
        .accumulator_msb_in (1'b0),
        .prescaler          (prescaler),
        .voice              (v1_out),
        .accumulator_msb_out()
    );

    //==========================================================================
    // V2: Noise Voice (noise-only with shared prescaler)
    //==========================================================================
    wire [7:0] v2_out;

    sid_noise_voice u_noise_voice (
        .clk           (clk),
        .rst           (rst),
        .frequency     (v2_frequency),
        .attack_rate   (v2_attack_rate),
        .decay_rate    (v2_decay_rate),
        .sustain_value (v2_sustain_value),
        .release_rate  (v2_release_rate),
        .gate          (v2_gate),
        .noise_en      (v2_noise_en),
        .prescaler     (prescaler),
        .voice         (v2_out)
    );

    //==========================================================================
    // Voice Mixer: (V1 + V2) >> 1
    //==========================================================================
    wire [8:0] mix = {1'b0, v1_out} + {1'b0, v2_out};
    wire [7:0] mixed = mix[8:1];

    //==========================================================================
    // PWM Audio Output (8-bit, ~196 kHz)
    //==========================================================================
    wire pwm_out;

    pwm_audio u_pwm (
        .clk    (clk),
        .rst_n  (rst_n),
        .sample (mixed),
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
    wire _unused = &{ena, ui_in[7:4], uio_in, 1'b0};

endmodule
