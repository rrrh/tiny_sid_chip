# SPDX-License-Identifier: Apache-2.0

import os
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge


# Register addresses
REG_FREQ_LO  = 0
REG_FREQ_HI  = 1
REG_PW_LO    = 2
REG_PW_HI    = 3
REG_ATTACK   = 4
REG_SUSTAIN  = 5
REG_WAVEFORM = 6


async def sid_write(dut, reg_addr, data, voice=0):
    """Write to a SID register via flat memory interface.
    ui_in[2:0] = address, ui_in[4:3] = voice select, ui_in[7] = write enable,
    uio_in = data.
    """
    ui = (reg_addr & 0x07) | ((voice & 0x3) << 3)
    dut.ui_in.value = ui
    dut.uio_in.value = data & 0xFF
    await RisingEdge(dut.clk)
    dut.ui_in.value = ui | 0x80  # assert WE
    await RisingEdge(dut.clk)
    dut.ui_in.value = ui & 0x7F  # deassert WE
    await RisingEdge(dut.clk)


async def sid_write_freq(dut, freq16, voice=0):
    """Write a 16-bit frequency as two byte registers."""
    await sid_write(dut, REG_FREQ_LO, freq16 & 0xFF, voice)
    await sid_write(dut, REG_FREQ_HI, (freq16 >> 8) & 0xFF, voice)


async def sid_write_pw(dut, pw8, voice=0):
    """Write an 8-bit pulse width register."""
    await sid_write(dut, REG_PW_LO, pw8 & 0xFF, voice)


async def count_pwm(dut, cycles):
    """Count PWM rising edges on uo_out[0] over a number of clock cycles."""
    count = 0
    last = 0
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        val = (dut.uo_out.value.to_unsigned()) & 1
        if val == 1 and last == 0:
            count += 1
        last = val
    return count


@cocotb.test()
async def test_reset(dut):
    """Test that reset clears outputs."""
    clock = Clock(dut.clk, 20, unit="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x00
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)

    # During reset, PWM should be 0 (may be X/undefined which is acceptable)
    val = dut.uo_out.value
    if not val.is_resolvable:
        pass  # X during reset is fine
    else:
        assert (val.to_unsigned() & 0x01) == 0, "PWM should be 0 during reset"

    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)


@cocotb.test()
async def test_sawtooth(dut):
    """Test sawtooth waveform produces PWM output."""
    clock = Clock(dut.clk, 20, unit="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x00
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    # Frequency: C4 (~262 Hz at 50 MHz) = 4291 = 0x10C3
    await sid_write_freq(dut, 4291)
    # Attack=0 (fastest), Decay=0
    await sid_write(dut, REG_ATTACK, 0x00)
    # Sustain=F (full), Release=0
    await sid_write(dut, REG_SUSTAIN, 0x0F)
    # Sawtooth + gate: bit5=saw, bit0=gate
    await sid_write(dut, REG_WAVEFORM, 0x21)

    # Wait for attack to ramp up and check PDM activity
    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"Sawtooth PWM count: {pdm_count}")
    assert pdm_count > 0, f"Sawtooth should produce PWM pulses, got {pdm_count}"


@cocotb.test()
async def test_triangle(dut):
    """Test triangle waveform produces PWM output."""
    clock = Clock(dut.clk, 20, unit="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x00
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    await sid_write_freq(dut, 4291)
    await sid_write(dut, REG_ATTACK, 0x00)
    await sid_write(dut, REG_SUSTAIN, 0x0F)
    # Triangle + gate: bit4=tri, bit0=gate
    await sid_write(dut, REG_WAVEFORM, 0x11)

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"Triangle PWM count: {pdm_count}")
    assert pdm_count > 0, f"Triangle should produce PWM pulses, got {pdm_count}"


@cocotb.test()
async def test_pulse(dut):
    """Test pulse waveform produces PWM output."""
    clock = Clock(dut.clk, 20, unit="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x00
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    await sid_write_freq(dut, 4291)
    # Pulse width = 50% (128 = 0x80)
    await sid_write_pw(dut, 0x80)
    await sid_write(dut, REG_ATTACK, 0x00)
    await sid_write(dut, REG_SUSTAIN, 0x0F)
    # Pulse + gate: bit6=pulse, bit0=gate
    await sid_write(dut, REG_WAVEFORM, 0x41)

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"Pulse PWM count: {pdm_count}")
    assert pdm_count > 0, f"Pulse should produce PWM pulses, got {pdm_count}"


