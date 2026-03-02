# SPDX-FileCopyrightText: © 2024 Tiny Tapeout
# SPDX-License-Identifier: Apache-2.0

import codecs

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles, RisingEdge

CLK_FREQ = 50_000_000

BAUD_RATE = 115200
CLOCKS_PER_BIT = CLK_FREQ // BAUD_RATE  # ~434

def rot13(text):
    return codecs.encode(text, 'rot_13')

async def reset_dut(dut):
    # 50 MHz clock (20 ns period)
    clock = Clock(dut.clk, 20, unit="ns")
    cocotb.start_soon(clock.start())

    # Reset
    dut._log.info("Reset")
    dut.ena.value = 1
    dut.ui_in.value = 1  # UART idle is high
    dut.uio_in.value = 0
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 10)
    dut.rst_n.value = 1
    await ClockCycles(dut.clk, 10)

async def uart_send(dut, byte):
    """Send a single byte over UART (8N1) by bit-banging ui[0]."""
    # Start bit (low)
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, CLOCKS_PER_BIT)

    # 8 data bits, LSB first
    for i in range(8):
        bit = (byte >> i) & 1
        dut.ui_in.value = bit
        await ClockCycles(dut.clk, CLOCKS_PER_BIT)

    # Stop bit (high)
    dut.ui_in.value = 1
    await ClockCycles(dut.clk, CLOCKS_PER_BIT)

async def broken_uart_send(dut, byte):
    """Send a single byte over inside a broken UART frame."""
    # Start bit (low)
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, CLOCKS_PER_BIT)

    # 8 data bits, LSB first
    for i in range(8):
        bit = (byte >> i) & 1
        dut.ui_in.value = bit
        await ClockCycles(dut.clk, CLOCKS_PER_BIT)

    # Broken stop bit (low)
    dut.ui_in.value = 0
    await ClockCycles(dut.clk, CLOCKS_PER_BIT)


async def wait_data_valid(dut, timeout_cycles=10000):
    """Wait for data_valid strobe (uio_out[0]) to pulse high."""
    for _ in range(timeout_cycles):
        await RisingEdge(dut.clk)
        if int(dut.uio_out.value) & 1:
            return
    raise TimeoutError("data_valid never asserted")


@cocotb.test()
async def test_correctness(dut):
    """Check correctness using a simple test."""
    dut._log.info("Start")

    await reset_dut(dut)

    # ROT13-encode "Hello World" so the hardware decoder produces it back
    expected = "Hello World"
    ciphertext = rot13(expected)

    for cipher_char, expected_char in zip(ciphertext, expected):
        dut._log.info(f"Sending '{cipher_char}', expecting '{expected_char}'")
        # Start watching for data_valid BEFORE sending, since the strobe
        # fires during the stop bit (before uart_send returns).
        valid_task = cocotb.start_soon(wait_data_valid(dut))
        await uart_send(dut, ord(cipher_char))
        await valid_task
        result = chr(int(dut.uo_out.value))
        dut._log.info(f"Got '{result}'")
        assert result == expected_char, f"Expected '{expected_char}', got '{result}'"

    dut._log.info("PASS: All characters decoded correctly")

@cocotb.test()
async def test_non_alpha_passthrough(dut):
    """Non-alphabetic characters should pass through unchanged."""
    dut._log.info("Start")

    await reset_dut(dut)

    non_alpha = "123 !@#"

    for char in non_alpha:
        dut._log.info(f"Sending '{char}', expecting passthrough '{char}'")
        valid_task = cocotb.start_soon(wait_data_valid(dut))
        await uart_send(dut, ord(char))
        await valid_task
        result = chr(int(dut.uo_out.value))
        dut._log.info(f"Got '{result}'")
        assert result == char, f"Expected '{char}', got '{result}'"

@cocotb.test()
async def test_bad_uart_frame(dut):
    """Test that module can recover from bad frames and won't output garbage."""
    dut._log.info("Start")

    await reset_dut(dut)

    # ROT13-encode "Hello" so the hardware decoder produces it back
    expected = "Hello"
    ciphertext = rot13(expected)

    async def assert_data_not_valid(dut, wait_cycles=5000):
        for _ in range(wait_cycles):
            await RisingEdge(dut.clk)
            assert not (int(dut.uio_out.value) & 1), "data_valid was unexpectedly asserted"

    # Send first byte inside broken UART frame
    dut._log.info(f"Sending '{ciphertext[0]}' inside broken UART, expecting no output")
    await broken_uart_send(dut, ord(ciphertext[0]))
    await assert_data_not_valid(dut)

    # Line is still low from the broken frame. The hardware should
    # wait for it to go idle on its own before accepting new data.
    dut.ui_in.value = 1  # Transmitter returns line to idle
    await ClockCycles(dut.clk, CLOCKS_PER_BIT)

    for cipher_char, expected_char in zip(ciphertext[1:], expected[1:]):
        dut._log.info(f"Sending '{cipher_char}', expecting '{expected_char}'")
        # Start watching for data_valid BEFORE sending, since the strobe
        # fires during the stop bit (before uart_send returns).
        valid_task = cocotb.start_soon(wait_data_valid(dut))
        await uart_send(dut, ord(cipher_char))
        await valid_task
        result = chr(int(dut.uo_out.value))
        dut._log.info(f"Got '{result}'")
        assert result == expected_char, f"Expected '{expected_char}', got '{result}'"
