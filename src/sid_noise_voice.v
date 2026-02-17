`timescale 1ns / 1ps
//==============================================================================
// SID Voice 2 — Noise or Sawtooth with ADSR Envelope
//==============================================================================
// Minimal second voice supporting two waveform modes:
//   noise_en=1: LFSR noise (snare/hihat percussion)
//   noise_en=0: sawtooth from accumulator (bassline)
//
//   - 24-bit accumulator (phase increment from 7-bit frequency)
//   - 16-bit LFSR (same polynomial as sid_voice)
//   - ADSR envelope with shared prescaler
//   - Logarithmic barrel shifter (same as sid_voice)
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
    input  wire        noise_en,       // 1=noise, 0=sawtooth
    input  wire [15:0] prescaler,      // shared with V1
    output wire [7:0]  voice
);

    //==========================================================================
    // 24-bit accumulator — provides saw waveform & clocks LFSR
    //==========================================================================
    reg [23:0] accumulator;
    reg [15:0] lfsr;
    reg        lfsr_clk_prev;

    always @(posedge clk) begin
        if (rst) begin
            accumulator   <= 24'd0;
            lfsr          <= 16'h0001;
            lfsr_clk_prev <= 1'b0;
        end else begin
            accumulator <= accumulator + {17'b0, frequency};

            // LFSR clocked by accumulator[19] edge
            lfsr_clk_prev <= accumulator[19];
            if (lfsr_clk_prev != accumulator[19])
                lfsr <= {lfsr[14:0], lfsr[15] ^ lfsr[13] ^ lfsr[12] ^ lfsr[10]};
        end
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
    // Waveform select: noise (LFSR) or sawtooth (accumulator)
    //==========================================================================
    wire [7:0] wave_out = noise_en ? lfsr[15:8] : accumulator[23:16];

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
