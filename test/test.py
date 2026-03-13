# SPDX-License-Identifier: Apache-2.0

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge


# Register addresses (per-voice: voice_sel 0-2)
REG0_FREQ_LO  = 0
REG0_FREQ_HI  = 1
REG0_PW_LO    = 2
REG0_PW_HI    = 3
REG0_WAVEFORM = 4
REG0_ATTACK   = 5
REG0_SUSTAIN  = 6

REG1_FREQ_LO  = 7
REG1_FREQ_HI  = 8
REG1_PW_LO    = 9
REG1_PW_HI    = 10 
REG1_WAVEFORM = 11
REG1_ATTACK   = 12
REG1_SUSTAIN  = 13

REG2_FREQ_LO  = 14
REG2_FREQ_HI  = 15
REG2_PW_LO    = 16
REG2_PW_HI    = 17
REG2_WAVEFORM = 18 
REG2_ATTACK   = 19
REG2_SUSTAIN  = 20

# Filter registers (voice_sel 3)
REG_FC_LO    = 21 
REG_FC_HI    = 22
REG_RES_FILT = 23
REG_MODE_VOL = 24

# SID-compatible waveform bits ($d404 layout)
GATE  = 0x01
SYNC  = 0x02
RMOD  = 0x04
TEST  = 0x08
TRI   = 0x10
SAW   = 0x20
PULSE = 0x40
NOISE = 0x80


async def sid_write(dut, reg_addr, data):
    """Write to a SID register via flat memory interface."""
    ui = reg_addr 
    dut.ui_in.value = ui
    dut.uio_in.value = data & 0xFF
    await RisingEdge(dut.clk)
    dut.ui_in.value = ui | 0x80
    await RisingEdge(dut.clk)
    dut.ui_in.value = ui & 0x7F
    await RisingEdge(dut.clk)


async def sid_write_freq(dut, freq16, voice = 0):
    """Write a 16-bit frequency register (low byte then high byte)."""
    if(voice == 0):
        await sid_write(dut, REG0_FREQ_LO, freq16 & 0xFF)
        await sid_write(dut, REG0_FREQ_HI, (freq16 >> 8) & 0xFF)
    elif(voice == 1):
        await sid_write(dut, REG1_FREQ_LO, freq16 & 0xFF)
        await sid_write(dut, REG1_FREQ_HI, (freq16 >> 8) & 0xFF)
    elif(voice == 2):
        await sid_write(dut, REG2_FREQ_LO, freq16 & 0xFF)
        await sid_write(dut, REG2_FREQ_HI, (freq16 >> 8) & 0xFF)

async def sid_write_pw(dut, pw8, voice=0):
    """Write the 8-bit pulse width register (per voice)."""
    if(voice == 0):
        await sid_write(dut, REG0_PW, pw8 & 0xFF)
    elif(voice == 1):
        await sid_write(dut, REG1_PW, pw8 & 0xFF)
    elif(voice == 2):
        await sid_write(dut, REG2_PW, pw8 & 0xFF)


def hz_to_freq(hz):
    """Convert Hz to 16-bit frequency register value.
    24-bit accumulator at 1 MHz effective: freq_reg = hz * 2^24 / 1e6"""
    return max(1, min(65535, round(hz * (2**24) / 1e6)))


async def count_pwm(dut, cycles):
    """Count PWM rising edges on uo_out[0]."""
    count = 0
    last = 0
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        val = (dut.uo_out.value.to_unsigned()) & 1
        if val == 1 and last == 0:
            count += 1
        last = val
    return count


async def setup_and_reset(dut):
    """Common setup: start 12 MHz clock, reset, and configure bypass path."""
    clock = Clock(dut.clk, 84, unit="ns")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 100)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)
    # Explicitly set bypass path: mode=0 (bypass), vol=max
    # This ensures analog macros (black boxes in GL sim) are not in the signal path
    await sid_write(dut, REG_MODE_VOL, 0x0F, voice=VOICE_FILT)


@cocotb.test()
async def test_reset(dut):
    """Test that reset clears outputs."""
    clock = Clock(dut.clk, 84, unit="ns")
    cocotb.start_soon(clock.start())
    dut.ena.value = 1
    dut.ui_in.value = 0
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 100)
    val = dut.uo_out.value
    if not val.is_resolvable:
        pass
    else:
        assert (val.to_unsigned() & 0x01) == 0, "PWM should be 0 during reset"
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 50)


@cocotb.test()
async def test_sawtooth(dut):
    """Test sawtooth waveform produces PWM output."""
    await setup_and_reset(dut)

    await sid_write_freq(dut, hz_to_freq(262))
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0xF0)
    await sid_write(dut, REG0_WAVEFORM, SAW | GATE)
    await ClockCycles(dut.clk, 250000)
    pdm_count = await count_pwm(dut, 25000)
    dut._log.info(f"Sawtooth PWM count: {pdm_count}")
    assert pdm_count > 0


@cocotb.test()
async def test_triangle(dut):
    """Test triangle waveform produces PWM output."""
    await setup_and_reset(dut)

    await sid_write_freq(dut, hz_to_freq(262))
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0xF0)
    await sid_write(dut, REG0_WAVEFORM, TRI | GATE)
    await ClockCycles(dut.clk, 250000)
    pdm_count = await count_pwm(dut, 25000)
    dut._log.info(f"Triangle PWM count: {pdm_count}")
    assert pdm_count > 0


