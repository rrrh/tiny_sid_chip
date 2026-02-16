`timescale 1ns / 1ps
//==============================================================================
// SID Voice — Waveform Generator with ADSR Envelope
//==============================================================================
// Single SID voice with:
//   - 24-bit phase accumulator
//   - Combinational sawtooth, triangle, pulse, noise waveform generators
//   - LFSR-based noise generator (16-bit)
//   - Waveform output mux (OR-combining, matching real SID behavior)
//   - 8-bit voice output scaled by 8-bit ADSR envelope
//==============================================================================

module sid_voice #(
    parameter IS_8580 = 0
) (
    input  wire        clk,
    input  wire        rst,

    input  wire [15:0] frequency,
    input  wire [7:0]  duration,
    input  wire [7:0]  attack,
    input  wire [7:0]  sustain,
    input  wire [7:0]  waveform,
    input  wire        accumulator_msb_in,

    output wire [7:0]  voice,
    output wire        accumulator_msb_out
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
    // Registered state (accumulator + LFSR only)
    //==========================================================================
    reg [23:0] accumulator;
    reg [15:0] lfsr;
    reg        lfsr_clk_prev;

    //==========================================================================
    // ADSR envelope generator
    //==========================================================================
    wire [7:0] adsr_value;

    sid_asdr_generator u_adsr (
        .clk           (clk),
        .rst           (rst),
        .gate          (gate),
        .attack_rate   (attack[3:0]),
        .decay_rate    (attack[7:4]),
        .sustain_value (sustain[3:0]),
        .release_rate  (sustain[7:4]),
        .adsr_value    (adsr_value)
    );

    //==========================================================================
    // Combinational waveform generation (no pipeline registers)
    //==========================================================================
    // Triangle: XOR fold with MSB (suppressed when sawtooth also enabled)
    wire [7:0] tri_xor = sawtooth_en ? 8'h00 : {8{accumulator[23]}};
    wire [7:0] tri_wave = accumulator[22:15] ^ tri_xor;

    // Pulse: comparator against duration (pulse width)
    wire pulse_wave = accumulator[23:16] > duration;

    // Waveform output mux (OR-combining like real SID)
    reg [7:0]  voice_mux;
    always @(*) begin
        voice_mux = 8'h00;
        if (triangle_en) voice_mux = voice_mux | tri_wave;
        if (sawtooth_en) voice_mux = voice_mux | accumulator[23:16];
        if (pulse_en)    voice_mux = voice_mux | {8{pulse_wave}};
        if (noise_en)    voice_mux = voice_mux | lfsr[15:8];
    end

    // Scale by ADSR envelope
    wire [15:0] voice_tmp = voice_mux * adsr_value;
    assign voice = voice_tmp[15:8];
    assign accumulator_msb_out = accumulator[23];

    //==========================================================================
    // Sequential: accumulator + LFSR
    //==========================================================================
    always @(posedge clk) begin
        if (rst || test) begin
            accumulator   <= 24'd0;
            lfsr          <= 16'h0001;
            lfsr_clk_prev <= 1'b0;
        end else begin
            accumulator <= accumulator + {8'b0, frequency};

            // LFSR clocked by accumulator bit 19 edge
            lfsr_clk_prev <= accumulator[19];
            if (lfsr_clk_prev != accumulator[19])
                lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
        end
    end

    wire _unused = &{IS_8580, waveform[2:1], accumulator_msb_in, 1'b0};

endmodule
