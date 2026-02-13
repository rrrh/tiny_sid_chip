## =============================================================================
## Arty A7-100 Constraints for tt_um_sid
## Derived from Arty_Master.xdc (Rev. D)
## =============================================================================

## Clock — 100 MHz oscillator
set_property -dict { PACKAGE_PIN E3    IOSTANDARD LVCMOS33 } [get_ports { CLK100MHZ }];
create_clock -add -name sys_clk_pin -period 10.00 -waveform {0 5} [get_ports { CLK100MHZ }];

## Generated 50 MHz clock (toggle divider → BUFG)
create_generated_clock -name clk_50mhz -source [get_ports CLK100MHZ] -divide_by 2 \
    [get_pins bufg_clk50/O]

## Pushbuttons (active high)
set_property -dict { PACKAGE_PIN D9    IOSTANDARD LVCMOS33 } [get_ports { btn[0] }]; # BTN0 → reset
set_property -dict { PACKAGE_PIN C9    IOSTANDARD LVCMOS33 } [get_ports { btn[1] }]; # BTN1 (unused)
set_property -dict { PACKAGE_PIN B9    IOSTANDARD LVCMOS33 } [get_ports { btn[2] }]; # BTN2 (unused)
set_property -dict { PACKAGE_PIN B8    IOSTANDARD LVCMOS33 } [get_ports { btn[3] }]; # BTN3 (unused)

## Slide switches
set_property -dict { PACKAGE_PIN A8    IOSTANDARD LVCMOS33 } [get_ports { sw[0] }]; # SW0 → ena
set_property -dict { PACKAGE_PIN C11   IOSTANDARD LVCMOS33 } [get_ports { sw[1] }]; # SW1 (unused)
set_property -dict { PACKAGE_PIN C10   IOSTANDARD LVCMOS33 } [get_ports { sw[2] }]; # SW2 (unused)
set_property -dict { PACKAGE_PIN A10   IOSTANDARD LVCMOS33 } [get_ports { sw[3] }]; # SW3 (unused)

## Green LEDs — uo_out[3:0] debug
set_property -dict { PACKAGE_PIN H5    IOSTANDARD LVCMOS33 } [get_ports { led[0] }]; # LD4
set_property -dict { PACKAGE_PIN J5    IOSTANDARD LVCMOS33 } [get_ports { led[1] }]; # LD5  (= pdm_out)
set_property -dict { PACKAGE_PIN T9    IOSTANDARD LVCMOS33 } [get_ports { led[2] }]; # LD6
set_property -dict { PACKAGE_PIN T10   IOSTANDARD LVCMOS33 } [get_ports { led[3] }]; # LD7

## Pmod JA — SPI bus (pins 1-3) + PDM audio output (pin 4)
##
##   Pin 1 (G13) ← spi_clk    from MCU SCK
##   Pin 2 (B11) ← spi_cs_n   from MCU CS
##   Pin 3 (A11) ← spi_mosi   from MCU MOSI
##   Pin 4 (D12) → pdm_out    to RC filter → headphones / amp
##   Pin 5        GND
##   Pin 6        VCC (3.3 V)
##
set_property -dict { PACKAGE_PIN G13   IOSTANDARD LVCMOS33 } [get_ports { spi_clk_in }];
set_property -dict { PACKAGE_PIN B11   IOSTANDARD LVCMOS33 } [get_ports { spi_cs_n_in }];
set_property -dict { PACKAGE_PIN A11   IOSTANDARD LVCMOS33 } [get_ports { spi_mosi_in }];
set_property -dict { PACKAGE_PIN D12   IOSTANDARD LVCMOS33 } [get_ports { pdm_out }];

## SPI inputs are asynchronous to clk_50 — mark as false paths for timing
set_false_path -from [get_ports { spi_clk_in spi_cs_n_in spi_mosi_in }]

## Button and switch inputs are asynchronous
set_false_path -from [get_ports { btn[*] sw[*] }]
