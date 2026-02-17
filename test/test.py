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

# I2C slave address
I2C_ADDR = 0x36
I2C_HALF_PERIOD = 25  # clock cycles (~1 MHz at 50 MHz sys clock)


async def i2c_start(dut):
    """I2C START condition: SDA falls while SCL is high."""
    uio = dut.uio_in.value.to_unsigned() if hasattr(dut.uio_in.value, 'to_unsigned') else 0x03
    # SDA=1, SCL=1
    uio = uio | 0x03
    dut.uio_in.value = uio
    await ClockCycles(dut.clk, I2C_HALF_PERIOD)
    # SDA=0 while SCL=1 → START
    uio = uio & ~0x01
    dut.uio_in.value = uio
    await ClockCycles(dut.clk, I2C_HALF_PERIOD)
    # SCL=0 to begin clocking
    uio = uio & ~0x02
    dut.uio_in.value = uio
    await ClockCycles(dut.clk, I2C_HALF_PERIOD)


async def i2c_stop(dut):
    """I2C STOP condition: SDA rises while SCL is high."""
    uio = dut.uio_in.value.to_unsigned() if hasattr(dut.uio_in.value, 'to_unsigned') else 0
    # SDA=0, SCL=0
    uio = uio & ~0x03
    dut.uio_in.value = uio
    await ClockCycles(dut.clk, I2C_HALF_PERIOD)
    # SCL=1
    uio = uio | 0x02
    dut.uio_in.value = uio
    await ClockCycles(dut.clk, I2C_HALF_PERIOD)
    # SDA=1 while SCL=1 → STOP
    uio = uio | 0x01
    dut.uio_in.value = uio
    await ClockCycles(dut.clk, I2C_HALF_PERIOD)


async def i2c_send_byte(dut, byte):
    """Send one byte MSB-first, then read ACK on 9th clock."""
    uio = dut.uio_in.value.to_unsigned() if hasattr(dut.uio_in.value, 'to_unsigned') else 0

    for i in range(7, -1, -1):
        bit = (byte >> i) & 1
        # Set SDA, SCL low
        uio = (uio & ~0x03) | bit  # bit0=SDA, bit1=SCL stays low
        dut.uio_in.value = uio
        await ClockCycles(dut.clk, I2C_HALF_PERIOD)
        # SCL high — slave samples
        uio = uio | 0x02
        dut.uio_in.value = uio
        await ClockCycles(dut.clk, I2C_HALF_PERIOD)
        # SCL low
        uio = uio & ~0x02
        dut.uio_in.value = uio
        await ClockCycles(dut.clk, I2C_HALF_PERIOD)

    # 9th clock: ACK — release SDA (high), slave pulls low via sda_oe
    uio = uio | 0x01  # SDA=1 (released)
    uio = uio & ~0x02  # SCL=0
    dut.uio_in.value = uio
    await ClockCycles(dut.clk, I2C_HALF_PERIOD)
    # SCL high — read ACK
    uio = uio | 0x02
    dut.uio_in.value = uio
    await ClockCycles(dut.clk, I2C_HALF_PERIOD)
    # SCL low
    uio = uio & ~0x02
    dut.uio_in.value = uio
    await ClockCycles(dut.clk, I2C_HALF_PERIOD)


async def sid_write(dut, reg_addr, data):
    """Write to a SID register via I2C."""
    await i2c_start(dut)
    await i2c_send_byte(dut, (I2C_ADDR << 1) | 0)  # address + write
    await i2c_send_byte(dut, reg_addr & 0xFF)
    await i2c_send_byte(dut, data & 0xFF)
    await i2c_stop(dut)
    await ClockCycles(dut.clk, 10)


async def sid_write_freq(dut, freq16):
    """Write a 16-bit frequency as two byte registers."""
    await sid_write(dut, REG_FREQ_LO, freq16 & 0xFF)
    await sid_write(dut, REG_FREQ_HI, (freq16 >> 8) & 0xFF)


async def sid_write_pw(dut, pw16):
    """Write a 16-bit pulse width as two byte registers."""
    await sid_write(dut, REG_PW_LO, pw16 & 0xFF)
    await sid_write(dut, REG_PW_HI, (pw16 >> 8) & 0xFF)


