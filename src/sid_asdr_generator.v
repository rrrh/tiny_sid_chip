`timescale 1ns / 1ps
//==============================================================================
// Simplified Linear ADSR Envelope Generator
//==============================================================================
// Linear attack/decay/release with power-of-2 rate scaling.
// Uses a free-running prescaler — the 4-bit rate value selects which
// prescaler bit to use as the envelope tick (rate 0 = fast, 15 = slow).
//
// Approximate timings at 50 MHz (256 steps per phase):
//   Rate 0:  ~2.6 ms     Rate 8:  ~671 ms
//   Rate 4:  ~42 ms      Rate 12: ~10.7 s
//
// States: IDLE → ATTACK → DECAY → RELEASE → IDLE
//   Sustain is handled within DECAY (hold when env reaches sustain level).
//==============================================================================

module sid_asdr_generator (
    input  wire       clk,
    input  wire       rst,
    input  wire       gate,
    input  wire [3:0] attack_rate,
    input  wire [3:0] decay_rate,
    input  wire [3:0] sustain_value,
    input  wire [3:0] release_rate,
    output wire [7:0] adsr_value
);

    //==========================================================================
    // State encoding
    //==========================================================================
    localparam [1:0] ENV_IDLE    = 2'd0,
                     ENV_ATTACK  = 2'd1,
                     ENV_DECAY   = 2'd2,
                     ENV_RELEASE = 2'd3;

    //==========================================================================
    // Registers
    //==========================================================================
    reg [1:0]  state;
    reg [7:0]  env_counter;
    reg        last_gate;
    reg [22:0] prescaler;

    //==========================================================================
    // Rate selection — pick active rate based on state
    //==========================================================================
    reg [3:0] active_rate;
    always @(*) begin
        case (state)
            ENV_ATTACK:  active_rate = attack_rate;
            ENV_DECAY:   active_rate = decay_rate;
            ENV_RELEASE: active_rate = release_rate;
            default:     active_rate = 4'd0;
        endcase
    end

    //==========================================================================
    // Envelope tick — select prescaler bit based on rate
    // Rate N checks &prescaler[N+8:0], firing every 2^(N+9) clocks
    //==========================================================================
    reg env_tick;
    always @(*) begin
        case (active_rate)
            4'd0:  env_tick = &prescaler[8:0];
            4'd1:  env_tick = &prescaler[9:0];
            4'd2:  env_tick = &prescaler[10:0];
            4'd3:  env_tick = &prescaler[11:0];
            4'd4:  env_tick = &prescaler[12:0];
            4'd5:  env_tick = &prescaler[13:0];
            4'd6:  env_tick = &prescaler[14:0];
            4'd7:  env_tick = &prescaler[15:0];
            4'd8:  env_tick = &prescaler[16:0];
            4'd9:  env_tick = &prescaler[17:0];
            4'd10: env_tick = &prescaler[18:0];
            4'd11: env_tick = &prescaler[19:0];
            4'd12: env_tick = &prescaler[20:0];
            4'd13: env_tick = &prescaler[21:0];
            4'd14: env_tick = &prescaler[22:0];
            default: env_tick = &prescaler[22:0];
        endcase
    end

    wire [7:0] sustain_level = {sustain_value, 4'h0};

    //==========================================================================
    // State machine
    //==========================================================================
    always @(posedge clk) begin
        if (rst) begin
            state       <= ENV_IDLE;
            env_counter <= 8'd0;
            last_gate   <= 1'b0;
            prescaler   <= 23'd0;
        end else begin
            prescaler <= prescaler + 1'b1;
            last_gate <= gate;

            case (state)
                ENV_IDLE: begin
                    env_counter <= 8'd0;
                    if (gate && !last_gate)
                        state <= ENV_ATTACK;
                end

                ENV_ATTACK: begin
                    if (!gate) begin
                        state <= ENV_RELEASE;
                    end else if (env_counter == 8'hFF) begin
                        state <= ENV_DECAY;
                    end else if (env_tick) begin
                        env_counter <= env_counter + 1'b1;
                    end
                end

                ENV_DECAY: begin
                    if (!gate) begin
                        state <= ENV_RELEASE;
                    end else if (env_counter > sustain_level && env_tick) begin
                        env_counter <= env_counter - 1'b1;
                    end
                end

                ENV_RELEASE: begin
                    if (gate && !last_gate) begin
                        state <= ENV_ATTACK;
                    end else if (env_counter == 8'd0) begin
                        state <= ENV_IDLE;
                    end else if (env_tick) begin
                        env_counter <= env_counter - 1'b1;
                    end
                end
            endcase
        end
    end

    assign adsr_value = {env_counter[7:1], 1'b0};

endmodule
