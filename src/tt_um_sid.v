/* verilator lint_off UNUSEDSIGNAL */
`timescale 1ns / 1ps
//==============================================================================
// TT10 Wrapper — Time-Multiplexed SID Voice Synthesizer (24 MHz, 3 voices)
//==============================================================================
// 24 MHz system clock, 6 MHz voice pipeline (÷4 clock enable).
// Pipeline register stage between voice mux read and combinatorial datapath
// eliminates most hold violations (~200 buffers → ~10-30).
//
// Slot scheduling (mod-6 counter, gated by clk_en_6m):
//   Slot 4: Latch mix output, Load Voice 0 → p_regs
//   Slot 5: Idle (p_regs hold Voice 0)
//   Slot 0: Compute Voice 0, Load Voice 1 → p_regs
//   Slot 1: Compute Voice 1, Load Voice 2 → p_regs
//   Slot 2: Compute Voice 2 (no load needed)
//   Slot 3: Idle
// Each voice accumulator updates once per 6-clock frame → 1 MHz effective.
//
// Yannes-aligned enhancements:
//   1. 8-bit envelope (256 levels, 48 dB dynamic range)
//   2. Per-voice ADSR parameters (attack, sustain, pulse width)
//   3. Exponential decay (rate adjustment based on envelope thresholds)
//   4. Explicit SUSTAIN state in 4-state envelope FSM (IDLE/ATTACK/DECAY/SUSTAIN)
//   5. Accumulator-clocked 15-bit LFSR (pitch-tracking noise from voice 0)
//   6. Sync modulation (hard sync, circular: V0←V2, V1←V0, V2←V1)
//   7. Ring modulation (XOR other voice MSB into triangle)
//   8. Test bit (zeros accumulator)
//
// Register Map (voice_sel 0–2: per-voice, voice_sel 3: global filter):
//   Per-voice (voice_sel 0–2):
//     0: freq_lo  — frequency[7:0]
//     1: freq_hi  — frequency[15:8]
//     2: pw_lo    — pulse width[7:0]
//     3: pw_hi    — pulse width[11:8] (bits [3:0] only)
//     4: attack   — attack[3:0]/decay[7:4]
//     5: sustain  — sustain[3:0]/rel[7:4]
//     6: waveform — SID-compatible layout
//   Filter (voice_sel 3):
//     0: fc_lo    — cutoff low [7:0] (fc_hi:fc_lo[2:0] → filt_fc[10:7] → DAC)  ($D415)
//     1: fc_hi    — cutoff high [7:0]                                            ($D416)
//     2: res_filt — [7:4] resonance → Q bias DAC, [3:0] filt enable             ($D417)
//     3: mode_vol — [6:4] mode (HP/BP/LP), [3:0] vol                            ($D418)
//
//   Analog signal chain: mix → R-2R DAC → SC SVF → SAR ADC → vol scaling
//   SC clock divider + C_Q array driven from register bank (flat memory, no SPI)
//
// Waveform register (SID $d404 layout):
//   [0] gate  [1] sync  [2] ring-mod  [3] test
//   [4] tri   [5] saw   [6] pulse     [7] noise
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
    // Clock divider: 24 MHz → 6 MHz clock enable (÷4)
    //==========================================================================
    reg [1:0] clk_div;
    wire clk_en_6m = (clk_div == 2'd3);
    always @(posedge clk or negedge rst_n)
        if (!rst_n) clk_div <= 2'd0;
        else        clk_div <= (clk_div == 2'd3) ? 2'd0 : clk_div + 2'd1;

    //==========================================================================
    // Write enable edge detection
    //==========================================================================
    reg wr_en_d;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) wr_en_d <= 1'b0;
        else        wr_en_d <= wr_en;
    wire wr_en_rise = wr_en && !wr_en_d;

    //==========================================================================
    // Slot counter (mod-6, 3-bit)
    //==========================================================================
    reg [2:0] slot;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) slot <= 3'd0;
        else if (clk_en_6m) slot <= (slot == 3'd5) ? 3'd0 : slot + 3'd1;

    wire voice_active = (slot <= 3'd2);
    wire [1:0] voice_idx = slot[1:0];

    //==========================================================================
    // Per-voice register file (3 voices)
    //==========================================================================
    reg [7:0]  freq        [0:2];
    reg [7:0]  freq_hi     [0:2];
    reg [7:0]  waveform    [0:2];
    reg [7:0]  pw_reg      [0:2];
    reg [3:0]  pw_hi       [0:2];
    reg [7:0]  attack_reg  [0:2];
    reg [7:0]  sustain_reg [0:2];

    reg [23:0] acc        [0:2];
    reg [7:0]  env        [0:2];
    reg [1:0]  ast        [0:2];
    reg        gate_latch [0:2];
    reg        releasing  [0:2];
    reg        prev_msb_d [0:2];

    //--- Filter registers (voice_sel == 3) ---
    reg [7:0] fc_lo;
    reg [7:0] fc_hi;
    reg [7:0] res_filt;
    reg [7:0] mode_vol;

    // Derived filter signals
    wire [10:0] filt_fc   = {fc_hi, fc_lo[2:0]};
    wire [3:0]  filt_res  = res_filt[7:4];
    wire [3:0]  filt_en   = res_filt[3:0];
    wire [3:0]  filt_mode = mode_vol[7:4];
    wire [3:0]  filt_vol  = mode_vol[3:0];

    // Register writes (per-voice and filter)
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            freq[0] <= 8'd0; freq[1] <= 8'd0; freq[2] <= 8'd0;
            freq_hi[0] <= 8'd0; freq_hi[1] <= 8'd0; freq_hi[2] <= 8'd0;
            waveform[0] <= 8'd0; waveform[1] <= 8'd0; waveform[2] <= 8'd0;
            pw_reg[0] <= 8'd0; pw_reg[1] <= 8'd0; pw_reg[2] <= 8'd0;
            pw_hi[0] <= 4'd0; pw_hi[1] <= 4'd0; pw_hi[2] <= 4'd0;
            attack_reg[0] <= 8'd0; attack_reg[1] <= 8'd0; attack_reg[2] <= 8'd0;
            sustain_reg[0] <= 8'd0; sustain_reg[1] <= 8'd0; sustain_reg[2] <= 8'd0;
            fc_lo <= 8'd0;
            fc_hi <= 8'd0;
            res_filt <= 8'd0;
            mode_vol <= 8'd0;
        end else if (wr_en_rise) begin
            case (reg_addr)
                3'd0: if (voice_sel <= 2'd2) freq[voice_sel]        <= wr_data;
                      else                   fc_lo                  <= wr_data;
                3'd1: if (voice_sel <= 2'd2) freq_hi[voice_sel]     <= wr_data;
                      else                   fc_hi                  <= wr_data;
                3'd2: if (voice_sel <= 2'd2) pw_reg[voice_sel]      <= wr_data;
                      else                   res_filt               <= wr_data;
                3'd3: if (voice_sel <= 2'd2) pw_hi[voice_sel]       <= wr_data[3:0];
                      else                   mode_vol               <= wr_data;
                3'd4: if (voice_sel <= 2'd2) attack_reg[voice_sel]  <= wr_data;
                3'd5: if (voice_sel <= 2'd2) sustain_reg[voice_sel] <= wr_data;
                3'd6: if (voice_sel <= 2'd2) waveform[voice_sel]    <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Pipeline registers (~97 FFs, loaded at 6 MHz rate)
    //==========================================================================
    reg [23:0] p_acc;
    reg [23:0] p_freq;
    reg [7:0]  p_waveform;
    reg [11:0] p_pw;
    reg [7:0]  p_env;
    reg [1:0]  p_ast;
    reg        p_gate_latch;
    reg        p_releasing;
    reg [7:0]  p_attack;
    reg [7:0]  p_sustain;
    reg        p_prev_msb_d;

    // Pipeline load logic
    // Load schedule: slot 4→V0, slot 0→V1, slot 1→V2
    wire load_en = (slot <= 3'd1) || (slot == 3'd4);
    wire [1:0] load_voice = (slot == 3'd4) ? 2'd0 :
                            (slot == 3'd0) ? 2'd1 : 2'd2;

    // Sync source prev_msb_d for pipeline load (flattened, no intermediate mux):
    //   slot 4 → load V0 → sync src V2 → prev_msb_d[2]
    //   slot 0 → load V1 → sync src V0 → prev_msb_d[0]
    //   slot 1 → load V2 → sync src V1 → prev_msb_d[1]
    wire p_prev_msb_d_nxt = (slot == 3'd4) ? prev_msb_d[2] :
                            (slot == 3'd0) ? prev_msb_d[0] : prev_msb_d[1];

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            p_acc        <= 24'd0;
            p_freq       <= 24'd0;
            p_waveform   <= 8'd0;
            p_pw         <= 12'd0;
            p_env        <= 8'd0;
            p_ast        <= 2'd0;
            p_gate_latch <= 1'b0;
            p_releasing  <= 1'b0;
            p_attack     <= 8'd0;
            p_sustain    <= 8'd0;
            p_prev_msb_d <= 1'b0;
        end else if (clk_en_6m && load_en) begin
            p_acc        <= acc[load_voice];
            p_freq       <= {8'd0, freq_hi[load_voice], freq[load_voice]};
            p_waveform   <= waveform[load_voice];
            p_pw         <= {pw_hi[load_voice], pw_reg[load_voice]};
            p_env        <= env[load_voice];
            p_ast        <= ast[load_voice];
            p_gate_latch <= gate_latch[load_voice];
            p_releasing  <= releasing[load_voice];
            p_attack     <= attack_reg[load_voice];
            p_sustain    <= sustain_reg[load_voice];
            p_prev_msb_d <= p_prev_msb_d_nxt;
        end
    end

    //==========================================================================
    // ADSR prescaler (14-bit, LSB fixed to 0 — 13 FF + 1 wire)
    // Advances by 7 per mod-6 frame (6×1 + 1 extra on slot 5) so that
    // the prescaler visits all residue classes mod 2^k for every voice,
    // ensuring env_tick fires correctly at all ADSR rates.
    //==========================================================================
    reg [13:1] adsr_pre_hi;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) adsr_pre_hi <= 13'd0;
        else if (clk_en_6m) adsr_pre_hi <= adsr_pre_hi + {12'd0, (slot == 3'd5)} + 1'b1;
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
    // Exponential decay adjustment
    //==========================================================================
    function [3:0] expo_adj;
        input [7:0] e;
        input [3:0] rate;
        reg [4:0] sum;
        begin
            if (e >= 8'd93)
                expo_adj = rate;
            else if (e >= 8'd54) begin
                sum = {1'b0, rate} + 5'd1;
                expo_adj = (sum > 5'd15) ? 4'd15 : sum[3:0];
            end else if (e >= 8'd26) begin
                sum = {1'b0, rate} + 5'd2;
                expo_adj = (sum > 5'd15) ? 4'd15 : sum[3:0];
            end else if (e >= 8'd14) begin
                sum = {1'b0, rate} + 5'd3;
                expo_adj = (sum > 5'd15) ? 4'd15 : sum[3:0];
            end else begin
                sum = {1'b0, rate} + 5'd4;
                expo_adj = (sum > 5'd15) ? 4'd15 : sum[3:0];
            end
        end
    endfunction

    //==========================================================================
    // Shared LFSR — 15-bit, accumulator-clocked from voice 0
    //==========================================================================
    reg [14:0] shared_lfsr;
    reg        noise_clk_d;
    wire       noise_clk = acc[0][19];
    wire       noise_clk_rise = noise_clk && !noise_clk_d;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            shared_lfsr <= 15'h7FFF;
            noise_clk_d <= 1'b0;
        end else begin
            noise_clk_d <= noise_clk;
            if (noise_clk_rise)
                shared_lfsr <= {shared_lfsr[13:0],
                                shared_lfsr[14] ^ shared_lfsr[13]};
        end
    end

    //==========================================================================
    // Single combinatorial voice datapath (reads from pipeline registers)
    //==========================================================================

    // Cross-voice MSB for sync/ring-mod (flattened, circular: V0←V2, V1←V0, V2←V1)
    wire other_msb = (voice_idx == 2'd0) ? acc[2][23] :
                     (voice_idx == 2'd1) ? acc[0][23] : acc[1][23];
    wire sync_trigger = other_msb && !p_prev_msb_d && p_waveform[1];

    // --- Oscillator with test bit and sync ---
    wire [23:0] nxt_acc = p_waveform[3] ? 24'd0 :       // test bit
                          sync_trigger   ? 24'd0 :       // sync
                          p_acc + p_freq;

    // --- Waveform generation ---
    wire [7:0] saw_out = nxt_acc[23:16];

    // Ring-mod: XOR other voice MSB into triangle MSB
    wire ring_msb = p_waveform[2] ? (nxt_acc[23] ^ other_msb) : nxt_acc[23];
    wire [7:0] tri_out = {nxt_acc[22:16] ^ {7{ring_msb}}, 1'b0};

    wire pulse_cmp = nxt_acc[23:12] >= p_pw;

    reg [7:0] wave_out;
    always @(*) begin
        if (!p_waveform[7] && !p_waveform[6] &&
            !p_waveform[5] && !p_waveform[4])
            wave_out = 8'h00;
        else begin
            wave_out = 8'hFF;
            if (p_waveform[4]) wave_out = wave_out & tri_out;
            if (p_waveform[5]) wave_out = wave_out & saw_out;
            if (p_waveform[6]) wave_out = wave_out & {8{pulse_cmp}};
            if (p_waveform[7]) wave_out = wave_out & shared_lfsr[14:7];
        end
    end

    // --- ADSR rate selection with exponential decay ---
    wire [3:0] sustain_level = p_sustain[3:0];
    wire       cur_gate      = p_waveform[0];

    reg [3:0] cur_rate;
    always @(*) begin
        if (p_releasing)
            cur_rate = expo_adj(p_env, p_sustain[7:4]);
        else case (p_ast)
            ENV_ATTACK:  cur_rate = p_attack[3:0];
            ENV_DECAY:   cur_rate = expo_adj(p_env, p_attack[7:4]);
            default:     cur_rate = 4'd0;
        endcase
    end

    wire env_tick = env_tick_fn(cur_rate, adsr_prescaler);

    // --- ADSR next-state logic (8-bit envelope, 4-state FSM) ---
    reg [1:0] nxt_ast;
    reg [7:0] nxt_env;
    reg       nxt_rel;
    always @(*) begin
        nxt_ast = p_ast;
        nxt_env = p_env;
        nxt_rel = p_releasing;
        if (p_releasing) begin
            if (cur_gate && !p_gate_latch) begin
                nxt_rel = 1'b0;
                nxt_ast = ENV_ATTACK;
            end else if (p_env == 8'd0) begin
                nxt_rel = 1'b0;
                nxt_ast = ENV_IDLE;
            end else if (env_tick)
                nxt_env = p_env - 1'b1;
        end else case (p_ast)
            ENV_IDLE: begin
                nxt_env = 8'd0;
                if (cur_gate && !p_gate_latch) nxt_ast = ENV_ATTACK;
            end
            ENV_ATTACK: begin
                if (!cur_gate) nxt_rel = 1'b1;
                else if (p_env == 8'hFF) nxt_ast = ENV_DECAY;
                else if (env_tick) nxt_env = p_env + 1'b1;
            end
            ENV_DECAY: begin
                if (!cur_gate) nxt_rel = 1'b1;
                else if (p_env <= {sustain_level, sustain_level})
                    nxt_ast = ENV_SUSTAIN;
                else if (env_tick) nxt_env = p_env - 1'b1;
            end
            ENV_SUSTAIN: begin
                if (!cur_gate) nxt_rel = 1'b1;
                else if (p_env > {sustain_level, sustain_level} && env_tick)
                    nxt_env = p_env - 1'b1;
                else
                    nxt_env = {sustain_level, sustain_level};
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
            acc[0] <= 24'd0; acc[1] <= 24'd0; acc[2] <= 24'd0;
            env[0] <= 8'd0; env[1] <= 8'd0; env[2] <= 8'd0;
            ast[0] <= ENV_IDLE; ast[1] <= ENV_IDLE; ast[2] <= ENV_IDLE;
            gate_latch[0] <= 1'b0; gate_latch[1] <= 1'b0; gate_latch[2] <= 1'b0;
            releasing[0] <= 1'b0; releasing[1] <= 1'b0; releasing[2] <= 1'b0;
            prev_msb_d[0] <= 1'b0; prev_msb_d[1] <= 1'b0; prev_msb_d[2] <= 1'b0;
        end else if (clk_en_6m && voice_active) begin
            acc[voice_idx]        <= nxt_acc;
            env[voice_idx]        <= nxt_env;
            ast[voice_idx]        <= nxt_ast;
            gate_latch[voice_idx] <= cur_gate;
            releasing[voice_idx]  <= nxt_rel;
            // prev_msb_d write: explicit per-slot (avoids computed array index)
            // V0 (slot 0) stores V2's MSB, V1 (slot 1) stores V0's, V2 (slot 2) stores V1's
            case (slot[1:0])
                2'd0: prev_msb_d[2] <= acc[2][23];
                2'd1: prev_msb_d[0] <= acc[0][23];
                2'd2: prev_msb_d[1] <= acc[1][23];
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Mix accumulation (slots 0-2) and latch (slot 3)
    //==========================================================================
    reg [9:0] mix_acc;
    reg [7:0] mix_out;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mix_acc <= 10'd0;
            mix_out <= 8'd0;
        end else if (clk_en_6m) begin
            case (slot)
                3'd0: mix_acc <= {2'b0, voice_out};
                3'd1: mix_acc <= mix_acc + {2'b0, voice_out};
                3'd2: mix_acc <= mix_acc + {2'b0, voice_out};
                3'd4: begin
                    mix_out <= mix_acc[9:2];
                    mix_acc <= 10'd0;
                end
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Sample-valid strobe: one cycle after slot 4 at 6 MHz rate
    //==========================================================================
    reg sample_valid;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) sample_valid <= 1'b0;
        else        sample_valid <= clk_en_6m && (slot == 3'd4);

    //==========================================================================
    // Analog filter signal chain:
    //   mix_out → R-2R DAC → SC SVF → SAR ADC → volume scaling
    //
    // Register mapping (voice_sel=3, flat memory — no SPI):
    //   fc_lo/fc_hi → filt_fc[10:7] → clock divider LUT → sc_clk
    //   res_filt[3:0] → q0..q3 (C_Q cap array switches, direct)
    //   mode_vol[6:4] → svf_sel[1:0] (HP>BP>LP priority, or bypass)
    //   mode_vol[3:0] → filt_vol     (digital volume scaling post-ADC)
    //==========================================================================
    (* keep *) wire dac_out;           // R-2R DAC analog output
    (* keep *) wire filter_out;        // SVF analog output
    (* keep *) wire sc_clk;            // SC switching clock to SVF

    // Bypass: no voices routed to filter, or no filter mode selected
    wire bypass = (filt_en[2:0] == 3'd0) || (filt_mode[2:0] == 3'd0);

    // SVF mode select: 00=LP, 01=BP, 10=HP, 11=bypass
    wire [1:0] svf_sel = bypass       ? 2'b11 :
                         filt_mode[2] ? 2'b10 :
                         filt_mode[1] ? 2'b01 : 2'b00;

    // --- R-2R DAC: mixer output → analog ---
    r2r_dac_8bit u_dac (
        .d0(mix_out[0]), .d1(mix_out[1]), .d2(mix_out[2]), .d3(mix_out[3]),
        .d4(mix_out[4]), .d5(mix_out[5]), .d6(mix_out[6]), .d7(mix_out[7]),
        .vout (dac_out)
    );

    // --- Programmable clock divider for SC SVF fc tuning ---
    // filt_fc[10:7] selects divider ratio via LUT (16 log-spaced steps)
    // f_clk = 24 MHz / divider → fc ≈ f_clk * C_sw / (2π * C_int)
    // Range: ~250 Hz (code 0, ÷1024) to ~16 kHz (code 15, ÷16)
    reg [10:0] div_ratio;
    always @(*) begin
        case (filt_fc[10:7])
            4'd0:  div_ratio = 11'd1024;  // f_clk ≈ 23.4 kHz → fc ≈ 250 Hz
            4'd1:  div_ratio = 11'd768;   // f_clk ≈ 31.3 kHz → fc ≈ 330 Hz
            4'd2:  div_ratio = 11'd640;   // f_clk ≈ 37.5 kHz → fc ≈ 400 Hz
            4'd3:  div_ratio = 11'd512;   // f_clk ≈ 46.9 kHz → fc ≈ 500 Hz
            4'd4:  div_ratio = 11'd384;   // f_clk ≈ 62.5 kHz → fc ≈ 660 Hz
            4'd5:  div_ratio = 11'd320;   // f_clk ≈ 75.0 kHz → fc ≈ 800 Hz
            4'd6:  div_ratio = 11'd256;   // f_clk ≈ 93.8 kHz → fc ≈ 1.0 kHz
            4'd7:  div_ratio = 11'd192;   // f_clk ≈ 125  kHz → fc ≈ 1.3 kHz
            4'd8:  div_ratio = 11'd128;   // f_clk ≈ 188  kHz → fc ≈ 2.0 kHz
            4'd9:  div_ratio = 11'd96;    // f_clk ≈ 250  kHz → fc ≈ 2.7 kHz
            4'd10: div_ratio = 11'd64;    // f_clk ≈ 375  kHz → fc ≈ 4.0 kHz
            4'd11: div_ratio = 11'd48;    // f_clk ≈ 500  kHz → fc ≈ 5.3 kHz
            4'd12: div_ratio = 11'd32;    // f_clk ≈ 750  kHz → fc ≈ 8.0 kHz
            4'd13: div_ratio = 11'd24;    // f_clk ≈ 1.0  MHz → fc ≈ 10.6 kHz
            4'd14: div_ratio = 11'd20;    // f_clk ≈ 1.2  MHz → fc ≈ 12.7 kHz
            4'd15: div_ratio = 11'd16;    // f_clk ≈ 1.5  MHz → fc ≈ 16.0 kHz
        endcase
    end

    reg [10:0] clk_cnt;
    reg       sc_clk_reg;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            clk_cnt    <= 11'd0;
            sc_clk_reg <= 1'b0;
        end else begin
            if (clk_cnt >= div_ratio - 1'b1) begin
                clk_cnt    <= 11'd0;
                sc_clk_reg <= ~sc_clk_reg;
            end else begin
                clk_cnt <= clk_cnt + 1'b1;
            end
        end
    end
    assign sc_clk = sc_clk_reg;

    // --- Analog SC SVF ---
    svf_2nd u_svf (
        .vin      (dac_out),
        .vout     (filter_out),
        .sel0     (svf_sel[0]),
        .sel1     (svf_sel[1]),
        .sc_clk   (sc_clk),
        .q0       (filt_res[0]),
        .q1       (filt_res[1]),
        .q2       (filt_res[2]),
        .q3       (filt_res[3])
    );

    // --- SAR ADC: analog → digital (continuous conversion) ---
    wire       adc_eoc;
    wire [7:0] adc_dout;
    reg        adc_busy;
    reg        adc_start;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            adc_busy  <= 1'b0;
            adc_start <= 1'b0;
        end else begin
            if (adc_eoc) begin
                adc_busy  <= 1'b0;
                adc_start <= 1'b1;
            end else if (adc_start) begin
                adc_start <= 1'b0;
                adc_busy  <= 1'b1;
            end else if (!adc_busy) begin
                adc_start <= 1'b1;
            end
        end
    end

    sar_adc_8bit u_adc (
        .clk   (clk),
        .rst_n (rst_n),
        .vin   (filter_out),
        .start (adc_start),
        .eoc   (adc_eoc),
        .dout0(adc_dout[0]), .dout1(adc_dout[1]), .dout2(adc_dout[2]), .dout3(adc_dout[3]),
        .dout4(adc_dout[4]), .dout5(adc_dout[5]), .dout6(adc_dout[6]), .dout7(adc_dout[7])
    );

    // --- Behavioral sim: connect 8-bit data between analog macro models ---
`ifdef BEHAVIORAL_SIM
    always @(u_dac.sim_data_out or u_svf.sim_data_out) begin
        u_svf.sim_data_in = u_dac.sim_data_out;
        u_adc.sim_data_in = u_svf.sim_data_out;
    end
