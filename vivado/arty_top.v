`timescale 1ns / 1ps
//==============================================================================
// Arty A7 Top-Level Wrapper for tt_um_sid
//==============================================================================
// Bridges the Arty A7-100 board I/O to the TT pin interface:
//   - 100 MHz oscillator divided to 50 MHz via toggle FF + BUFG
//   - btn[0] active-high reset → rst_n active-low
//   - sw[0] active-high → ena
//   - Pmod JA top row: SPI bus (pins 1-3) + PDM audio out (pin 4)
//   - Green LEDs: uo_out[3:0] for debug
//==============================================================================

module arty_top (
    input  wire       CLK100MHZ,       // 100 MHz board oscillator
    input  wire [3:0] btn,             // Pushbuttons (active high)
    input  wire [3:0] sw,              // Slide switches
    output wire [3:0] led,             // Green LEDs (LD4-LD7)

    // Pmod JA — SPI interface + audio output
    input  wire       spi_clk_in,      // JA pin 1 (G13)
    input  wire       spi_cs_n_in,     // JA pin 2 (B11)
    input  wire       spi_mosi_in,     // JA pin 3 (A11)
    output wire       pdm_out          // JA pin 4 (D12)
);

    //==========================================================================
    // 50 MHz clock from 100 MHz toggle divider
    //==========================================================================
    reg clk_div = 1'b0;
    always @(posedge CLK100MHZ) clk_div <= ~clk_div;

    wire clk_50;
    BUFG bufg_clk50 (.I(clk_div), .O(clk_50));

    //==========================================================================
    // TT pin mapping
    //==========================================================================
    wire rst_n = ~btn[0];

    wire [7:0] ui_in  = {5'b00000, spi_mosi_in, spi_cs_n_in, spi_clk_in};
    wire [7:0] uo_out;
    wire [7:0] uio_out;
    wire [7:0] uio_oe;

    tt_um_sid u_sid (
        .ui_in   (ui_in),
        .uo_out  (uo_out),
        .uio_in  (8'b0),
        .uio_out (uio_out),
        .uio_oe  (uio_oe),
        .ena     (sw[0]),
        .clk     (clk_50),
        .rst_n   (rst_n)
    );

    //==========================================================================
    // Output mapping
    //==========================================================================
    assign pdm_out = uo_out[1];
    assign led     = uo_out[3:0];

endmodule
