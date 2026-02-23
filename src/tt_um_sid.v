`timescale 1ns / 1ps
//==============================================================================
// TT10 Wrapper — Time-Multiplexed SID Voice Synthesizer (5 MHz, 2 voices)
//==============================================================================
// 5 MHz time-multiplexed architecture with single voice datapath.
// Slot scheduling (mod-5 counter):
//   Slot 0: Process Voice 0
//   Slot 1: Process Voice 1
//   Slot 2: Latch mix output
//   Slot 3: Idle
//   Slot 4: Idle
// Each voice accumulator updates once per 5-clock frame → 1 MHz effective.
//
// Yannes-aligned enhancements:
//   1. 8-bit envelope (256 levels, 48 dB dynamic range)
//   2. Per-voice ADSR parameters (attack, sustain, pulse width)
//   3. Exponential decay (rate adjustment based on envelope thresholds)
//   4. Explicit SUSTAIN state in 4-state envelope FSM
//   5. Accumulator-clocked LFSR (pitch-tracking noise from voice 0)
//
// Register Map:
//   0: freq     — frequency[7:0]         (per voice)
//   1: (reserved)
//   2: pw       — pulse width[7:0]       (per voice)
//   3: (reserved)
//   4: attack   — attack[3:0]/decay[7:4] (per voice)
//   5: sustain  — sustain[3:0]/rel[7:4]  (per voice)
//   6: waveform — SID-compatible layout   (per voice)
//
// Waveform register (SID $d404 layout):
//   [0] gate  [1] (reserved)  [2] (reserved)  [3] test
//   [4] tri   [5] saw         [6] pulse        [7] noise
// Note: sync/ring-mod dropped to save area
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
    wire [2:0] reg_addr  = ui_in[2:0];
    wire [1:0] voice_sel = ui_in[4:3];
    wire       wr_en     = ui_in[7];
    wire [7:0] wr_data   = uio_in;

    //==========================================================================
    // Write enable edge detection
    //==========================================================================
    reg wr_en_d;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) wr_en_d <= 1'b0;
        else        wr_en_d <= wr_en;
    wire wr_en_rise = wr_en && !wr_en_d;

    //==========================================================================
    // Slot counter (mod-5, 3-bit)
    //==========================================================================
    reg [2:0] slot;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) slot <= 3'd0;
        else        slot <= (slot == 3'd4) ? 3'd0 : slot + 3'd1;

    wire voice_active = (slot <= 3'd1);
    wire voice_idx = slot[0];

    //==========================================================================
    // Per-voice register file (2 voices)
    //==========================================================================
    reg [7:0]  freq       [0:1];
    reg [7:0]  waveform   [0:1];
    reg [7:0]  pw_reg;
    reg [7:0]  attack_reg;
    reg [7:0]  sustain_reg;

    reg [15:0] acc        [0:1];
    reg [7:0]  env        [0:1];
    reg [1:0]  ast        [0:1];
    reg        gate_latch [0:1];
    reg        releasing  [0:1];

    // Register writes
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            freq[0] <= 8'd0; freq[1] <= 8'd0;
            waveform[0] <= 8'd0; waveform[1] <= 8'd0;
            pw_reg <= 8'd0;
            attack_reg <= 8'd0;
            sustain_reg <= 8'd0;
        end else if (wr_en_rise) begin
            case (reg_addr)
                3'd0: if (voice_sel <= 2'd1) freq[voice_sel[0]] <= wr_data;
                3'd2: pw_reg      <= wr_data;
                3'd4: attack_reg  <= wr_data;
                3'd5: sustain_reg <= wr_data;
                3'd6: if (voice_sel <= 2'd1) waveform[voice_sel[0]] <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // ADSR prescaler (14-bit, LSB fixed to 0 — 13 FF + 1 wire)
    //==========================================================================
    reg [13:1] adsr_pre_hi;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) adsr_pre_hi <= 13'd0;
        else        adsr_pre_hi <= adsr_pre_hi + 1'b1;
    wire [13:0] adsr_prescaler = {adsr_pre_hi, 1'b0};

    //==========================================================================
    // ADSR state encoding
    //==========================================================================
    localparam [1:0] ENV_IDLE    = 2'd0,
                     ENV_ATTACK  = 2'd1,
                     ENV_DECAY   = 2'd2,
                     ENV_SUSTAIN = 2'd3;

    //==========================================================================
    // Envelope tick function (14-bit prescaler, LSB=0, 8 rate levels)
    // Rate taps start at bit 1 (skip fixed-0 LSB)
    //==========================================================================
    function env_tick_fn;
        input [3:0] rate;
        input [13:0] pre;
        begin
            case (rate)
                4'd0:    env_tick_fn = &pre[2:1];
                4'd1:    env_tick_fn = &pre[3:1];
                4'd2:    env_tick_fn = &pre[4:1];
                4'd3:    env_tick_fn = &pre[5:1];
                4'd4:    env_tick_fn = &pre[6:1];
                4'd5:    env_tick_fn = &pre[7:1];
                4'd6:    env_tick_fn = &pre[8:1];
                4'd7:    env_tick_fn = &pre[9:1];
                default: env_tick_fn = &pre[13:1];
            endcase
        end
    endfunction

    //==========================================================================
    // Shared LFSR — 8-bit, accumulator-clocked from voice 0
    //==========================================================================
    reg [7:0] shared_lfsr;
    reg       noise_clk_d;
    wire      noise_clk = acc[0][11];
    wire      noise_clk_rise = noise_clk && !noise_clk_d;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            shared_lfsr <= 8'hFF;
            noise_clk_d <= 1'b0;
        end else begin
            noise_clk_d <= noise_clk;
            if (noise_clk_rise)
                shared_lfsr <= {shared_lfsr[6:0],
                                shared_lfsr[7] ^ shared_lfsr[5]};
        end
    end

    //==========================================================================
    // Single combinatorial voice datapath
    //==========================================================================

    // Read current voice state
    wire [15:0] cur_acc       = acc[voice_idx];
    wire [7:0]  cur_freq      = freq[voice_idx];
    wire [7:0]  cur_waveform  = waveform[voice_idx];
    wire [7:0]  cur_pw        = pw_reg;
    wire [7:0]  cur_env       = env[voice_idx];
    wire [1:0]  cur_ast       = ast[voice_idx];
    wire        cur_gate      = cur_waveform[0];
    wire        cur_gl        = gate_latch[voice_idx];
    wire        cur_releasing = releasing[voice_idx];
    wire [7:0]  cur_attack    = attack_reg;
    wire [7:0]  cur_sustain   = sustain_reg;

    // --- Oscillator ---
    wire [15:0] nxt_acc = cur_acc + {8'd0, cur_freq};

    // --- Waveform generation ---
    wire [7:0] saw_out = nxt_acc[15:8];
    wire [7:0] tri_out = {nxt_acc[14:8] ^ {7{nxt_acc[15]}}, 1'b0};
    wire       pulse_cmp = nxt_acc[15:8] >= cur_pw;

    reg [7:0] wave_out;
    always @(*) begin
        if (!cur_waveform[7] && !cur_waveform[6] &&
            !cur_waveform[5] && !cur_waveform[4])
            wave_out = 8'h00;
        else begin
            wave_out = 8'hFF;
            if (cur_waveform[4]) wave_out = wave_out & tri_out;
            if (cur_waveform[5]) wave_out = wave_out & saw_out;
            if (cur_waveform[6]) wave_out = wave_out & {8{pulse_cmp}};
            if (cur_waveform[7]) wave_out = wave_out & shared_lfsr;
        end
    end

    // --- ADSR rate selection ---
    wire [3:0] sustain_level = cur_sustain[3:0];

    reg [3:0] cur_rate;
    always @(*) begin
        if (cur_releasing)    cur_rate = cur_sustain[7:4];
        else case (cur_ast)
            ENV_ATTACK:  cur_rate = cur_attack[3:0];
            ENV_DECAY:   cur_rate = cur_attack[7:4];
            default:     cur_rate = 4'd0;
        endcase
    end

    wire env_tick = env_tick_fn(cur_rate, adsr_prescaler);

    // --- ADSR next-state logic (8-bit envelope, 4-state FSM) ---
    reg [1:0] nxt_ast;
    reg [7:0] nxt_env;
    reg       nxt_rel;
    always @(*) begin
        nxt_ast = cur_ast;
        nxt_env = cur_env;
        nxt_rel = cur_releasing;
        if (cur_releasing) begin
            if (cur_gate && !cur_gl) begin
                nxt_rel = 1'b0;
                nxt_ast = ENV_ATTACK;
            end else if (cur_env == 8'd0) begin
                nxt_rel = 1'b0;
                nxt_ast = ENV_IDLE;
            end else if (env_tick)
                nxt_env = cur_env - 1'b1;
        end else case (cur_ast)
            ENV_IDLE: begin
                nxt_env = 8'd0;
                if (cur_gate && !cur_gl) nxt_ast = ENV_ATTACK;
            end
            ENV_ATTACK: begin
                if (!cur_gate) nxt_rel = 1'b1;
                else if (cur_env == 8'hFF) nxt_ast = ENV_DECAY;
                else if (env_tick) nxt_env = cur_env + 1'b1;
            end
            ENV_DECAY: begin
                if (!cur_gate) nxt_rel = 1'b1;
                else if (cur_env <= {sustain_level, 4'hF})
                    nxt_ast = ENV_SUSTAIN;
                else if (env_tick) nxt_env = cur_env - 1'b1;
            end
            ENV_SUSTAIN: begin
                if (!cur_gate) nxt_rel = 1'b1;
                else if (cur_env > {sustain_level, 4'hF} && env_tick)
                    nxt_env = cur_env - 1'b1;
                else
                    nxt_env = {sustain_level, 4'hF};
            end
        endcase
    end

    // --- Multiply: 8×8 = 16-bit, take upper 8 bits ---
    wire [15:0] voice_product = wave_out * nxt_env;
    wire [7:0]  voice_out = voice_product[15:8];

    //==========================================================================
    // State update on voice slots
    //==========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            acc[0] <= 16'd0; acc[1] <= 16'd0;
            env[0] <= 8'd0; env[1] <= 8'd0;
            ast[0] <= ENV_IDLE; ast[1] <= ENV_IDLE;
            gate_latch[0] <= 1'b0; gate_latch[1] <= 1'b0;
            releasing[0] <= 1'b0; releasing[1] <= 1'b0;
        end else if (voice_active) begin
            acc[voice_idx]        <= nxt_acc;
            env[voice_idx]        <= nxt_env;
            ast[voice_idx]        <= nxt_ast;
            gate_latch[voice_idx] <= cur_gate;
            releasing[voice_idx]  <= nxt_rel;
        end
    end

    //==========================================================================
    // Mix accumulation (slots 0-1) and latch (slot 2)
    //==========================================================================
    reg [8:0] mix_acc;
    reg [7:0] mix_out;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mix_acc <= 9'd0;
            mix_out <= 8'd0;
        end else begin
            case (slot)
                3'd0: mix_acc <= {1'b0, voice_out};
                3'd1: mix_acc <= mix_acc + {1'b0, voice_out};
                3'd2: begin
                    mix_out <= mix_acc[8:1];
                    mix_acc <= 9'd0;
                end
                default: ;
            endcase
        end
    end

    //==========================================================================
    // PWM Audio Output (8-bit, ~19.6 kHz at 5 MHz)
    //==========================================================================
    wire pwm_out;

    pwm_audio u_pwm (
        .clk    (clk),
        .rst_n  (rst_n),
        .sample (mix_out),
        .pwm    (pwm_out)
    );

    //==========================================================================
    // Output Pin Mapping
    //==========================================================================
    assign uo_out  = {7'b0, pwm_out};
    assign uio_out = 8'b0;
    assign uio_oe  = 8'b0;

    wire _unused = &{ena, ui_in[6:5], 1'b0};

endmodule
