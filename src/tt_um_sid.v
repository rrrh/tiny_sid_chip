`timescale 1ns / 1ps
//==============================================================================
// TT10 Wrapper — Triple SID Voice Synthesizer (Fully Parallel)
//==============================================================================
// Three independent voice pipelines compute every clock cycle at 5 MHz.
// No time-multiplexing mux — eliminates vidx-related hold violations.
//
// 20-bit phase accumulators with 16-bit frequency registers:
//   Effective rate = 5 MHz per voice
//   Resolution = 5 MHz / 2^20 ≈ 4.77 Hz per step
//   freq_reg = desired_Hz * 2^20 / 5e6 ≈ desired_Hz * 0.2097
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
//   3: volume   — [7:4]=global volume  (shared)
//   4: attack   — attack_rate[3:0] / decay_rate[7:4]  (per voice)
//   5: sustain  — sustain_level[3:0] / release_rate[7:4]  (per voice)
//   6: waveform — waveform[7:0]
//   7: (reserved)
//
// Mixing: all 3 voice outputs summed in parallel each clock.
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
    // Voice 1 register bank
    //==========================================================================
    reg [15:0] v1_frequency;
    reg [7:0]  v1_duration, v1_waveform, v1_attack, v1_sustain;

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
    reg [7:0]  v2_duration, v2_waveform, v2_attack, v2_sustain;

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
    reg [7:0]  v3_duration, v3_waveform, v3_attack, v3_sustain;

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
    // Global volume register (shared, written via reg 3 from any voice)
    //==========================================================================
    reg [3:0] global_vol;
    always @(posedge clk or negedge rst_n)
        if (!rst_n)                              global_vol <= 4'hF;
        else if (wr_en_rise && reg_addr == 3'd3) global_vol <= wr_data[7:4];

    //==========================================================================
    // Shared ADSR prescaler (free-running 18-bit counter)
    //==========================================================================
    reg [17:0] adsr_prescaler;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) adsr_prescaler <= 18'd0;
        else        adsr_prescaler <= adsr_prescaler + 1'b1;

    //==========================================================================
    // Shared LFSR (8-bit maximal-length)
    //==========================================================================
    reg [7:0] shared_lfsr;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) shared_lfsr <= 8'd1;
        else        shared_lfsr <= {shared_lfsr[6:0],
                                    shared_lfsr[7] ^ shared_lfsr[5] ^
                                    shared_lfsr[4] ^ shared_lfsr[3]};

    //==========================================================================
    // ADSR parameters
    //==========================================================================
    localparam [1:0] ENV_IDLE    = 2'd0,
                     ENV_ATTACK  = 2'd1,
                     ENV_DECAY   = 2'd2,
                     ENV_RELEASE = 2'd3;

    //==========================================================================
    // Envelope tick from prescaler (shared, rate-selected per voice)
    //==========================================================================
    function env_tick_fn;
        input [3:0] rate;
        input [17:0] pre;
        begin
            case (rate)
                4'd0:    env_tick_fn = &pre[5:0];
                4'd1:    env_tick_fn = &pre[6:0];
                4'd2:    env_tick_fn = &pre[7:0];
                4'd3:    env_tick_fn = &pre[8:0];
                4'd4:    env_tick_fn = &pre[9:0];
                4'd5:    env_tick_fn = &pre[10:0];
                4'd6:    env_tick_fn = &pre[11:0];
                4'd7:    env_tick_fn = &pre[12:0];
                4'd8:    env_tick_fn = &pre[13:0];
                4'd9:    env_tick_fn = &pre[14:0];
                4'd10:   env_tick_fn = &pre[15:0];
                4'd11:   env_tick_fn = &pre[16:0];
                4'd12:   env_tick_fn = &pre[17:0];
                default: env_tick_fn = &pre[17:0];
            endcase
        end
    endfunction

    //==========================================================================
    // Voice compute function: waveform + ADSR → 8-bit output
    //==========================================================================
    // Voice 1
    reg [19:0] v1_acc;
    reg [3:0]  v1_env;
    reg [1:0]  v1_ast;
    reg        v1_lg;

    wire [7:0] v1_saw = v1_acc[19:12];
    wire [7:0] v1_tri_tmp = v1_waveform[5] ? 8'h00 : {8{v1_acc[19]}};
    wire [7:0] v1_tri = v1_acc[18:11] ^ v1_tri_tmp;
    wire       v1_pulse = v1_acc[19:12] > v1_duration;

    reg [7:0]  v1_wave;
    always @(*) begin
        v1_wave = 8'h00;
        if (v1_waveform[4]) v1_wave = v1_wave | v1_tri;
        if (v1_waveform[5]) v1_wave = v1_wave | v1_saw;
        if (v1_waveform[6]) v1_wave = v1_wave | {8{v1_pulse}};
        if (v1_waveform[7]) v1_wave = v1_wave | shared_lfsr;
    end

    wire [11:0] v1_out = rst ? 12'd0 : (v1_wave * v1_env);

    // ADSR for voice 1
    reg [3:0] v1_active_rate;
    always @(*) begin
        case (v1_ast)
            ENV_ATTACK:  v1_active_rate = v1_attack[3:0];
            ENV_DECAY:   v1_active_rate = v1_attack[7:4];
            ENV_RELEASE: v1_active_rate = v1_sustain[7:4];
            default:     v1_active_rate = 4'd0;
        endcase
    end

    wire v1_tick = env_tick_fn(v1_active_rate, adsr_prescaler);
    wire v1_gate = v1_waveform[0];
    wire [3:0] v1_sus_lvl = v1_sustain[3:0];

    reg [1:0] v1_nxt_ast;
    reg [3:0] v1_nxt_env;
    always @(*) begin
        v1_nxt_ast = v1_ast; v1_nxt_env = v1_env;
        case (v1_ast)
            ENV_IDLE: begin
                v1_nxt_env = 4'd0;
                if (v1_gate && !v1_lg) v1_nxt_ast = ENV_ATTACK;
            end
            ENV_ATTACK: begin
                if (!v1_gate) v1_nxt_ast = ENV_RELEASE;
                else if (v1_env == 4'hF) v1_nxt_ast = ENV_DECAY;
                else if (v1_tick) v1_nxt_env = v1_env + 1'b1;
            end
            ENV_DECAY: begin
                if (!v1_gate) v1_nxt_ast = ENV_RELEASE;
                else if (v1_env > v1_sus_lvl && v1_tick) v1_nxt_env = v1_env - 1'b1;
            end
            ENV_RELEASE: begin
                if (v1_gate && !v1_lg) v1_nxt_ast = ENV_ATTACK;
                else if (v1_env == 4'd0) v1_nxt_ast = ENV_IDLE;
                else if (v1_tick) v1_nxt_env = v1_env - 1'b1;
            end
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v1_acc <= 20'd0; v1_env <= 4'd0; v1_ast <= ENV_IDLE; v1_lg <= 1'b0;
        end else begin
            v1_acc <= v1_waveform[3] ? 20'd0 : (v1_acc + {4'd0, v1_frequency});
            v1_env <= v1_nxt_env; v1_ast <= v1_nxt_ast; v1_lg <= v1_gate;
        end
    end

    //==========================================================================
    // Voice 2
    //==========================================================================
    reg [19:0] v2_acc;
    reg [3:0]  v2_env;
    reg [1:0]  v2_ast;
    reg        v2_lg;

    wire [7:0] v2_saw = v2_acc[19:12];
    wire [7:0] v2_tri_tmp = v2_waveform[5] ? 8'h00 : {8{v2_acc[19]}};
    wire [7:0] v2_tri = v2_acc[18:11] ^ v2_tri_tmp;
    wire       v2_pulse = v2_acc[19:12] > v2_duration;

    reg [7:0]  v2_wave;
    always @(*) begin
        v2_wave = 8'h00;
        if (v2_waveform[4]) v2_wave = v2_wave | v2_tri;
        if (v2_waveform[5]) v2_wave = v2_wave | v2_saw;
        if (v2_waveform[6]) v2_wave = v2_wave | {8{v2_pulse}};
        if (v2_waveform[7]) v2_wave = v2_wave | shared_lfsr;
    end

    wire [11:0] v2_out = rst ? 12'd0 : (v2_wave * v2_env);

    reg [3:0] v2_active_rate;
    always @(*) begin
        case (v2_ast)
            ENV_ATTACK:  v2_active_rate = v2_attack[3:0];
            ENV_DECAY:   v2_active_rate = v2_attack[7:4];
            ENV_RELEASE: v2_active_rate = v2_sustain[7:4];
            default:     v2_active_rate = 4'd0;
        endcase
    end

    wire v2_tick = env_tick_fn(v2_active_rate, adsr_prescaler);
    wire v2_gate = v2_waveform[0];
    wire [3:0] v2_sus_lvl = v2_sustain[3:0];

    reg [1:0] v2_nxt_ast;
    reg [3:0] v2_nxt_env;
    always @(*) begin
        v2_nxt_ast = v2_ast; v2_nxt_env = v2_env;
        case (v2_ast)
            ENV_IDLE: begin
                v2_nxt_env = 4'd0;
                if (v2_gate && !v2_lg) v2_nxt_ast = ENV_ATTACK;
            end
            ENV_ATTACK: begin
                if (!v2_gate) v2_nxt_ast = ENV_RELEASE;
                else if (v2_env == 4'hF) v2_nxt_ast = ENV_DECAY;
                else if (v2_tick) v2_nxt_env = v2_env + 1'b1;
            end
            ENV_DECAY: begin
                if (!v2_gate) v2_nxt_ast = ENV_RELEASE;
                else if (v2_env > v2_sus_lvl && v2_tick) v2_nxt_env = v2_env - 1'b1;
            end
            ENV_RELEASE: begin
                if (v2_gate && !v2_lg) v2_nxt_ast = ENV_ATTACK;
                else if (v2_env == 4'd0) v2_nxt_ast = ENV_IDLE;
                else if (v2_tick) v2_nxt_env = v2_env - 1'b1;
            end
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v2_acc <= 20'd0; v2_env <= 4'd0; v2_ast <= ENV_IDLE; v2_lg <= 1'b0;
        end else begin
            v2_acc <= v2_waveform[3] ? 20'd0 : (v2_acc + {4'd0, v2_frequency});
            v2_env <= v2_nxt_env; v2_ast <= v2_nxt_ast; v2_lg <= v2_gate;
        end
    end

    //==========================================================================
    // Voice 3
    //==========================================================================
    reg [19:0] v3_acc;
    reg [3:0]  v3_env;
    reg [1:0]  v3_ast;
    reg        v3_lg;

    wire [7:0] v3_saw = v3_acc[19:12];
    wire [7:0] v3_tri_tmp = v3_waveform[5] ? 8'h00 : {8{v3_acc[19]}};
    wire [7:0] v3_tri = v3_acc[18:11] ^ v3_tri_tmp;
    wire       v3_pulse = v3_acc[19:12] > v3_duration;

    reg [7:0]  v3_wave;
    always @(*) begin
        v3_wave = 8'h00;
        if (v3_waveform[4]) v3_wave = v3_wave | v3_tri;
        if (v3_waveform[5]) v3_wave = v3_wave | v3_saw;
        if (v3_waveform[6]) v3_wave = v3_wave | {8{v3_pulse}};
        if (v3_waveform[7]) v3_wave = v3_wave | shared_lfsr;
    end

    wire [11:0] v3_out = rst ? 12'd0 : (v3_wave * v3_env);

    reg [3:0] v3_active_rate;
    always @(*) begin
        case (v3_ast)
            ENV_ATTACK:  v3_active_rate = v3_attack[3:0];
            ENV_DECAY:   v3_active_rate = v3_attack[7:4];
            ENV_RELEASE: v3_active_rate = v3_sustain[7:4];
            default:     v3_active_rate = 4'd0;
        endcase
    end

    wire v3_tick = env_tick_fn(v3_active_rate, adsr_prescaler);
    wire v3_gate = v3_waveform[0];
    wire [3:0] v3_sus_lvl = v3_sustain[3:0];

    reg [1:0] v3_nxt_ast;
    reg [3:0] v3_nxt_env;
    always @(*) begin
        v3_nxt_ast = v3_ast; v3_nxt_env = v3_env;
        case (v3_ast)
            ENV_IDLE: begin
                v3_nxt_env = 4'd0;
                if (v3_gate && !v3_lg) v3_nxt_ast = ENV_ATTACK;
            end
            ENV_ATTACK: begin
                if (!v3_gate) v3_nxt_ast = ENV_RELEASE;
                else if (v3_env == 4'hF) v3_nxt_ast = ENV_DECAY;
                else if (v3_tick) v3_nxt_env = v3_env + 1'b1;
            end
            ENV_DECAY: begin
                if (!v3_gate) v3_nxt_ast = ENV_RELEASE;
                else if (v3_env > v3_sus_lvl && v3_tick) v3_nxt_env = v3_env - 1'b1;
            end
            ENV_RELEASE: begin
                if (v3_gate && !v3_lg) v3_nxt_ast = ENV_ATTACK;
                else if (v3_env == 4'd0) v3_nxt_ast = ENV_IDLE;
                else if (v3_tick) v3_nxt_env = v3_env - 1'b1;
            end
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v3_acc <= 20'd0; v3_env <= 4'd0; v3_ast <= ENV_IDLE; v3_lg <= 1'b0;
        end else begin
            v3_acc <= v3_waveform[3] ? 20'd0 : (v3_acc + {4'd0, v3_frequency});
            v3_env <= v3_nxt_env; v3_ast <= v3_nxt_ast; v3_lg <= v3_gate;
        end
    end

    //==========================================================================
    // Parallel mix: sum all 3 voice outputs in one clock
    //==========================================================================
    wire [9:0] mix_sum = {2'b0, v1_out[11:4]} + {2'b0, v2_out[11:4]}
                       + {2'b0, v3_out[11:4]};

    reg [7:0] mix_out;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) mix_out <= 8'd0;
        else        mix_out <= mix_sum[9:2];

    //==========================================================================
    // Global volume control (feedforward, no feedback)
    //==========================================================================
    wire [11:0] vol_scaled = mix_out * global_vol;
    wire [7:0]  final_sample = vol_scaled[11:4];

    //==========================================================================
    // PWM Audio Output (8-bit, ~19.6 kHz at 5 MHz)
    //==========================================================================
    wire pwm_out;

    pwm_audio u_pwm (
        .clk    (clk),
        .rst_n  (rst_n),
        .sample (final_sample),
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