`endif

    // --- Volume scaling (shift-add, same as original filter.v) ---
    wire [7:0] scaled = (filt_vol[3] ? {1'b0, adc_dout[7:1]} : 8'd0) +
                        (filt_vol[2] ? {2'b0, adc_dout[7:2]} : 8'd0) +
                        (filt_vol[1] ? {3'b0, adc_dout[7:3]} : 8'd0) +
                        (filt_vol[0] ? {4'b0, adc_dout[7:4]} : 8'd0);

    wire [7:0] filtered_out = bypass ? mix_out : scaled;

    //==========================================================================
    // 6 dB/octave Lowpass (fc ≈ 1244 Hz) before PWM
    //==========================================================================
    wire [7:0] lpf_out;

    output_lpf u_lpf (
        .clk          (clk),
        .rst_n        (rst_n),
        .sample_valid (sample_valid),
        .sample_in    (filtered_out),
        .sample_out   (lpf_out)
    );

    //==========================================================================
    // PWM Audio Output (8-bit, ~94.1 kHz at 24 MHz)
    //==========================================================================
    wire pwm_out;

    pwm_audio u_pwm (
        .clk    (clk),
        .rst_n  (rst_n),
        .sample (lpf_out),
        .pwm    (pwm_out)
    );

    //==========================================================================
    // Output Pin Mapping
    //==========================================================================
    assign uo_out  = {7'b0, pwm_out};
    assign uio_out = 8'b0;
    assign uio_oe  = 8'b0;

    wire _unused = &{ena, ui_in[6:5], adc_busy, filt_fc[6:0], 1'b0};

endmodule
