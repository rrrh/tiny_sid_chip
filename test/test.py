# SPDX-License-Identifier: Apache-2.0

import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge


async def spi_write(dut, addr, data):
    """Write a 24-bit SPI transaction: {1'b1, 4'b0, addr[2:0], data[15:0]}
    CPOL=0, CPHA=0, MSB first.
    ui_in[0] = spi_clk, ui_in[1] = spi_cs_n, ui_in[2] = spi_mosi
    """
    word = (1 << 23) | ((addr & 0x7) << 16) | (data & 0xFFFF)

    # Assert CS low
    ui = dut.ui_in.value.integer if hasattr(dut.ui_in.value, 'integer') else 0
    ui = ui & ~0x02  # CS low
    ui = ui & ~0x01  # CLK low
    dut.ui_in.value = ui
    await ClockCycles(dut.clk, 5)

    for i in range(23, -1, -1):
        bit = (word >> i) & 1
        # Set MOSI, CLK low
        ui = (ui & ~0x04) | (bit << 2)
        ui = ui & ~0x01  # CLK low
        dut.ui_in.value = ui
        await ClockCycles(dut.clk, 5)

        # CLK high — data sampled
        ui = ui | 0x01
        dut.ui_in.value = ui
        await ClockCycles(dut.clk, 5)

    # CLK low, then deassert CS
    ui = ui & ~0x01
    dut.ui_in.value = ui
    await ClockCycles(dut.clk, 5)

    ui = ui | 0x02  # CS high
    dut.ui_in.value = ui
    await ClockCycles(dut.clk, 10)


async def sid_write(dut, reg_index, data):
    """Write to a SID register (0-4) via SPI."""
    await spi_write(dut, reg_index, data)


async def count_pdm(dut, cycles):
    """Count PDM rising edges on uo_out[1] over a number of clock cycles."""
    count = 0
    last = 0
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        val = (dut.uo_out.value.integer >> 1) & 1
        if val == 1 and last == 0:
            count += 1
        last = val
    return count


@cocotb.test()
async def test_reset(dut):
    """Test that reset clears outputs."""
    clock = Clock(dut.clk, 20, units="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x02  # CS high, CLK low
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)

    # During reset, PDM should be 0
    assert (dut.uo_out.value.integer & 0x02) == 0, "PDM should be 0 during reset"

    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)


@cocotb.test()
async def test_sawtooth(dut):
    """Test sawtooth waveform produces PDM output."""
    clock = Clock(dut.clk, 20, units="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x02  # CS high
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    # Frequency: C4 (~262 Hz at 50 MHz) = 4291
    await sid_write(dut, 0, 4291)
    # Attack=0 (fastest), Decay=0
    await sid_write(dut, 2, 0x0000)
    # Sustain=F (full), Release=0
    await sid_write(dut, 3, 0x00F0)
    # Sawtooth + gate: bit5=saw, bit0=gate
    await sid_write(dut, 4, 0x0021)

    # Wait for attack to ramp up and check PDM activity
    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pdm(dut, 100000)
    dut._log.info(f"Sawtooth PDM count: {pdm_count}")
    assert pdm_count > 0, f"Sawtooth should produce PDM pulses, got {pdm_count}"


@cocotb.test()
async def test_triangle(dut):
    """Test triangle waveform produces PDM output."""
    clock = Clock(dut.clk, 20, units="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x02
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    await sid_write(dut, 0, 4291)
    await sid_write(dut, 2, 0x0000)
    await sid_write(dut, 3, 0x00F0)
    # Triangle + gate: bit4=tri, bit0=gate
    await sid_write(dut, 4, 0x0011)

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pdm(dut, 100000)
    dut._log.info(f"Triangle PDM count: {pdm_count}")
    assert pdm_count > 0, f"Triangle should produce PDM pulses, got {pdm_count}"


@cocotb.test()
async def test_pulse(dut):
    """Test pulse waveform produces PDM output."""
    clock = Clock(dut.clk, 20, units="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x02
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    await sid_write(dut, 0, 4291)
    # Pulse width = 50% (2048)
    await sid_write(dut, 1, 2048)
    await sid_write(dut, 2, 0x0000)
    await sid_write(dut, 3, 0x00F0)
    # Pulse + gate: bit6=pulse, bit0=gate
    await sid_write(dut, 4, 0x0041)

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pdm(dut, 100000)
    dut._log.info(f"Pulse PDM count: {pdm_count}")
    assert pdm_count > 0, f"Pulse should produce PDM pulses, got {pdm_count}"


@cocotb.test()
async def test_noise(dut):
    """Test noise waveform produces PDM output."""
    clock = Clock(dut.clk, 20, units="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x02
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    await sid_write(dut, 0, 4291)
    await sid_write(dut, 2, 0x0000)
    await sid_write(dut, 3, 0x00F0)
    # Noise + gate: bit7=noise, bit0=gate
    await sid_write(dut, 4, 0x0081)

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pdm(dut, 100000)
    dut._log.info(f"Noise PDM count: {pdm_count}")
    assert pdm_count > 0, f"Noise should produce PDM pulses, got {pdm_count}"


@cocotb.test(skip=os.environ.get("GATES") == "yes")
async def test_gate_release(dut):
    """Test that releasing the gate silences PDM output. Skipped in GL sim."""
    clock = Clock(dut.clk, 20, units="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x02
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    await sid_write(dut, 0, 4291)
    await sid_write(dut, 2, 0x0000)
    await sid_write(dut, 3, 0x00F0)  # sustain=F, release=0 (fastest)
    # Sawtooth + gate
    await sid_write(dut, 4, 0x0021)

    # Let it play
    await ClockCycles(dut.clk, 200000)

    # Release gate (clear bit 0)
    await sid_write(dut, 4, 0x0020)

    # Wait for release to complete (longer for gate-level timing)
    await ClockCycles(dut.clk, 500000)

    # PDM should be silent (allow small residual from GL timing)
    pdm_count = await count_pdm(dut, 100000)
    dut._log.info(f"After release PDM count: {pdm_count}")
    assert pdm_count < 100, f"PDM should be nearly silent after release, got {pdm_count}"
