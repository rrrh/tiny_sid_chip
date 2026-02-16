`timescale 1ns / 1ps
//==============================================================================
// SID Drum Sequencer — Minimal Boom-Bap Beat
//==============================================================================
// 16-step pattern at ~89 BPM (2^23 clocks/step at 50 MHz).
// Outputs SID voice register values directly — no SPI overhead.
//
// Pattern: K.H.S.H.K..KHS.H.
//   K = kick (triangle ~80 Hz, 42ms gate)
//   S = snare (noise, 21ms gate)
//   H = hi-hat (high-freq noise, 10ms gate)
//
// Resources: 29 FFs, ~minimal combinational logic.
// Gate timing uses prescaler bit thresholds (zero comparator cost).
//==============================================================================

module sid_sequencer (
    input  wire        clk,
    input  wire        rst,
    input  wire        enable,

    output reg  [15:0] frequency,
    output reg  [7:0]  duration,
    output reg  [7:0]  attack,
    output reg  [7:0]  sustain,
    output reg  [7:0]  waveform
);

    //==========================================================================
    // Timing: 2^23 clocks/step ≈ 167.8 ms ≈ 89.4 BPM (16th notes)
    //==========================================================================
    reg [22:0] prescaler;   // 23 FFs — free-running, wraps at 2^23
    reg [3:0]  step;        // 4 FFs  — auto-wraps at 16
    reg        gate_on;     // 1 FF
    reg        step_start;  // 1 FF   — triggers gate one cycle after step advance

    //==========================================================================
    // Pattern ROM: 0 = rest, 1 = kick, 2 = snare, 3 = hi-hat
    //==========================================================================
    reg [1:0] drum_type;
    always @(*) begin
        case (step)
            4'd0:    drum_type = 2'd1;  // Kick
            4'd2:    drum_type = 2'd3;  // Hi-hat
            4'd4:    drum_type = 2'd2;  // Snare
            4'd6:    drum_type = 2'd3;  // Hi-hat
            4'd7:    drum_type = 2'd1;  // Kick
            4'd10:   drum_type = 2'd1;  // Kick
            4'd11:   drum_type = 2'd3;  // Hi-hat
            4'd12:   drum_type = 2'd2;  // Snare
            4'd14:   drum_type = 2'd3;  // Hi-hat
            default: drum_type = 2'd0;  // Rest
        endcase
    end

    //==========================================================================
    // Sequencer state machine
    //==========================================================================
    always @(posedge clk) begin
        if (rst) begin
            prescaler  <= 23'd0;
            step       <= 4'd0;
            gate_on    <= 1'b0;
            step_start <= 1'b0;
        end else if (enable) begin
            prescaler  <= prescaler + 1'b1;
            step_start <= 1'b0;

            // Gate off at threshold (lower priority — overridden by step_start)
            if (gate_on) begin
                case (drum_type)
                    2'd1:    if (prescaler[21]) gate_on <= 1'b0;  // ~42 ms
                    2'd2:    if (prescaler[20]) gate_on <= 1'b0;  // ~21 ms
                    2'd3:    if (prescaler[19]) gate_on <= 1'b0;  // ~10 ms
                    default: gate_on <= 1'b0;
                endcase
            end

            // Step advance at prescaler wrap (higher priority)
            if (&prescaler) begin
                step       <= step + 1'b1;
                step_start <= 1'b1;
            end

            // Gate on one cycle after step advance (drum_type now valid)
            if (step_start && drum_type != 2'd0)
                gate_on <= 1'b1;
        end
    end

    //==========================================================================
    // Drum parameter output (combinational)
    //==========================================================================
    always @(*) begin
        case (drum_type)
            2'd1: begin  // Kick — triangle ~80 Hz
                frequency = 16'd27;
                duration  = 8'h80;
                attack    = 8'h40;   // atk=0 (instant), dec=4 (~42 ms)
                sustain   = 8'h00;   // sus=0, rel=0
                waveform  = {7'b0010000, gate_on};  // triangle + gate
            end
            2'd2: begin  // Snare — noise
                frequency = 16'd1678;
                duration  = 8'h80;
                attack    = 8'h30;   // atk=0, dec=3 (~21 ms)
                sustain   = 8'h10;   // sus=0, rel=1 (~5 ms)
                waveform  = {7'b1000000, gate_on};  // noise + gate
            end
            2'd3: begin  // Hi-hat — high-freq noise
                frequency = 16'd4027;
                duration  = 8'h80;
                attack    = 8'h10;   // atk=0, dec=1 (~5 ms)
                sustain   = 8'h00;   // sus=0, rel=0
                waveform  = {7'b1000000, gate_on};  // noise + gate
            end
            default: begin  // Rest
                frequency = 16'd0;
                duration  = 8'h00;
                attack    = 8'h00;
                sustain   = 8'h00;
                waveform  = 8'h00;
            end
        endcase
    end

endmodule
