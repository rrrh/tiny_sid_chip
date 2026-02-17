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
    input  wire [15:0] prescaler,

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
        .prescaler     (prescaler),
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

    // Scale by ADSR envelope — logarithmic barrel shifter (−6 dB/step)
    // adsr_value bit 0 is always 0, so test bits [7:1]
    reg [2:0] shift_amt;
    always @(*) begin
        casez (adsr_value[7:1])
            7'b1??????: shift_amt = 3'd0;  // 128-254 → ×1
            7'b01?????: shift_amt = 3'd1;  // 64-127  → ×0.5
            7'b001????: shift_amt = 3'd2;  // 32-63   → ×0.25
            7'b0001???: shift_amt = 3'd3;  // 16-31   → ×0.125
            7'b00001??: shift_amt = 3'd4;  // 8-15    → ×0.0625
            7'b000001?: shift_amt = 3'd5;  // 4-7     → ×0.03125
            7'b0000001: shift_amt = 3'd6;  // 2-3     → ×0.015625
            default:    shift_amt = 3'd7;  // 0-1     → ×0.0078125
        endcase
    end
    assign voice = (adsr_value[7:1] == 7'd0) ? 8'd0 : (voice_mux >> shift_amt);
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
