`timescale 1ns / 1ps
//==============================================================================
// I2C Register Bank for SID Voice (Write-Only)
//==============================================================================
// I2C slave interface. Write-only — no read-back support.
//
// I2C Protocol:
//   7-bit address: 0x36 (fixed)
//   Write transaction:
//     START → [0x6C] → ACK → [reg_addr] → ACK → [data] → ACK → STOP
//   Register address auto-increments for multi-byte writes.
//
// Register Map (by address):
//   0: freq_lo    — sid_frequency[7:0]
//   1: freq_hi    — sid_frequency[15:8]
//   2: pw_lo      — sid_duration[7:0]   (pulse width)
//   4: attack     — sid_attack[7:0]     (atk[3:0] / dec[7:4])
//   5: sustain    — sid_sustain[7:0]    (sus[3:0] / rel[7:4])
//   6: waveform   — sid_waveform[7:0]
//==============================================================================

module i2c_regs (
    input  wire        clk,
    input  wire        rst_n,

    // I2C interface
    input  wire        scl_in,
    input  wire        sda_in,
    output reg         sda_oe,        // active-high: drive SDA low (open-drain ACK)

    // SID register outputs (Voice 1)
    output reg  [15:0] sid_frequency,
    output reg  [7:0]  sid_duration,
    output reg  [7:0]  sid_attack,
    output reg  [7:0]  sid_sustain,
    output reg  [7:0]  sid_waveform,

    // Voice 2 — not controllable via I2C, tied off
    output wire [7:0]  v2_attack,
    output wire [7:0]  v2_gate_freq
);

    assign v2_attack    = 8'd0;
    assign v2_gate_freq = 8'd0;

    localparam [6:0] I2C_ADDR = 7'h36;

    //==========================================================================
    // 2FF Synchronizers
    //==========================================================================
    reg scl_d1, scl_d2, sda_d1, sda_d2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            scl_d1 <= 1'b1; scl_d2 <= 1'b1;
            sda_d1 <= 1'b1; sda_d2 <= 1'b1;
        end else begin
            scl_d1 <= scl_in; scl_d2 <= scl_d1;
            sda_d1 <= sda_in; sda_d2 <= sda_d1;
        end
    end

    //==========================================================================
    // Edge / condition detection
    //==========================================================================
    reg scl_d3, sda_d3;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            scl_d3 <= 1'b1;
            sda_d3 <= 1'b1;
        end else begin
            scl_d3 <= scl_d2;
            sda_d3 <= sda_d2;
        end
    end

    wire scl_rise  =  scl_d2 && !scl_d3;
    wire scl_fall  = !scl_d2 &&  scl_d3;
    wire i2c_start = !sda_d2 &&  sda_d3 && scl_d2;  // SDA↓ while SCL high
    wire i2c_stop  =  sda_d2 && !sda_d3 && scl_d2;  // SDA↑ while SCL high

    //==========================================================================
    // State machine — 3 states + 2-bit byte counter
    //==========================================================================
    // Merged FSM: one SHIFT state handles all byte reception,
    // one ACK state handles all ACK phases. byte_num selects action.
    localparam [1:0] ST_IDLE  = 2'd0,
                     ST_SHIFT = 2'd1,
                     ST_ACK   = 2'd2;

    localparam [1:0] BN_ADDR = 2'd0,  // byte 0: slave address
                     BN_REG  = 2'd1,  // byte 1: register address
                     BN_DATA = 2'd2;  // byte 2+: data

    reg [1:0]  state;
    reg [1:0]  byte_num;
    reg [7:0]  shift_reg;
    reg [2:0]  bit_cnt;
    reg [2:0]  reg_addr;

    // sda_oe doubles as ACK sub-phase indicator:
    //   ACK state, sda_oe=0 → waiting for first SCL fall (assert ACK)
    //   ACK state, sda_oe=1 → waiting for second SCL fall (release ACK)

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= ST_IDLE;
            byte_num      <= BN_ADDR;
            shift_reg     <= 8'd0;
            bit_cnt       <= 3'd0;
            reg_addr      <= 3'd0;
            sda_oe        <= 1'b0;
            sid_frequency <= 16'd0;
            sid_duration  <= 8'd0;
            sid_attack    <= 8'd0;
            sid_sustain   <= 8'd0;
            sid_waveform  <= 8'd0;
        end else begin
            if (i2c_start) begin
                state     <= ST_SHIFT;
                byte_num  <= BN_ADDR;
                bit_cnt   <= 3'd0;
                shift_reg <= 8'd0;
                sda_oe    <= 1'b0;
            end
            else if (i2c_stop) begin
                state  <= ST_IDLE;
                sda_oe <= 1'b0;
            end
            else begin
                case (state)

                ST_IDLE: begin
                    sda_oe <= 1'b0;
                end

                //--------------------------------------------------------------
                // SHIFT — receive 8 bits on SCL rising edges (all byte types)
                //--------------------------------------------------------------
                ST_SHIFT: begin
                    if (scl_rise) begin
                        shift_reg <= {shift_reg[6:0], sda_d2};
                        if (bit_cnt == 3'd7) begin
                            state   <= ST_ACK;
                            bit_cnt <= 3'd0;
                        end else begin
                            bit_cnt <= bit_cnt + 1'b1;
                        end
                    end
                end

                //--------------------------------------------------------------
                // ACK — assert/release ACK, dispatch action by byte_num
                //--------------------------------------------------------------
                ST_ACK: begin
                    if (scl_fall) begin
                        if (!sda_oe) begin
                            // First SCL fall: perform action and assert ACK
                            case (byte_num)
                                BN_ADDR: begin
                                    if (shift_reg[7:1] == I2C_ADDR && shift_reg[0] == 1'b0) begin
                                        sda_oe <= 1'b1;
                                    end else begin
                                        state <= ST_IDLE;  // NACK
                                    end
                                end
                                BN_REG: begin
                                    reg_addr <= shift_reg[2:0];
                                    sda_oe   <= 1'b1;
                                end
                                default: begin  // BN_DATA
                                    case (reg_addr)
                                        3'd0: sid_frequency[7:0]  <= shift_reg;
                                        3'd1: sid_frequency[15:8] <= shift_reg;
                                        3'd2: sid_duration         <= shift_reg;
                                        3'd4: sid_attack           <= shift_reg;
                                        3'd5: sid_sustain          <= shift_reg;
                                        3'd6: sid_waveform         <= shift_reg;
                                        default: ;
                                    endcase
                                    reg_addr <= reg_addr + 1'b1;
                                    sda_oe   <= 1'b1;
                                end
                            endcase
                        end else begin
                            // Second SCL fall: release ACK, next byte
                            sda_oe    <= 1'b0;
                            state     <= ST_SHIFT;
                            shift_reg <= 8'd0;
                            if (byte_num != BN_DATA)
                                byte_num <= byte_num + 1'b1;
                        end
                    end
                end

                default: state <= ST_IDLE;

                endcase
            end
        end
    end

endmodule
