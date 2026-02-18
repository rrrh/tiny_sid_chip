`timescale 1ns / 1ps
//==============================================================================
// SID Voice — Waveform Generator with ADSR Envelope
//==============================================================================
// Implements a single SID voice with:
//   - 16-bit phase accumulator
//   - Sawtooth, triangle, pulse, and noise waveform generators (combinational)
//   - 8-bit LFSR-based noise generator (free-running)
//   - Waveform output mux (OR-combining, matching real SID behavior)
//   - 8-bit voice output scaled by 4-bit ADSR envelope (12-bit product)
//==============================================================================

module sid_voice #(
    parameter IS_8580 = 0
) (
    input  wire        clk,
    input  wire        rst,

    // Voice input (sid_voice_in_type)
    input  wire [15:0] frequency,
    input  wire [7:0]  duration,
    input  wire [7:0]  attack,
    input  wire [7:0]  sustain,
    input  wire [7:0]  waveform,
    input  wire [22:0] prescaler,
    // Voice output
    output wire [7:0]  voice
);

    //==========================================================================
    // Waveform control bit aliases
    //==========================================================================
    wire test        = waveform[3];
    wire gate        = waveform[0];
    wire triangle_en = waveform[4];
    wire sawtooth_en = waveform[5];
    wire pulse_en    = waveform[6];
    wire noise_en    = waveform[7];

    //==========================================================================
    // Registered state
    //==========================================================================
    reg [15:0] accumulator;
    reg [7:0]  lfsr;

    //==========================================================================
    // ADSR envelope generator
    //==========================================================================
    wire [3:0] adsr_value;

    sid_asdr_generator u_adsr (
        .clk           (clk),
        .rst           (rst),
        .gate          (gate),
        .attack_rate   (attack[3:0]),
        .decay_rate    (attack[7:4]),
        .sustain_value (sustain[3:0]),
        .release_rate  (sustain[7:4]),
        .prescaler     (prescaler),
        .adsr_value    (adsr_value)
    );

    //==========================================================================
    // Combinational waveform generation (derived from accumulator/LFSR)
    //==========================================================================
    wire [7:0] saw_out = accumulator[15:8];

    wire [7:0] tri_tmp = sawtooth_en ? 8'h00 : {8{accumulator[15]}};
    wire [7:0] tri_out = accumulator[14:7] ^ tri_tmp;

    wire       pulse_out = accumulator[15:8] > duration;

    //==========================================================================
    // Output mux and envelope scaling
    //==========================================================================
    reg [11:0] voice_tmp;
    reg [7:0]  voice_mux;

    always @(*) begin
        voice_mux = 8'h00;
        if (triangle_en)
            voice_mux = voice_mux | tri_out;
        if (sawtooth_en)
            voice_mux = voice_mux | saw_out;
        if (pulse_en)
            voice_mux = voice_mux | {8{pulse_out}};
        if (noise_en)
            voice_mux = voice_mux | lfsr;

        voice_tmp = voice_mux * adsr_value;

        if (rst)
            voice_tmp = 12'b0;
    end

    //==========================================================================
    // Sequential process
    //==========================================================================
    always @(posedge clk) begin
        if (rst) begin
            accumulator <= 16'd0;
            lfsr        <= 8'b00000001;
        end else if (test) begin
            accumulator <= 16'd0;
            lfsr        <= 8'b00000001;
        end else begin
            accumulator <= accumulator + frequency;
            lfsr        <= {lfsr[6:0], lfsr[3] ^ lfsr[7]};
        end
    end

    //==========================================================================
    // Output assignments
    //==========================================================================
    assign voice = voice_tmp[11:4];

endmodule
