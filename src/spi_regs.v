`timescale 1ns / 1ps
//==============================================================================
// SPI Register Bank for SID Voice (Write-Only)
//==============================================================================
// Direct SPI-to-register interface. Write-only — no read-back support.
//
// SPI Protocol (CPOL=0, CPHA=0, MSB first):
//   3-byte (24-bit) write transactions:
//     Byte 0 (CMD):    [7]=1 (write)  [6:3]=unused  [2:0]=register index (0-4)
//     Byte 1 (DATA_H): data[15:8]
//     Byte 2 (DATA_L): data[7:0]
//
// Register Map (by index):
//   0: frequency [15:0]
//   1: duration  [15:0]
//   2: attack    [7:0]  (upper 8 bits ignored)
//   3: sustain   [7:0]  (upper 8 bits ignored)
//   4: waveform  [7:0]  (upper 8 bits ignored)
//==============================================================================

module spi_regs (
    input  wire        clk,
    input  wire        rst_n,

    // SPI slave interface
    input  wire        spi_clk,
    input  wire        spi_cs_n,
    input  wire        spi_mosi,
    output wire        spi_miso,

    // SID register outputs
    output reg  [15:0] sid_frequency,
    output reg  [15:0] sid_duration,
    output reg  [7:0]  sid_attack,
    output reg  [7:0]  sid_sustain,
    output reg  [7:0]  sid_waveform
);

    // Write-only: MISO always low
    assign spi_miso = 1'b0;

    //==========================================================================
    // 2FF Synchronizers
    //==========================================================================
    reg spi_clk_d1,  spi_clk_d2;
    reg spi_cs_n_d1, spi_cs_n_d2;
    reg spi_mosi_d1, spi_mosi_d2;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            spi_clk_d1  <= 1'b0;
            spi_clk_d2  <= 1'b0;
            spi_cs_n_d1 <= 1'b1;
            spi_cs_n_d2 <= 1'b1;
            spi_mosi_d1 <= 1'b0;
            spi_mosi_d2 <= 1'b0;
        end else begin
            spi_clk_d1  <= spi_clk;
            spi_clk_d2  <= spi_clk_d1;
            spi_cs_n_d1 <= spi_cs_n;
            spi_cs_n_d2 <= spi_cs_n_d1;
            spi_mosi_d1 <= spi_mosi;
            spi_mosi_d2 <= spi_mosi_d1;
        end
    end

    //==========================================================================
    // Edge Detection
    //==========================================================================
    reg spi_clk_d3;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n)
            spi_clk_d3 <= 1'b0;
        else
            spi_clk_d3 <= spi_clk_d2;
    end

    wire spi_clk_rise = spi_clk_d2 && !spi_clk_d3;
    wire cs_active    = !spi_cs_n_d2;

    //==========================================================================
    // SPI Receive Logic (system clock domain)
    //==========================================================================
    reg [23:0] rx_shift;
    reg [4:0]  bit_cnt;
    reg        cmd_captured;
    reg        is_write;
    reg [2:0]  reg_addr;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rx_shift     <= 24'd0;
            bit_cnt      <= 5'd0;
            cmd_captured <= 1'b0;
            is_write     <= 1'b0;
            reg_addr     <= 3'd0;

            sid_frequency <= 16'd0;
            sid_duration  <= 16'd0;
            sid_attack    <= 8'd0;
            sid_sustain   <= 8'd0;
            sid_waveform  <= 8'd0;
        end else if (!cs_active) begin
            // CS_n high — reset transaction state
            rx_shift     <= 24'd0;
            bit_cnt      <= 5'd0;
            cmd_captured <= 1'b0;
            is_write     <= 1'b0;
            reg_addr     <= 3'd0;
        end else if (spi_clk_rise) begin
            rx_shift <= {rx_shift[22:0], spi_mosi_d2};
            bit_cnt  <= bit_cnt + 1'b1;

            // After 8 bits: CMD byte captured
            if (bit_cnt == 5'd7 && !cmd_captured) begin
                cmd_captured <= 1'b1;
                is_write     <= rx_shift[6];
                reg_addr     <= {rx_shift[1:0], spi_mosi_d2};
            end

            // After 24 bits: if write, store data
            if (bit_cnt == 5'd23 && is_write) begin
                case (reg_addr)
                    3'd0: sid_frequency <= {rx_shift[14:0], spi_mosi_d2};
                    3'd1: sid_duration  <= {rx_shift[14:0], spi_mosi_d2};
                    3'd2: sid_attack    <= {rx_shift[6:0], spi_mosi_d2};
                    3'd3: sid_sustain   <= {rx_shift[6:0], spi_mosi_d2};
                    3'd4: sid_waveform  <= {rx_shift[6:0], spi_mosi_d2};
                    default: ;
                endcase
            end
        end
    end

endmodule
