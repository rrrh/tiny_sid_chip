`timescale 1ns / 1ps
//==============================================================================
// TT10 Wrapper — Triple SID Voice Synthesizer (Parallel, 1 MHz)
//==============================================================================
// Three parallel voice pipelines at 1 MHz, Yannes-authentic features:
//   16-bit phase accumulators, 8-bit frequency registers (zero-extended)
//   23-bit LFSR noise generator (SID-authentic polynomial)
//   Hard sync and ring modulation (circular voice chain)
//   AND-combining waveform selector (like real SID)
//   4-bit ADSR envelope, shared parameters
//
// Register Map:
//   0: freq     — frequency[7:0]  (per voice)
//   1: (reserved)
//   2: pw       — pulse width[7:0]  (per voice)
//   3: (reserved)
//   4: attack   — attack_rate[3:0] / decay_rate[7:4]  (shared)
//   5: sustain  — sustain_level[3:0] / release_rate[7:4]  (shared)
//   6: waveform — SID-compatible layout  (per voice)
//
// Waveform register (SID $d404 layout):
//   [0] gate  [1] sync  [2] ring_mod  [3] test
//   [4] tri   [5] saw   [6] pulse     [7] noise
//
// Sync/Ring mod chain (circular, like real SID):
//   Voice 1 ← Voice 3,  Voice 2 ← Voice 1,  Voice 3 ← Voice 2
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
    reg [7:0] v1_frequency, v1_pw, v1_waveform;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v1_frequency <= 0; v1_pw <= 0; v1_waveform <= 0;
        end else if (wr_en_rise && voice_sel == 2'd0) begin
            case (reg_addr)
                3'd0: v1_frequency <= wr_data;
                3'd2: v1_pw       <= wr_data;
                3'd6: v1_waveform <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Voice 2 register bank
    //==========================================================================
    reg [7:0] v2_frequency, v2_pw, v2_waveform;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v2_frequency <= 0; v2_pw <= 0; v2_waveform <= 0;
        end else if (wr_en_rise && voice_sel == 2'd1) begin
            case (reg_addr)
                3'd0: v2_frequency <= wr_data;
                3'd2: v2_pw       <= wr_data;
                3'd6: v2_waveform <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Voice 3 register bank
    //==========================================================================
    reg [7:0] v3_frequency, v3_pw, v3_waveform;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v3_frequency <= 0; v3_pw <= 0; v3_waveform <= 0;
        end else if (wr_en_rise && voice_sel == 2'd2) begin
            case (reg_addr)
                3'd0: v3_frequency <= wr_data;
                3'd2: v3_pw       <= wr_data;
                3'd6: v3_waveform <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Shared ADSR registers
    //==========================================================================
    reg [7:0] shared_attack, shared_sustain;
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            shared_attack <= 0; shared_sustain <= 0;
        end else if (wr_en_rise) begin
            case (reg_addr)
                3'd4: shared_attack  <= wr_data;
                3'd5: shared_sustain <= wr_data;
                default: ;
            endcase
        end
    end

    //==========================================================================
    // Shared ADSR prescaler (14-bit)
    //==========================================================================
    reg [13:0] adsr_prescaler;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) adsr_prescaler <= 14'd0;
        else        adsr_prescaler <= adsr_prescaler + 1'b1;

    //==========================================================================
    // Shared LFSR — 23-bit (SID-authentic)
    //==========================================================================
    // Feedback taps: bits 17 and 22 (from SID die reverse-engineering)
    //==========================================================================
    reg [22:0] shared_lfsr;
    always @(posedge clk or negedge rst_n)
        if (!rst_n) shared_lfsr <= 23'h7FFFFF;
        else        shared_lfsr <= {shared_lfsr[21:0],
                                    shared_lfsr[22] ^ shared_lfsr[17]};

    //==========================================================================
    // ADSR parameters
    //==========================================================================
    localparam [1:0] ENV_IDLE    = 2'd0,
                     ENV_ATTACK  = 2'd1,
                     ENV_DECAY   = 2'd2,
                     ENV_RELEASE = 2'd3;

    wire [3:0] sustain_level = shared_sustain[3:0];

    //==========================================================================
    // Envelope tick function (14-bit prescaler, 9 rate levels)
    //==========================================================================
    function env_tick_fn;
        input [3:0] rate;
        input [13:0] pre;
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
                default: env_tick_fn = &pre[13:0];
            endcase
        end
    endfunction

    //==========================================================================
    // Waveform bit aliases (SID $d404 layout)
    //==========================================================================
    // [0]=gate [1]=sync [2]=ring_mod [3]=test [4]=tri [5]=saw [6]=pulse [7]=noise

    //==========================================================================
    // Voice 1: oscillator + waveform + ADSR
    //==========================================================================
    reg [15:0] v1_acc;
    reg [3:0]  v1_env;
    reg [1:0]  v1_ast;
    reg        v1_lg;
    reg        v1_prev_msb_d;  // for sync edge detect

    // Sync chain: voice 1 syncs from voice 3
    wire       v1_sync_en  = v1_waveform[1];
    wire       v1_ring_en  = v1_waveform[2];
    wire       v1_test     = v1_waveform[3];
    wire       v1_gate     = v1_waveform[0];

    // Forward declarations for circular chain (v3_acc defined later)
    wire [15:0] v3_acc_w;
    wire        v1_prev_msb = v3_acc_w[15];
    wire        v1_prev_msb_rise = v1_prev_msb && !v1_prev_msb_d;

    // Oscillator
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v1_acc <= 0; v1_prev_msb_d <= 0;
        end else begin
            v1_prev_msb_d <= v1_prev_msb;
            if (v1_test)
                v1_acc <= 16'd0;
            else if (v1_sync_en && v1_prev_msb_rise)
                v1_acc <= 16'd0;
            else
                v1_acc <= v1_acc + {8'd0, v1_frequency};
        end
    end

    // Waveforms (8-bit output)
    wire [7:0] v1_saw = v1_acc[15:8];
    wire       v1_ring_msb = v1_ring_en ? v1_prev_msb : v1_acc[15];
    wire [7:0] v1_tri = {v1_acc[14:8] ^ {7{v1_ring_msb}}, 1'b0};
    wire       v1_pulse_cmp = v1_acc[15:8] >= v1_pw;

    // AND-combining waveform selector (SID-authentic)
    reg [7:0] v1_wave;
    always @(*) begin
        if (!v1_waveform[7] && !v1_waveform[6] && !v1_waveform[5] && !v1_waveform[4])
            v1_wave = 8'h00;
        else begin
            v1_wave = 8'hFF;
            if (v1_waveform[4]) v1_wave = v1_wave & v1_tri;
            if (v1_waveform[5]) v1_wave = v1_wave & v1_saw;
            if (v1_waveform[6]) v1_wave = v1_wave & {8{v1_pulse_cmp}};
            if (v1_waveform[7]) v1_wave = v1_wave & shared_lfsr[22:15];
        end
    end
    wire [11:0] v1_out = rst ? 12'd0 : (v1_wave * v1_env);

    // ADSR voice 1
    reg [3:0] v1_rate;
    always @(*) case (v1_ast)
        ENV_ATTACK:  v1_rate = shared_attack[3:0];
        ENV_DECAY:   v1_rate = shared_attack[7:4];
        ENV_RELEASE: v1_rate = shared_sustain[7:4];
        default:     v1_rate = 4'd0;
    endcase

    wire v1_tick = env_tick_fn(v1_rate, adsr_prescaler);

    reg [1:0] v1_nxt_ast; reg [3:0] v1_nxt_env;
    always @(*) begin
        v1_nxt_ast = v1_ast; v1_nxt_env = v1_env;
        case (v1_ast)
            ENV_IDLE: begin
                v1_nxt_env = 4'd0;
                if (v1_gate && !v1_lg) v1_nxt_ast = ENV_ATTACK;
            end
            ENV_ATTACK:
                if (!v1_gate) v1_nxt_ast = ENV_RELEASE;
                else if (v1_env == 4'hF) v1_nxt_ast = ENV_DECAY;
                else if (v1_tick) v1_nxt_env = v1_env + 1'b1;
            ENV_DECAY:
                if (!v1_gate) v1_nxt_ast = ENV_RELEASE;
                else if (v1_env > sustain_level && v1_tick) v1_nxt_env = v1_env - 1'b1;
            ENV_RELEASE:
                if (v1_gate && !v1_lg) v1_nxt_ast = ENV_ATTACK;
                else if (v1_env == 4'd0) v1_nxt_ast = ENV_IDLE;
                else if (v1_tick) v1_nxt_env = v1_env - 1'b1;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v1_env <= 0; v1_ast <= ENV_IDLE; v1_lg <= 0;
        end else begin
            v1_env <= v1_nxt_env; v1_ast <= v1_nxt_ast; v1_lg <= v1_gate;
        end
    end

    //==========================================================================
    // Voice 2: oscillator + waveform + ADSR
    //==========================================================================
    reg [15:0] v2_acc;
    reg [3:0]  v2_env;
    reg [1:0]  v2_ast;
    reg        v2_lg;
    reg        v2_prev_msb_d;

    // Sync chain: voice 2 syncs from voice 1
    wire       v2_sync_en  = v2_waveform[1];
    wire       v2_ring_en  = v2_waveform[2];
    wire       v2_test     = v2_waveform[3];
    wire       v2_gate     = v2_waveform[0];
    wire       v2_prev_msb = v1_acc[15];
    wire       v2_prev_msb_rise = v2_prev_msb && !v2_prev_msb_d;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v2_acc <= 0; v2_prev_msb_d <= 0;
        end else begin
            v2_prev_msb_d <= v2_prev_msb;
            if (v2_test)
                v2_acc <= 16'd0;
            else if (v2_sync_en && v2_prev_msb_rise)
                v2_acc <= 16'd0;
            else
                v2_acc <= v2_acc + {8'd0, v2_frequency};
        end
    end

    wire [7:0] v2_saw = v2_acc[15:8];
    wire       v2_ring_msb = v2_ring_en ? v2_prev_msb : v2_acc[15];
    wire [7:0] v2_tri = {v2_acc[14:8] ^ {7{v2_ring_msb}}, 1'b0};
    wire       v2_pulse_cmp = v2_acc[15:8] >= v2_pw;

    reg [7:0] v2_wave;
    always @(*) begin
        if (!v2_waveform[7] && !v2_waveform[6] && !v2_waveform[5] && !v2_waveform[4])
            v2_wave = 8'h00;
        else begin
            v2_wave = 8'hFF;
            if (v2_waveform[4]) v2_wave = v2_wave & v2_tri;
            if (v2_waveform[5]) v2_wave = v2_wave & v2_saw;
            if (v2_waveform[6]) v2_wave = v2_wave & {8{v2_pulse_cmp}};
            if (v2_waveform[7]) v2_wave = v2_wave & shared_lfsr[22:15];
        end
    end
    wire [11:0] v2_out = rst ? 12'd0 : (v2_wave * v2_env);

    reg [3:0] v2_rate;
    always @(*) case (v2_ast)
        ENV_ATTACK:  v2_rate = shared_attack[3:0];
        ENV_DECAY:   v2_rate = shared_attack[7:4];
        ENV_RELEASE: v2_rate = shared_sustain[7:4];
        default:     v2_rate = 4'd0;
    endcase

    wire v2_tick = env_tick_fn(v2_rate, adsr_prescaler);

    reg [1:0] v2_nxt_ast; reg [3:0] v2_nxt_env;
    always @(*) begin
        v2_nxt_ast = v2_ast; v2_nxt_env = v2_env;
        case (v2_ast)
            ENV_IDLE: begin
                v2_nxt_env = 4'd0;
                if (v2_gate && !v2_lg) v2_nxt_ast = ENV_ATTACK;
            end
            ENV_ATTACK:
                if (!v2_gate) v2_nxt_ast = ENV_RELEASE;
                else if (v2_env == 4'hF) v2_nxt_ast = ENV_DECAY;
                else if (v2_tick) v2_nxt_env = v2_env + 1'b1;
            ENV_DECAY:
                if (!v2_gate) v2_nxt_ast = ENV_RELEASE;
                else if (v2_env > sustain_level && v2_tick) v2_nxt_env = v2_env - 1'b1;
            ENV_RELEASE:
                if (v2_gate && !v2_lg) v2_nxt_ast = ENV_ATTACK;
                else if (v2_env == 4'd0) v2_nxt_ast = ENV_IDLE;
                else if (v2_tick) v2_nxt_env = v2_env - 1'b1;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v2_env <= 0; v2_ast <= ENV_IDLE; v2_lg <= 0;
        end else begin
            v2_env <= v2_nxt_env; v2_ast <= v2_nxt_ast; v2_lg <= v2_gate;
        end
    end

    //==========================================================================
    // Voice 3: oscillator + waveform + ADSR
    //==========================================================================
    reg [15:0] v3_acc;
    reg [3:0]  v3_env;
    reg [1:0]  v3_ast;
    reg        v3_lg;
    reg        v3_prev_msb_d;

    assign v3_acc_w = v3_acc;  // for voice 1 sync chain

    // Sync chain: voice 3 syncs from voice 2
    wire       v3_sync_en  = v3_waveform[1];
    wire       v3_ring_en  = v3_waveform[2];
    wire       v3_test     = v3_waveform[3];
    wire       v3_gate     = v3_waveform[0];
    wire       v3_prev_msb = v2_acc[15];
    wire       v3_prev_msb_rise = v3_prev_msb && !v3_prev_msb_d;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v3_acc <= 0; v3_prev_msb_d <= 0;
        end else begin
            v3_prev_msb_d <= v3_prev_msb;
            if (v3_test)
                v3_acc <= 16'd0;
            else if (v3_sync_en && v3_prev_msb_rise)
                v3_acc <= 16'd0;
            else
                v3_acc <= v3_acc + {8'd0, v3_frequency};
        end
    end

    wire [7:0] v3_saw = v3_acc[15:8];
    wire       v3_ring_msb = v3_ring_en ? v3_prev_msb : v3_acc[15];
    wire [7:0] v3_tri = {v3_acc[14:8] ^ {7{v3_ring_msb}}, 1'b0};
    wire       v3_pulse_cmp = v3_acc[15:8] >= v3_pw;

    reg [7:0] v3_wave;
    always @(*) begin
        if (!v3_waveform[7] && !v3_waveform[6] && !v3_waveform[5] && !v3_waveform[4])
            v3_wave = 8'h00;
        else begin
            v3_wave = 8'hFF;
            if (v3_waveform[4]) v3_wave = v3_wave & v3_tri;
            if (v3_waveform[5]) v3_wave = v3_wave & v3_saw;
            if (v3_waveform[6]) v3_wave = v3_wave & {8{v3_pulse_cmp}};
            if (v3_waveform[7]) v3_wave = v3_wave & shared_lfsr[22:15];
        end
    end
    wire [11:0] v3_out = rst ? 12'd0 : (v3_wave * v3_env);

    reg [3:0] v3_rate;
    always @(*) case (v3_ast)
        ENV_ATTACK:  v3_rate = shared_attack[3:0];
        ENV_DECAY:   v3_rate = shared_attack[7:4];
        ENV_RELEASE: v3_rate = shared_sustain[7:4];
        default:     v3_rate = 4'd0;
    endcase

    wire v3_tick = env_tick_fn(v3_rate, adsr_prescaler);

    reg [1:0] v3_nxt_ast; reg [3:0] v3_nxt_env;
    always @(*) begin
        v3_nxt_ast = v3_ast; v3_nxt_env = v3_env;
        case (v3_ast)
            ENV_IDLE: begin
                v3_nxt_env = 4'd0;
                if (v3_gate && !v3_lg) v3_nxt_ast = ENV_ATTACK;
            end
            ENV_ATTACK:
                if (!v3_gate) v3_nxt_ast = ENV_RELEASE;
                else if (v3_env == 4'hF) v3_nxt_ast = ENV_DECAY;
                else if (v3_tick) v3_nxt_env = v3_env + 1'b1;
            ENV_DECAY:
                if (!v3_gate) v3_nxt_ast = ENV_RELEASE;
                else if (v3_env > sustain_level && v3_tick) v3_nxt_env = v3_env - 1'b1;
            ENV_RELEASE:
                if (v3_gate && !v3_lg) v3_nxt_ast = ENV_ATTACK;
                else if (v3_env == 4'd0) v3_nxt_ast = ENV_IDLE;
                else if (v3_tick) v3_nxt_env = v3_env - 1'b1;
        endcase
    end

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            v3_env <= 0; v3_ast <= ENV_IDLE; v3_lg <= 0;
        end else begin
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
    // PWM Audio Output (8-bit, ~3.9 kHz at 1 MHz)
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