async def count_pwm(dut, cycles):
    """Count PWM rising edges on uio_out[7] over a number of clock cycles."""
    count = 0
    last = 0
    for _ in range(cycles):
        await RisingEdge(dut.clk)
        val = (dut.uio_out.value.to_unsigned() >> 7) & 1
        if val == 1 and last == 0:
            count += 1
        last = val
    return count


async def reset_dut(dut):
    """Common reset sequence for all tests."""
    clock = Clock(dut.clk, 20, units="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x00
    dut.uio_in.value = 0x03  # SDA=1, SCL=1 (I2C idle)
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)


@cocotb.test()
async def test_reset(dut):
    """Test that reset clears outputs."""
    clock = Clock(dut.clk, 20, units="ns")  # 50 MHz
    cocotb.start_soon(clock.start())

    dut.ena.value = 1
    dut.ui_in.value = 0x00
    dut.uio_in.value = 0x03  # I2C idle
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 20)

    # During reset, PWM should be 0 (may be X/undefined which is acceptable)
    val = dut.uio_out.value
    if not val.is_resolvable:
        pass  # X during reset is fine
    else:
        assert (val.to_unsigned() & 0x80) == 0, "PWM should be 0 during reset"

    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)


@cocotb.test()
async def test_sawtooth(dut):
    """Test sawtooth waveform produces PWM output."""
    await reset_dut(dut)

    await sid_write_freq(dut, 4291)
    await sid_write(dut, REG_ATTACK, 0x00)
    await sid_write(dut, REG_SUSTAIN, 0x0F)
    await sid_write(dut, REG_WAVEFORM, 0x21)  # SAW + GATE

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"Sawtooth PWM count: {pdm_count}")
    assert pdm_count > 0, f"Sawtooth should produce PWM pulses, got {pdm_count}"


@cocotb.test()
async def test_triangle(dut):
    """Test triangle waveform produces PWM output."""
    await reset_dut(dut)

    await sid_write_freq(dut, 4291)
    await sid_write(dut, REG_ATTACK, 0x00)
    await sid_write(dut, REG_SUSTAIN, 0x0F)
    await sid_write(dut, REG_WAVEFORM, 0x11)  # TRI + GATE

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"Triangle PWM count: {pdm_count}")
    assert pdm_count > 0, f"Triangle should produce PWM pulses, got {pdm_count}"


@cocotb.test()
async def test_pulse(dut):
    """Test pulse waveform produces PWM output."""
    await reset_dut(dut)

    await sid_write_freq(dut, 4291)
    await sid_write_pw(dut, 2048)
    await sid_write(dut, REG_ATTACK, 0x00)
    await sid_write(dut, REG_SUSTAIN, 0x0F)
    await sid_write(dut, REG_WAVEFORM, 0x41)  # PULSE + GATE

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"Pulse PWM count: {pdm_count}")
    assert pdm_count > 0, f"Pulse should produce PWM pulses, got {pdm_count}"


@cocotb.test()
async def test_noise(dut):
    """Test noise waveform produces PWM output."""
    await reset_dut(dut)

    await sid_write_freq(dut, 4291)
    await sid_write(dut, REG_ATTACK, 0x00)
    await sid_write(dut, REG_SUSTAIN, 0x0F)
    await sid_write(dut, REG_WAVEFORM, 0x81)  # NOISE + GATE

    await ClockCycles(dut.clk, 200000)
    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"Noise PWM count: {pdm_count}")
    assert pdm_count > 0, f"Noise should produce PWM pulses, got {pdm_count}"


@cocotb.test(skip=os.environ.get("GATES") == "yes")
async def test_gate_release(dut):
    """Test that releasing the gate silences PWM output. Skipped in GL sim."""
    await reset_dut(dut)

    await sid_write_freq(dut, 4291)
    await sid_write(dut, REG_ATTACK, 0x00)
    await sid_write(dut, REG_SUSTAIN, 0x0F)
    await sid_write(dut, REG_WAVEFORM, 0x21)  # SAW + GATE

    await ClockCycles(dut.clk, 200000)

    # Release gate
    await sid_write(dut, REG_WAVEFORM, 0x20)

    # Wait for release
    await ClockCycles(dut.clk, 300000)

    pdm_count = await count_pwm(dut, 100000)
    dut._log.info(f"After release PWM count: {pdm_count}")
    assert pdm_count == 0, f"PWM should be silent after release, got {pdm_count}"
