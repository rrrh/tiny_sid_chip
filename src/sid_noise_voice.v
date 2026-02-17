`timescale 1ns / 1ps
//==============================================================================
// SID Voice 2 — Sawtooth with ADSR Envelope
//==============================================================================
// Minimal second voice for bassline:
//   - 16-bit accumulator (prescaler-gated for low frequencies)
//   - ADSR envelope with shared prescaler
//   - Logarithmic barrel shifter (same as sid_voice)
//
// Frequency formula: f = freq × (clk/256) / 2^16 ≈ freq × 2.98 Hz @ 50 MHz
//   freq=22 → 65.6 Hz (C2), freq=17 → 50.7 Hz (G1), freq=20 → 59.6 Hz (Bb1)
//==============================================================================

module sid_noise_voice (
    input  wire        clk,
    input  wire        rst,
    input  wire [6:0]  frequency,      // 7-bit phase increment
    input  wire [3:0]  attack_rate,
    input  wire [3:0]  decay_rate,
    input  wire [3:0]  sustain_value,
    input  wire [3:0]  release_rate,
    input  wire        gate,
    input  wire [15:0] prescaler,      // shared with V1
    output wire [7:0]  voice
);

    //==========================================================================
    // 16-bit accumulator — prescaler-gated for bass frequencies
    // Increments every 256 clocks (when &prescaler[7:0])
    //==========================================================================
    reg [15:0] accumulator;

    always @(posedge clk) begin
        if (rst)
            accumulator <= 16'd0;
        else if (&prescaler[7:0])
            accumulator <= accumulator + {9'b0, frequency};
    end

    //==========================================================================
    // ADSR envelope
    //==========================================================================
    wire [7:0] adsr_value;

    sid_asdr_generator u_adsr (
        .clk           (clk),
        .rst           (rst),
        .gate          (gate),
        .attack_rate   (attack_rate),
        .decay_rate    (decay_rate),
        .sustain_value (sustain_value),
        .release_rate  (release_rate),
        .prescaler     (prescaler),
        .adsr_value    (adsr_value)
    );

    //==========================================================================
    // Sawtooth waveform from accumulator MSBs
    //==========================================================================
    wire [7:0] wave_out = accumulator[15:8];

    //==========================================================================
    // Logarithmic barrel shifter — same as sid_voice
    //==========================================================================
    reg [2:0] shift_amt;
    always @(*) begin
        casez (adsr_value[7:1])
            7'b1??????: shift_amt = 3'd0;
            7'b01?????: shift_amt = 3'd1;
            7'b001????: shift_amt = 3'd2;
            7'b0001???: shift_amt = 3'd3;
            7'b00001??: shift_amt = 3'd4;
            7'b000001?: shift_amt = 3'd5;
            7'b0000001: shift_amt = 3'd6;
            default:    shift_amt = 3'd7;
        endcase
    end

    assign voice = (adsr_value[7:1] == 7'd0) ? 8'd0 : (wave_out >> shift_amt);

endmodule
