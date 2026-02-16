`timescale 1ns / 1ps
//==============================================================================
// SPI Register Bank for SID Voice (Write-Only)
//==============================================================================
// Direct SPI-to-register interface. Write-only — no read-back support.
//
// SPI Protocol (CPOL=0, CPHA=0, MSB first):
//   2-byte (16-bit) write transactions:
//     [15:13] = addr[2:0]   (3-bit register address)
//     [12:8]  = reserved    (ignored)
//     [7:0]   = data[7:0]   (8-bit data)
//
// Register Map (by address):
//   0: freq_lo    — sid_frequency[7:0]
//   1: freq_hi    — sid_frequency[15:8]
//   2: pw_lo      — sid_duration[7:0]   (pulse width)
//   4: attack     — sid_attack[7:0]     (atk[3:0] / dec[7:4])
//   5: sustain    — sid_sustain[7:0]    (sus[3:0] / rel[7:4])
//   6: waveform   — sid_waveform[7:0]
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
    output reg  [7:0]  sid_duration,
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
    reg [15:0] rx_shift;
    reg [3:0]  bit_cnt;

    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            rx_shift     <= 16'd0;
            bit_cnt      <= 4'd0;

            sid_frequency <= 16'd0;
            sid_duration  <= 8'd0;
            sid_attack    <= 8'd0;
            sid_sustain   <= 8'd0;
            sid_waveform  <= 8'd0;
        end else if (!cs_active) begin
            // CS_n high — reset transaction state
            rx_shift     <= 16'd0;
            bit_cnt      <= 4'd0;
        end else if (spi_clk_rise) begin
            rx_shift <= {rx_shift[14:0], spi_mosi_d2};
            bit_cnt  <= bit_cnt + 1'b1;

            // After 16 bits: store data to addressed register
            if (bit_cnt == 4'd15) begin
                case (rx_shift[14:12])
                    3'd0: sid_frequency[7:0]  <= {rx_shift[6:0], spi_mosi_d2};
                    3'd1: sid_frequency[15:8] <= {rx_shift[6:0], spi_mosi_d2};
                    3'd2: sid_duration         <= {rx_shift[6:0], spi_mosi_d2};
                    3'd4: sid_attack           <= {rx_shift[6:0], spi_mosi_d2};
                    3'd5: sid_sustain          <= {rx_shift[6:0], spi_mosi_d2};
                    3'd6: sid_waveform         <= {rx_shift[6:0], spi_mosi_d2};
                    default: ;
                endcase
            end
        end
    end

endmodule
