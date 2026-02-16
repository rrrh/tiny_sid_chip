`timescale 1ns / 1ps
//==============================================================================
// SID Voice — Waveform Generator with ADSR Envelope
// Converted from sid_voice.vhdl
//==============================================================================
// Implements a single SID voice with:
//   - 24-bit phase accumulator
//   - Sawtooth, triangle, pulse, and noise waveform generators
//   - Ring modulation and hard sync between oscillators
//   - LFSR-based noise generator
//   - Waveform output mux (OR-combining, matching real SID behavior)
//   - 8-bit voice output scaled by 8-bit ADSR envelope (16-bit product)
//
// Record types from sequrga_pkg are flattened into individual port signals.
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
    input  wire        accumulator_msb_in,

    // Voice output (sid_voice_out_type)
    output wire [7:0]  voice,
    output wire        accumulator_msb_out
);

    //==========================================================================
    // Waveform control bit aliases
    //==========================================================================
    wire test        = waveform[3];
    wire ringmod     = waveform[2];
    wire sync        = waveform[1];
    wire gate        = waveform[0];
    wire triangle_en = waveform[4];
    wire sawtooth_en = waveform[5];
    wire pulse_en    = waveform[6];
    wire noise_en    = waveform[7];

    //==========================================================================
    // Registered state
    //==========================================================================
    reg [7:0]  sawtooth;
    reg [7:0]  triangle;
    reg        pulse;
    reg [7:0]  noise;
    reg [23:0] accumulator;
    reg        accumulator_msb_prev;
    reg [15:0] lfsr;
    reg        lfsr_clk_prev;

    //==========================================================================
    // Next-state signals
    //==========================================================================
    reg [7:0]  next_sawtooth;
    reg [7:0]  next_triangle;
    reg        next_pulse;
    reg [7:0]  next_noise;
    reg [23:0] next_accumulator;
    reg        next_accumulator_msb_prev;
    reg [15:0] next_lfsr;
    reg        next_lfsr_clk_prev;

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
    // Combinational process
    //==========================================================================
    reg [7:0]  tmp;
    reg [15:0] voice_tmp;
    reg [7:0]  voice_mux;

    always @(*) begin
        // Default: hold current state
        next_sawtooth           = sawtooth;
        next_triangle           = triangle;
        next_pulse              = pulse;
        next_noise              = noise;
        next_accumulator        = accumulator;
        next_accumulator_msb_prev = accumulator_msb_prev;
        next_lfsr               = lfsr;
        next_lfsr_clk_prev     = lfsr_clk_prev;

        //--------------------------------------------------------------
        // Main accumulator
        //--------------------------------------------------------------
        next_accumulator = accumulator + {8'b0, frequency};

        //--------------------------------------------------------------
        // Sawtooth (uses current registered accumulator)
        //--------------------------------------------------------------
        next_sawtooth = accumulator[23:16];

        //--------------------------------------------------------------
        // Triangle (uses current registered accumulator)
        //--------------------------------------------------------------
        if (!sawtooth_en) begin
            if (ringmod)
                tmp = {8{accumulator_msb_in}};
            else
                tmp = {8{accumulator[23]}};
        end else begin
            // XOR circuit not used when sawtooth is enabled
            tmp = 8'h00;
        end
        next_triangle = accumulator[22:15] ^ tmp;

        //--------------------------------------------------------------
        // Pulse (uses current registered accumulator)
        //--------------------------------------------------------------
        if (accumulator[23:16] > duration)
            next_pulse = 1'b1;
        else
            next_pulse = 1'b0;

        //--------------------------------------------------------------
        // Noise (LFSR, clocked by accumulator bit 19)
        //--------------------------------------------------------------
        if (lfsr_clk_prev != accumulator[19])
            next_lfsr = {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
        next_noise = next_lfsr[15:8];

        //--------------------------------------------------------------
        // Output mux (OR-combining like real SID)
        //--------------------------------------------------------------
        voice_mux = 8'h00;
        if (triangle_en)
            voice_mux = voice_mux | triangle;
        if (sawtooth_en)
            voice_mux = voice_mux | sawtooth;
        if (pulse_en)
            voice_mux = voice_mux | {8{pulse}};
        if (noise_en)
            voice_mux = voice_mux | noise;

        // Scale by ADSR envelope
        voice_tmp = voice_mux * adsr_value;

        //--------------------------------------------------------------
        // Sync and control
        //--------------------------------------------------------------
        next_accumulator_msb_prev = accumulator_msb_in;
        next_lfsr_clk_prev = accumulator[19];

        // Test, sync, or rst resets the accumulator
        if (rst || test ||
            (sync && (next_accumulator_msb_prev != accumulator_msb_in) &&
             !accumulator_msb_in))
        begin
            next_accumulator = 24'b0;
            next_accumulator_msb_prev = 1'b0;
        end

        // Test or rst resets the LFSR
        if (rst || test)
            next_lfsr = 16'b0000000000000001;

        // Rst resets the voice output
        if (rst)
            voice_tmp = 16'b0;
    end

    //==========================================================================
    // Sequential process
    //==========================================================================
    always @(posedge clk) begin
        if (rst) begin
            sawtooth           <= 8'd0;
            triangle           <= 8'd0;
            pulse              <= 1'b0;
            noise              <= 8'd0;
            accumulator        <= 24'd0;
            accumulator_msb_prev <= 1'b0;
            lfsr               <= 16'b0000000000000001;
            lfsr_clk_prev      <= 1'b0;
        end else begin
            sawtooth           <= next_sawtooth;
            triangle           <= next_triangle;
            pulse              <= next_pulse;
            noise              <= next_noise;
            accumulator        <= next_accumulator;
            accumulator_msb_prev <= next_accumulator_msb_prev;
            lfsr               <= next_lfsr;
            lfsr_clk_prev      <= next_lfsr_clk_prev;
        end
    end

    //==========================================================================
    // Output assignments
    //==========================================================================
    assign voice = voice_tmp[15:8];
    assign accumulator_msb_out = accumulator[23];

endmodule
