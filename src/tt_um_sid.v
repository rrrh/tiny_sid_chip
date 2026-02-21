`timescale 1ns / 1ps
//==============================================================================
// TT10 Wrapper — Triple SID Voice Synthesizer (Time-Multiplexed)
//==============================================================================
// Uses one shared compute pipeline cycling through 3 voices each clock.
// Each voice is updated every 3rd clock cycle at 5 MHz = 1.667 MHz/voice.
//
// 18-bit phase accumulators with 16-bit frequency registers:
//   Effective rate = 5 MHz / 3 = 1.667 MHz per voice
//   Resolution = 1.667 MHz / 2^18 ≈ 6.36 Hz per step
//   freq_reg = desired_Hz * 2^18 / 1666667 ≈ desired_Hz * 0.1573
//
// Flat Memory-Mapped Register Interface:
//   ui_in[2:0]  = register address (3-bit)
//   ui_in[4:3]  = voice select (0=voice1, 1=voice2, 2=voice3)
//   ui_in[7]    = write enable (active high, rising-edge triggered)
//   ui_in[6:5]  = unused
//   uio[7:0]    = data input (all inputs, directly driven by controller)
//   uo_out[0]   = pwm_out (8-bit PWM audio output)
//   uo_out[7:1] = 0
//
// Register Map (per voice):
//   0: freq_lo  — frequency[7:0]
//   1: freq_hi  — frequency[15:8]
//   2: pw       — pulse width[7:0]
//   3: (reserved)
//   4: attack   — attack_rate[3:0] / decay_rate[7:4]  (per-voice)
//   5: sustain  — sustain_level[3:0] / release_rate[7:4]  (per-voice)
//   6: waveform — waveform[7:0]
//
// Mixing: accumulate 3 voice outputs over 3 clocks, shift right by 2.
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

    wire rst = !rst_n;

    //==========================================================================
    // Write enable edge detection
    //==========================================================================
    reg wr_en_d;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) wr_en_d <= 1'b0;
        else        wr_en_d <= wr_en;
    wire wr_en_rise = wr_en && !wr_en_d;

    //==========================================================================
    // Voice 1 register bank (frequency, duration, waveform, attack, sustain)
    //==========================================================================
    reg [15:0] v1_frequency;
    reg [7:0]  v1_duration;
    reg [7:0]  v1_waveform;
    reg [7:0]  v1_attack, v1_sustain;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v1_frequency <= 0; v1_duration <= 0; v1_waveform <= 0;
            v1_attack <= 0; v1_sustain <= 0;
        end else if (wr_en_rise && voice_sel == 2'd0) begin
            case (reg_addr)
                3'd0: v1_frequency[7:0]  <= wr_data;
                3'd1: v1_frequency[15:8] <= wr_data;
                3'd2: v1_duration        <= wr_data;
                3'd4: v1_attack          <= wr_data;
                3'd5: v1_sustain         <= wr_data;
                3'd6: v1_waveform        <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Voice 2 register bank
    //==========================================================================
    reg [15:0] v2_frequency;
    reg [7:0]  v2_duration;
    reg [7:0]  v2_waveform;
    reg [7:0]  v2_attack, v2_sustain;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v2_frequency <= 0; v2_duration <= 0; v2_waveform <= 0;
            v2_attack <= 0; v2_sustain <= 0;
        end else if (wr_en_rise && voice_sel == 2'd1) begin
            case (reg_addr)
                3'd0: v2_frequency[7:0]  <= wr_data;
                3'd1: v2_frequency[15:8] <= wr_data;
                3'd2: v2_duration        <= wr_data;
                3'd4: v2_attack          <= wr_data;
                3'd5: v2_sustain         <= wr_data;
                3'd6: v2_waveform        <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Voice 3 register bank
    //==========================================================================
    reg [15:0] v3_frequency;
    reg [7:0]  v3_duration;
    reg [7:0]  v3_waveform;
    reg [7:0]  v3_attack, v3_sustain;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v3_frequency <= 0; v3_duration <= 0; v3_waveform <= 0;
            v3_attack <= 0; v3_sustain <= 0;
        end else if (wr_en_rise && voice_sel == 2'd2) begin
            case (reg_addr)
                3'd0: v3_frequency[7:0]  <= wr_data;
                3'd1: v3_frequency[15:8] <= wr_data;
                3'd2: v3_duration        <= wr_data;
                3'd4: v3_attack          <= wr_data;
                3'd5: v3_sustain         <= wr_data;
                3'd6: v3_waveform        <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Shared ADSR prescaler (free-running 18-bit counter)
    //==========================================================================
    reg [17:0] adsr_prescaler;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) adsr_prescaler <= 18'd0;
        else        adsr_prescaler <= adsr_prescaler + 1'b1;

    //==========================================================================
    // Voice round-robin counter: 0 → 1 → 2 → 0 → ...
    //==========================================================================
    reg [1:0] vidx;
    always @(posedge clk or negedge rst_n)
        if (!rst_n)          vidx <= 2'd0;
        else if (vidx == 2'd2) vidx <= 2'd0;
        else                 vidx <= vidx + 1'b1;

    //==========================================================================
    // Mux current voice registers based on vidx
    //==========================================================================
    reg [15:0] cur_frequency;
    reg [7:0]  cur_duration, cur_waveform;
    reg [7:0]  cur_attack, cur_sustain;

    always @(*) begin
        case (vidx)
            2'd0: begin
                cur_frequency = v1_frequency; cur_duration = v1_duration;
                cur_waveform = v1_waveform;
                cur_attack = v1_attack; cur_sustain = v1_sustain;
            end
            2'd1: begin
                cur_frequency = v2_frequency; cur_duration = v2_duration;
                cur_waveform = v2_waveform;
                cur_attack = v2_attack; cur_sustain = v2_sustain;
            end
            default: begin
                cur_frequency = v3_frequency; cur_duration = v3_duration;
                cur_waveform = v3_waveform;
                cur_attack = v3_attack; cur_sustain = v3_sustain;
            end
        endcase
    end

    //==========================================================================
    // Waveform control bit aliases (from current voice)
    //==========================================================================
    wire cur_test        = cur_waveform[3];
    wire cur_gate        = cur_waveform[0];
    wire cur_triangle_en = cur_waveform[4];
    wire cur_sawtooth_en = cur_waveform[5];
    wire cur_pulse_en    = cur_waveform[6];
    wire cur_noise_en    = cur_waveform[7];

    //==========================================================================
    // Per-voice state banks
    //==========================================================================
    // Phase accumulator (18-bit) per voice + shared LFSR (8-bit)
    reg [17:0] v_acc_0,  v_acc_1,  v_acc_2;
    reg [7:0]  shared_lfsr;

    // ADSR state: env_counter (4-bit), state (2-bit), last_gate (1-bit)
    reg [3:0]  v_env_0,  v_env_1,  v_env_2;
    reg [1:0]  v_ast_0,  v_ast_1,  v_ast_2;
    reg        v_lg_0,   v_lg_1,   v_lg_2;

    //==========================================================================
    // Mux current voice state based on vidx
    //==========================================================================
    reg [17:0] cur_acc;
    wire [7:0] cur_lfsr = shared_lfsr;
    reg [3:0]  cur_env;
    reg [1:0]  cur_ast;
    reg        cur_lg;

    always @(*) begin
        case (vidx)
            2'd0: begin
                cur_acc = v_acc_0;
                cur_env = v_env_0; cur_ast = v_ast_0; cur_lg = v_lg_0;
            end
            2'd1: begin
                cur_acc = v_acc_1;
                cur_env = v_env_1; cur_ast = v_ast_1; cur_lg = v_lg_1;
            end
            default: begin
                cur_acc = v_acc_2;
                cur_env = v_env_2; cur_ast = v_ast_2; cur_lg = v_lg_2;
            end
        endcase
    end

    //==========================================================================
    // Shared combinational: waveform generation (18-bit accumulator)
    //==========================================================================
    wire [7:0] saw_out = cur_acc[17:10];
    wire [7:0] tri_tmp = cur_sawtooth_en ? 8'h00 : {8{cur_acc[17]}};
    wire [7:0] tri_out = cur_acc[16:9] ^ tri_tmp;
    wire       pulse_out = cur_acc[17:10] > cur_duration;

    //==========================================================================
    // Shared combinational: ADSR envelope tick + next state
    //==========================================================================
    localparam [1:0] ENV_IDLE    = 2'd0,
                     ENV_ATTACK  = 2'd1,
                     ENV_DECAY   = 2'd2,
                     ENV_RELEASE = 2'd3;

    // Rate selection
    reg [3:0] active_rate;
    always @(*) begin
        case (cur_ast)
            ENV_ATTACK:  active_rate = cur_attack[3:0];
            ENV_DECAY:   active_rate = cur_attack[7:4];
            ENV_RELEASE: active_rate = cur_sustain[7:4];
            default:     active_rate = 4'd0;
        endcase
    end

    // Envelope tick from prescaler
    // At 5 MHz: rate 0 → tick every 64 clk (3.3 ms full traverse)
    //           rate 12 → tick every 262144 clk (13.4 s full traverse)
    //           rates 13-15 alias to rate 12
    reg env_tick;
    always @(*) begin
        case (active_rate)
            4'd0:  env_tick = &adsr_prescaler[5:0];
            4'd1:  env_tick = &adsr_prescaler[6:0];
            4'd2:  env_tick = &adsr_prescaler[7:0];
            4'd3:  env_tick = &adsr_prescaler[8:0];
            4'd4:  env_tick = &adsr_prescaler[9:0];
            4'd5:  env_tick = &adsr_prescaler[10:0];
            4'd6:  env_tick = &adsr_prescaler[11:0];
            4'd7:  env_tick = &adsr_prescaler[12:0];
            4'd8:  env_tick = &adsr_prescaler[13:0];
            4'd9:  env_tick = &adsr_prescaler[14:0];
            4'd10: env_tick = &adsr_prescaler[15:0];
            4'd11: env_tick = &adsr_prescaler[16:0];
            4'd12: env_tick = &adsr_prescaler[17:0];
            4'd13: env_tick = &adsr_prescaler[17:0];
            4'd14: env_tick = &adsr_prescaler[17:0];
            default: env_tick = &adsr_prescaler[17:0];
        endcase
    end

    wire [3:0] sustain_level = cur_sustain[3:0];

    // Compute next ADSR state + env_counter
    reg [1:0] nxt_ast;
    reg [3:0] nxt_env;

    always @(*) begin
        nxt_ast = cur_ast;
        nxt_env = cur_env;

        case (cur_ast)
            ENV_IDLE: begin
                nxt_env = 4'd0;
                if (cur_gate && !cur_lg)
                    nxt_ast = ENV_ATTACK;
            end
            ENV_ATTACK: begin
                if (!cur_gate) begin
                    nxt_ast = ENV_RELEASE;
                end else if (cur_env == 4'hF) begin
                    nxt_ast = ENV_DECAY;
                end else if (env_tick) begin
                    nxt_env = cur_env + 1'b1;
                end
            end
            ENV_DECAY: begin
                if (!cur_gate) begin
                    nxt_ast = ENV_RELEASE;
                end else if (cur_env > sustain_level && env_tick) begin
                    nxt_env = cur_env - 1'b1;
                end
            end
            ENV_RELEASE: begin
                if (cur_gate && !cur_lg) begin
                    nxt_ast = ENV_ATTACK;
                end else if (cur_env == 4'd0) begin
                    nxt_ast = ENV_IDLE;
                end else if (env_tick) begin
                    nxt_env = cur_env - 1'b1;
                end
            end
        endcase
    end

    //==========================================================================
    // Shared combinational: waveform mux + envelope scaling
    //==========================================================================
    reg [7:0]  voice_mux;
    reg [11:0] voice_out;

    always @(*) begin
        voice_mux = 8'h00;
        if (cur_triangle_en) voice_mux = voice_mux | tri_out;
        if (cur_sawtooth_en) voice_mux = voice_mux | saw_out;
        if (cur_pulse_en)    voice_mux = voice_mux | {8{pulse_out}};
        if (cur_noise_en)    voice_mux = voice_mux | cur_lfsr;

        voice_out = voice_mux * cur_env;

        if (rst) voice_out = 12'b0;
    end

    //==========================================================================
    // Next accumulator + LFSR
    //==========================================================================
    wire [17:0] nxt_acc  = cur_test ? 18'd0 :
                           (cur_acc + {2'd0, cur_frequency});

    wire [7:0]  nxt_lfsr = {shared_lfsr[6:0], shared_lfsr[7] ^ shared_lfsr[5] ^ shared_lfsr[4] ^ shared_lfsr[3]};

    //==========================================================================
    // Sequential: update state banks for current voice + shared LFSR
    //==========================================================================
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v_acc_0 <= 18'd0; v_acc_1 <= 18'd0; v_acc_2 <= 18'd0;
            shared_lfsr <= 8'd1;
            v_env_0 <= 4'd0; v_env_1 <= 4'd0; v_env_2 <= 4'd0;
            v_ast_0 <= ENV_IDLE; v_ast_1 <= ENV_IDLE; v_ast_2 <= ENV_IDLE;
            v_lg_0 <= 1'b0; v_lg_1 <= 1'b0; v_lg_2 <= 1'b0;
        end else begin
            shared_lfsr <= nxt_lfsr;
            case (vidx)
                2'd0: begin
                    v_acc_0  <= nxt_acc;
                    v_env_0  <= nxt_env;  v_ast_0  <= nxt_ast;
                    v_lg_0   <= cur_gate;
                end
                2'd1: begin
                    v_acc_1  <= nxt_acc;
                    v_env_1  <= nxt_env;  v_ast_1  <= nxt_ast;
                    v_lg_1   <= cur_gate;
                end
                default: begin
                    v_acc_2  <= nxt_acc;
                    v_env_2  <= nxt_env;  v_ast_2  <= nxt_ast;
                    v_lg_2   <= cur_gate;
                end
            endcase
        end
    end

    //==========================================================================
    // Mix: accumulate voice outputs over 3 cycles, latch every 3rd
    //==========================================================================
    reg [9:0] mix_acc;
    reg [7:0] mix_out;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            mix_acc <= 10'd0;
            mix_out <= 8'd0;
        end else begin
            if (vidx == 2'd0) begin
                mix_out <= mix_acc[9:2];
                mix_acc <= {2'b0, voice_out[11:4]};
            end else begin
                mix_acc <= mix_acc + {2'b0, voice_out[11:4]};
            end
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
    assign uio_oe  = 8'b0;  // all inputs

    // Suppress unused input warnings
    wire _unused = &{ena, ui_in[6:5], 1'b0};

endmodule