@cocotb.test()
async def test_noise(dut):
    """Test noise waveform produces PWM output."""
    clock = Clock(dut.clk, 20, unit="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x00
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    await sid_write_freq(dut, 4291)
    await sid_write(dut, REG_ATTACK, 0x00)
    await sid_write(dut, REG_SUSTAIN, 0x0F)
    # Noise + gate: bit7=noise, bit0=gate
    await sid_write(dut, REG_WAVEFORM, 0x81)

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"Noise PWM count: {pdm_count}")
    assert pdm_count > 0, f"Noise should produce PWM pulses, got {pdm_count}"


@cocotb.test(skip=os.environ.get("GATES") == "yes")
async def test_gate_release(dut):
    """Test that releasing the gate silences PWM output. Skipped in GL sim."""
    clock = Clock(dut.clk, 20, unit="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x00
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    await sid_write_freq(dut, 4291)
    await sid_write(dut, REG_ATTACK, 0x00)
    await sid_write(dut, REG_SUSTAIN, 0x0F)  # sustain=F, release=0 (fastest)
    # Sawtooth + gate
    await sid_write(dut, REG_WAVEFORM, 0x21)

    # Let it play
    await ClockCycles(dut.clk, 200000)

    # Release gate (clear bit 0)
    await sid_write(dut, REG_WAVEFORM, 0x20)

    # Wait for release to fully complete (~2.6ms at rate 0 = 130k cycles at 50 MHz)
    await ClockCycles(dut.clk, 300000)

    # PWM should be silent
    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"After release PWM count: {pdm_count}")
    assert pdm_count == 0, f"PWM should be silent after release, got {pdm_count}"


@cocotb.test()
async def test_two_voices(dut):
    """Test that both voices play simultaneously and produce PWM output."""
    clock = Clock(dut.clk, 20, unit="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x00
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    # Voice 1: Sawtooth C4
    await sid_write_freq(dut, 4291, voice=0)
    await sid_write(dut, REG_ATTACK, 0x00, voice=0)
    await sid_write(dut, REG_SUSTAIN, 0x0F, voice=0)
    await sid_write(dut, REG_WAVEFORM, 0x21, voice=0)  # SAW + GATE

    # Voice 2: Triangle E4
    await sid_write_freq(dut, 5404, voice=1)
    await sid_write(dut, REG_ATTACK, 0x00, voice=1)
    await sid_write(dut, REG_SUSTAIN, 0x0F, voice=1)
    await sid_write(dut, REG_WAVEFORM, 0x11, voice=1)  # TRI + GATE

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"Two voices PWM count: {pdm_count}")
    assert pdm_count > 0, f"Two voices should produce PWM pulses, got {pdm_count}"


@cocotb.test()
async def test_three_voices(dut):
    """Test that all three voices play simultaneously and produce PWM output."""
    clock = Clock(dut.clk, 20, unit="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x00
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

    # Voice 1: Sawtooth C4
    await sid_write_freq(dut, 4291, voice=0)
    await sid_write(dut, REG_ATTACK, 0x00, voice=0)
    await sid_write(dut, REG_SUSTAIN, 0x0F, voice=0)
    await sid_write(dut, REG_WAVEFORM, 0x21, voice=0)  # SAW + GATE

    # Voice 2: Triangle E4
    await sid_write_freq(dut, 5404, voice=1)
    await sid_write(dut, REG_ATTACK, 0x00, voice=1)
    await sid_write(dut, REG_SUSTAIN, 0x0F, voice=1)
    await sid_write(dut, REG_WAVEFORM, 0x11, voice=1)  # TRI + GATE

    # Voice 3: Pulse G4
    await sid_write_freq(dut, 6430, voice=2)
    await sid_write_pw(dut, 0x80, voice=2)
    await sid_write(dut, REG_ATTACK, 0x00, voice=2)
    await sid_write(dut, REG_SUSTAIN, 0x0F, voice=2)
    await sid_write(dut, REG_WAVEFORM, 0x41, voice=2)  # PULSE + GATE

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"Three voices PWM count: {pdm_count}")
    assert pdm_count > 0, f"Three voices should produce PWM pulses, got {pdm_count}"
