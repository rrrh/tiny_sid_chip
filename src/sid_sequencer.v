`timescale 1ns / 1ps
//==============================================================================
// SID Drum Sequencer — Minimal Boom-Bap Beat
//==============================================================================
// 16-step pattern at ~89 BPM (2^23 clocks/step at 50 MHz).
// Outputs SID voice register values directly — no SPI overhead.
// Free-running: top-level mux gates output selection.
//
// Pattern: K.H.S.H.K..KHS.H.  (steps 0-15)
//   K = kick (triangle ~95 Hz)
//   S = snare (noise)
//   H = hi-hat (high-freq noise)
//
// Resources: 28 FFs, <200 cells.
// All drum parameters are power-of-2 constants — no mux trees needed.
//==============================================================================

module sid_sequencer (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,      // unused — kept for port compatibility

    output wire [15:0] frequency,
    output wire [7:0]  duration,
    output wire [7:0]  attack,
    output wire [7:0]  sustain,
    output wire [7:0]  waveform
);

    //==========================================================================
    // Timing: 2^23 clocks/step ≈ 167.8 ms ≈ 89.4 BPM (16th notes)
    //==========================================================================
    reg [22:0] prescaler;   // 23 FFs — free-running, wraps at 2^23
    reg [3:0]  step;        // 4 FFs  — auto-wraps at 16
    reg        gate_on;     // 1 FF

    //==========================================================================
    // Pattern ROM: 0 = rest, 1 = kick, 2 = snare, 3 = hi-hat
    // Encoded as two 16-bit constants indexed by step.
    //==========================================================================
    //                               step: FEDCBA9876543210
    wire [15:0] PAT_HI = 16'b0101_1000_0101_0100;  // drum_type[1]: snare|hihat
    wire [15:0] PAT_LO = 16'b0100_1100_1100_0101;  // drum_type[0]: kick|hihat
    wire [1:0] drum_type = {PAT_HI[step], PAT_LO[step]};

    //==========================================================================
    // Sequencer state machine (free-running, no enable gating)
    //==========================================================================
    always @(posedge clk) begin
        if (rst) begin
            prescaler <= 23'd0;
            step      <= 4'd0;
            gate_on   <= 1'b0;
        end else begin
            prescaler <= prescaler + 1'b1;

            // Gate off at ~21 ms threshold
            if (gate_on && prescaler[20])
                gate_on <= 1'b0;

            // Step advance at prescaler wrap → gate on if next step has a drum
            if (&prescaler) begin
                step    <= step + 1'b1;
                gate_on <= |{PAT_HI[step + 1'b1], PAT_LO[step + 1'b1]};
            end
        end
    end

    //==========================================================================
    // Drum parameter output — power-of-2 constants, no mux trees
    //==========================================================================
    wire is_kick  = ~drum_type[1] & drum_type[0];
    wire is_snare =  drum_type[1] & ~drum_type[0];
    wire is_hihat =  drum_type[1] & drum_type[0];
    wire is_active = |drum_type;

    // freq: kick=32(bit5), snare=2048(bit11), hihat=4096(bit12)
    assign frequency = {3'b0, is_hihat, is_snare, 5'b0, is_kick, 5'b0};
    assign duration  = {is_active, 7'b0};
    assign attack    = {1'b0, is_kick, is_snare, is_hihat, 4'b0};
    assign sustain   = {4'b0, is_snare, 3'b0};
    assign waveform  = {drum_type[1], 2'b0, is_kick, 3'b0, gate_on & is_active};

    wire _unused = enable;

endmodule
