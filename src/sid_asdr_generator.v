`timescale 1ns / 1ps
//==============================================================================
// Simplified Linear ADSR Envelope Generator
//==============================================================================
// Linear attack/decay/release with power-of-2 rate scaling.
// Uses a free-running 16-bit prescaler — the 4-bit rate value selects which
// prescaler bit to use as the envelope tick (rate 0 = fast, 7+ = slow).
//
// Approximate timings at 50 MHz (256 steps per phase):
//   Rate 0:  ~2.6 ms     Rate 4:  ~42 ms
//   Rate 7:  ~335 ms     Rate 8+: ~335 ms (clamped)
//
// States: IDLE → ATTACK → DECAY → RELEASE → IDLE
//   Sustain is handled within DECAY (hold when env reaches sustain level).
//==============================================================================

module sid_asdr_generator (
    input  wire        clk,
    input  wire        rst,
    input  wire        gate,
    input  wire [3:0]  attack_rate,
    input  wire [3:0]  decay_rate,
    input  wire [3:0]  sustain_value,
    input  wire [3:0]  release_rate,
    input  wire [15:0] prescaler,
    output wire [7:0]  adsr_value
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
    // Envelope tick — select prescaler bit based on rate (clamped to 7)
    // Rate N checks &prescaler[N+8:0], firing every 2^(N+9) clocks
    // Rates 8-15 clamp to rate 7 (~335 ms per phase at 50 MHz)
    //==========================================================================
    reg env_tick;
    wire [2:0] clamped_rate = (active_rate > 4'd7) ? 3'd7 : active_rate[2:0];
    always @(*) begin
        case (clamped_rate)
            3'd0:    env_tick = &prescaler[8:0];
            3'd1:    env_tick = &prescaler[9:0];
            3'd2:    env_tick = &prescaler[10:0];
            3'd3:    env_tick = &prescaler[11:0];
            3'd4:    env_tick = &prescaler[12:0];
            3'd5:    env_tick = &prescaler[13:0];
            3'd6:    env_tick = &prescaler[14:0];
            default: env_tick = &prescaler[15:0];
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
        end else begin
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