@cocotb.test()
async def test_pulse(dut):
    """Test pulse waveform produces PWM output."""
    await setup_and_reset(dut)

    await sid_write_freq(dut, hz_to_freq(262))
    await sid_write_pw(dut, 0x80, voice=0)
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0xF0)
    await sid_write(dut, REG0_WAVEFORM, PULSE | GATE)
    await ClockCycles(dut.clk, 250000)
    pdm_count = await count_pwm(dut, 25000)
    dut._log.info(f"Pulse PWM count: {pdm_count}")
    assert pdm_count > 0


@cocotb.test()
async def test_noise(dut):
    """Test noise waveform produces PWM output."""
    await setup_and_reset(dut)

    await sid_write_freq(dut, hz_to_freq(262))
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0xF0)
    await sid_write(dut, REG0_WAVEFORM, NOISE | GATE)
    await ClockCycles(dut.clk, 250000)
    pdm_count = await count_pwm(dut, 25000)
    dut._log.info(f"Noise PWM count: {pdm_count}")
    assert pdm_count > 0


@cocotb.test()
async def test_gate_release(dut):
    """Test that releasing the gate silences PWM output."""
    await setup_and_reset(dut)

    await sid_write_freq(dut, hz_to_freq(262))
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0xF0)
    await sid_write(dut, REG0_WAVEFORM, SAW | GATE)
    await ClockCycles(dut.clk, 250000)
    await sid_write(dut, REG_WAVEFORM, SAW)  # release gate
    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pwm(dut, 25000)
    dut._log.info(f"After release PWM count: {pdm_count}")
    assert pdm_count == 0


@cocotb.test()
async def test_two_voices(dut):
    """Test two voices playing simultaneously with per-voice ADSR."""
    await setup_and_reset(dut)

    await sid_write_freq(dut, hz_to_freq(262))
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0xF0)
    await sid_write(dut, REG_WAVEFORM, SAW | GATE, voice=0)

    await sid_write_freq(dut, hz_to_freq(330), voice=1)
    await sid_write_pw(dut, 0x80, voice=1)
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0x0F)
    await sid_write(dut, REG0_WAVEFORM, PULSE | GATE, voice=1)

    await ClockCycles(dut.clk, 250000)
    pdm_count = await count_pwm(dut, 25000)
    dut._log.info(f"Two voices PWM count: {pdm_count}")
    assert pdm_count > 0


@cocotb.test()
async def test_three_voices(dut):
    """Test three voices playing simultaneously."""
    await setup_and_reset(dut)

    # V0: sawtooth C4
    await sid_write_freq(dut, hz_to_freq(262))
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0xF0)
    await sid_write(dut, REG0_WAVEFORM, SAW | GATE, voice=0)

    # V1: pulse E4
    await sid_write_freq(dut, hz_to_freq(330), voice=1)
    await sid_write_pw(dut, 0x80, voice=1)
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0x0F)
    await sid_write(dut, REG0_WAVEFORM, PULSE | GATE)

    # V2: triangle G4
    await sid_write_freq(dut, hz_to_freq(392), voice=2)
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0x0F)
    await sid_write(dut, REG0_WAVEFORM, TRI | GATE)

    await ClockCycles(dut.clk, 250000)
    pdm_count = await count_pwm(dut, 25000)
    dut._log.info(f"Three voices PWM count: {pdm_count}")
    assert pdm_count > 0


@cocotb.test()
async def test_sync_modulation(dut):
    """Test sync modulation between voices."""
    await setup_and_reset(dut)

    # V0: master oscillator (high freq sawtooth)
    await sid_write_freq(dut, hz_to_freq(524))
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0xF0)
    await sid_write(dut, REG0_WAVEFORM, SAW | GATE)

    # V1: slave with sync (lower freq, synced to V0)
    await sid_write_freq(dut, hz_to_freq(262), voice=1)
    await sid_write(dut, REG1_ATTACK, 0x00)
    await sid_write(dut, REG1_SUSTAIN, 0x0F)
    await sid_write(dut, REG1_WAVEFORM, SAW | SYNC | GATE)

    await ClockCycles(dut.clk, 250000)
    pdm_count = await count_pwm(dut, 25000)
    dut._log.info(f"Sync modulation PWM count: {pdm_count}")
    assert pdm_count > 0


@cocotb.test()
async def test_per_voice_adsr(dut):
    """Test per-voice ADSR with different settings per voice."""
    await setup_and_reset(dut)

    # V0: fast attack, high sustain
    await sid_write_freq(dut, hz_to_freq(262))
    await sid_write(dut, REG0_ATTACK, 0x00)
    await sid_write(dut, REG0_SUSTAIN, 0xF0)
    await sid_write(dut, REG0_WAVEFORM, SAW | GATE)

    # V1: fast attack, low sustain (different ADSR)
    await sid_write_freq(dut, hz_to_freq(330), voice=1)
    await sid_write(dut, REG1_ATTACK, 0x00)
    await sid_write(dut, REG1_SUSTAIN, 0x30)
    await sid_write(dut, REG1_WAVEFORM, SAW | GATE)

    await ClockCycles(dut.clk, 250000)
    pdm_count = await count_pwm(dut, 25000)
    dut._log.info(f"Per-voice ADSR PWM count: {pdm_count}")
    assert pdm_count > 0
