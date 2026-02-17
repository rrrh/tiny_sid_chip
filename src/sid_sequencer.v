`timescale 1ns / 1ps
//==============================================================================
// SID Drum + Bass Sequencer — Boom-Bap Beat with Bassline
//==============================================================================
// 16-step pattern at ~89 BPM (2^23 clocks/step at 50 MHz).
//
// V1 (full voice): ALL drums — kick (saw), snare (noise), hi-hat (noise)
// V2 (voice 2):    Bassline  — sawtooth, C minor pentatonic
//
// Drum pattern: K.H.S.H.K..KHS.H.  (steps 0-15)
// Bass pattern: C..C...G..C.B...   (C2, G1, Bb1)
//
// Both voices can sound simultaneously — bass sustains under drum hits.
//==============================================================================

module sid_sequencer (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,      // unused — kept for port compatibility

    // Voice 1 outputs (drums — full voice)
    output wire [15:0] frequency,
    output wire [7:0]  duration,
    output wire [7:0]  attack,
    output wire [7:0]  sustain,
    output wire [7:0]  waveform,

    // Voice 2 outputs (bassline)
    output wire [7:0]  v2_attack,
    output wire [7:0]  v2_sustain,
    output wire        v2_gate,
    output wire [6:0]  v2_frequency
);

    //==========================================================================
    // Timing: 2^23 clocks/step ≈ 167.8 ms ≈ 89.4 BPM (16th notes)
    //==========================================================================
    reg [22:0] prescaler;   // 23 FFs
    reg [3:0]  step;        // 4 FFs
    reg        gate_on;     // 1 FF — V1 drums
    reg        v2_gate_on;  // 1 FF — V2 bass

    //==========================================================================
    // Drum pattern ROM: 0=rest, 1=kick, 2=snare, 3=hi-hat
    //==========================================================================
    //                               step: FEDCBA9876543210
    wire [15:0] PAT_HI = 16'b0101_1000_0101_0100;  // drum_type[1]
    wire [15:0] PAT_LO = 16'b0100_1100_1100_0101;  // drum_type[0]
    wire [1:0] drum_type = {PAT_HI[step], PAT_LO[step]};

    //==========================================================================
    // Bass pattern ROM: 0=rest, 1=C2, 2=G1, 3=Bb1
    // Pattern: C..C...G..C.B...
    //==========================================================================
    //                                step: FEDCBA9876543210
    wire [15:0] BASS_HI = 16'b0001_0000_1000_0000;  // bass_type[1]
    wire [15:0] BASS_LO = 16'b0001_0100_0000_1001;  // bass_type[0]
    wire [1:0] bass_type = {BASS_HI[step], BASS_LO[step]};

    //==========================================================================
    // Sequencer state machine
    //==========================================================================
    always @(posedge clk) begin
        if (rst) begin
            prescaler  <= 23'd0;
            step       <= 4'd0;
            gate_on    <= 1'b0;
            v2_gate_on <= 1'b0;
        end else begin
            prescaler <= prescaler + 1'b1;

            // V1 drum gate off at ~21 ms (short percussive gate)
            if (gate_on && prescaler[20])
                gate_on <= 1'b0;

            // V2 bass gate off at ~84 ms (longer sustained gate)
            if (v2_gate_on && prescaler[22])
                v2_gate_on <= 1'b0;

            // Step advance at prescaler wrap
            if (&prescaler) begin
                step <= step + 1'b1;
                // V1 gate: any drum hit
                gate_on    <= |{PAT_HI[step + 1'b1], PAT_LO[step + 1'b1]};
                // V2 gate: any bass note
                v2_gate_on <= |{BASS_HI[step + 1'b1], BASS_LO[step + 1'b1]};
            end
        end
    end

    //==========================================================================
    // Drum type decoding
    //==========================================================================
    wire is_kick  = ~drum_type[1] & drum_type[0];
    wire is_snare =  drum_type[1] & ~drum_type[0];
    wire is_hihat =  drum_type[1] & drum_type[0];
    wire is_active = |drum_type;

    //==========================================================================
    // V1 outputs: ALL drums (time-shared, original SID style)
    //   kick: saw waveform, freq=32, fast attack, medium decay
    //   snare: noise, freq=2048, fast attack, short decay
    //   hihat: noise, freq=4096, fast attack, very short decay
    //==========================================================================
    assign frequency = {3'b0, is_hihat, is_snare, 5'b0, is_kick, 5'b0};
    assign duration  = {is_active, 7'b0};
    assign attack    = {1'b0, is_kick, is_snare, is_hihat, 4'b0};
    assign sustain   = {4'b0, is_snare, 3'b0};
    assign waveform  = {drum_type[1], 1'b0, is_kick, 4'b0, gate_on & is_active};

    //==========================================================================
    // V2 outputs: bassline (sawtooth, C minor pentatonic)
    //   C2 ≈ 65 Hz: freq = 22  (22 * 50e6/2^24 = 65.6 Hz)
    //   G1 ≈ 49 Hz: freq = 17  (17 * 50e6/2^24 = 50.7 Hz)
    //   Bb1≈ 58 Hz: freq = 20  (20 * 50e6/2^24 = 59.6 Hz)
    //==========================================================================
    reg [6:0] bass_freq;
    always @(*) begin
        case (bass_type)
            2'd1:    bass_freq = 7'd22;   // C2
            2'd2:    bass_freq = 7'd17;   // ~G1
            2'd3:    bass_freq = 7'd20;   // ~Bb1
            default: bass_freq = 7'd22;   // hold C2 on rest steps
        endcase
    end

    assign v2_frequency = bass_freq;
    assign v2_gate      = v2_gate_on;
    // Bass ADSR: instant attack, medium decay, moderate sustain, slow release
    assign v2_attack    = 8'h40;                           // decay=4, attack=0
    assign v2_sustain   = 8'h76;                           // release=7, sustain=6

    wire _unused = enable;

endmodule
