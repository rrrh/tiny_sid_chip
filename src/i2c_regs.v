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
    // State machine
    //==========================================================================
    // Byte phases: ADDR(byte0), REG(byte1), DATA(byte2+)
    // Within each byte: 8 data bits on SCL rise, then ACK on SCL fall/rise
    localparam [2:0] ST_IDLE     = 3'd0,
                     ST_ADDR     = 3'd1,  // receiving address byte bits
                     ST_ADDR_ACK = 3'd2,  // ACK phase for address byte
                     ST_REG      = 3'd3,  // receiving register address byte
                     ST_REG_ACK  = 3'd4,
                     ST_DATA     = 3'd5,  // receiving data byte
                     ST_DATA_ACK = 3'd6;

    reg [2:0]  state;
    reg [7:0]  shift_reg;
    reg [2:0]  bit_cnt;    // counts 0..7 for 8 data bits
    reg [2:0]  reg_addr;
    reg        ack_phase;  // 0=waiting for SCL rise (master samples ACK), 1=done

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            state         <= ST_IDLE;
            shift_reg     <= 8'd0;
            bit_cnt       <= 3'd0;
            reg_addr      <= 3'd0;
            sda_oe        <= 1'b0;
            ack_phase     <= 1'b0;
            sid_frequency <= 16'd0;
            sid_duration  <= 8'd0;
            sid_attack    <= 8'd0;
            sid_sustain   <= 8'd0;
            sid_waveform  <= 8'd0;
        end else begin
            // START always restarts the transaction
            if (i2c_start) begin
                state     <= ST_ADDR;
                bit_cnt   <= 3'd0;
                shift_reg <= 8'd0;
                sda_oe    <= 1'b0;
                ack_phase <= 1'b0;
            end
            // STOP always returns to idle
            else if (i2c_stop) begin
                state  <= ST_IDLE;
                sda_oe <= 1'b0;
            end
            else begin
                case (state)

                //--------------------------------------------------------------
                // IDLE — wait for START
                //--------------------------------------------------------------
                ST_IDLE: begin
                    sda_oe <= 1'b0;
                end

                //--------------------------------------------------------------
                // ADDR — shift in 8 bits (7-bit address + R/W) on SCL rise
                //--------------------------------------------------------------
                ST_ADDR: begin
                    if (scl_rise) begin
                        shift_reg <= {shift_reg[6:0], sda_d2};
                        if (bit_cnt == 3'd7) begin
                            state     <= ST_ADDR_ACK;
                            bit_cnt   <= 3'd0;
                            ack_phase <= 1'b0;
                        end else begin
                            bit_cnt <= bit_cnt + 1'b1;
                        end
                    end
                end

                //--------------------------------------------------------------
                // ADDR_ACK — assert ACK on SCL fall, release on next SCL fall
                //--------------------------------------------------------------
                ST_ADDR_ACK: begin
                    if (!ack_phase) begin
                        // First SCL fall after last data bit: assert ACK
                        if (scl_fall) begin
                            if (shift_reg[7:1] == I2C_ADDR && shift_reg[0] == 1'b0) begin
                                sda_oe    <= 1'b1;  // ACK (pull SDA low)
                                ack_phase <= 1'b1;
                            end else begin
                                // NACK — wrong address or read mode
                                sda_oe <= 1'b0;
                                state  <= ST_IDLE;
                            end
                        end
                    end else begin
                        // Next SCL fall: release ACK, move to REG byte
                        if (scl_fall) begin
                            sda_oe    <= 1'b0;
                            state     <= ST_REG;
                            shift_reg <= 8'd0;
                            ack_phase <= 1'b0;
                        end
                    end
                end

                //--------------------------------------------------------------
                // REG — shift in register address byte
                //--------------------------------------------------------------
                ST_REG: begin
                    if (scl_rise) begin
                        shift_reg <= {shift_reg[6:0], sda_d2};
                        if (bit_cnt == 3'd7) begin
                            state     <= ST_REG_ACK;
                            bit_cnt   <= 3'd0;
                            ack_phase <= 1'b0;
                        end else begin
                            bit_cnt <= bit_cnt + 1'b1;
                        end
                    end
                end

                //--------------------------------------------------------------
                // REG_ACK — ACK the register address byte
                //--------------------------------------------------------------
                ST_REG_ACK: begin
                    if (!ack_phase) begin
                        if (scl_fall) begin
                            reg_addr  <= shift_reg[2:0];
                            sda_oe    <= 1'b1;  // ACK
                            ack_phase <= 1'b1;
                        end
                    end else begin
                        if (scl_fall) begin
                            sda_oe    <= 1'b0;
                            state     <= ST_DATA;
                            shift_reg <= 8'd0;
                            ack_phase <= 1'b0;
                        end
                    end
                end

                //--------------------------------------------------------------
                // DATA — shift in data byte
                //--------------------------------------------------------------
                ST_DATA: begin
                    if (scl_rise) begin
                        shift_reg <= {shift_reg[6:0], sda_d2};
                        if (bit_cnt == 3'd7) begin
                            state     <= ST_DATA_ACK;
                            bit_cnt   <= 3'd0;
                            ack_phase <= 1'b0;
                        end else begin
                            bit_cnt <= bit_cnt + 1'b1;
                        end
                    end
                end

                //--------------------------------------------------------------
                // DATA_ACK — ACK data, write to register, auto-increment addr
                //--------------------------------------------------------------
                ST_DATA_ACK: begin
                    if (!ack_phase) begin
                        if (scl_fall) begin
                            // Write the received byte to the addressed register
                            case (reg_addr)
                                3'd0: sid_frequency[7:0]  <= shift_reg;
                                3'd1: sid_frequency[15:8] <= shift_reg;
                                3'd2: sid_duration         <= shift_reg;
                                3'd4: sid_attack           <= shift_reg;
                                3'd5: sid_sustain          <= shift_reg;
                                3'd6: sid_waveform         <= shift_reg;
                                default: ;
                            endcase
                            reg_addr  <= reg_addr + 1'b1;
                            sda_oe    <= 1'b1;  // ACK
                            ack_phase <= 1'b1;
                        end
                    end else begin
                        if (scl_fall) begin
                            sda_oe    <= 1'b0;
                            state     <= ST_DATA;
                            shift_reg <= 8'd0;
                            ack_phase <= 1'b0;
                        end
                    end
                end

                default: state <= ST_IDLE;

                endcase
            end
        end
    end

endmodule
