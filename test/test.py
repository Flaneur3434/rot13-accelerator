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


async def wait_data_valid(dut, timeout_cycles=10000):
    """Wait for data_valid strobe (uio_out[0]) to pulse high."""
    for _ in range(timeout_cycles):
        await RisingEdge(dut.clk)
        if dut.uio_out.value & 1:
            return
    raise TimeoutError("data_valid never asserted")


@cocotb.test()
async def test_project(dut):
    dut._log.info("Start")

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

    # "Uryyb" ROT13-decodes to "Hello"
    ciphertext = "Uryyb"
    expected = "Hello"

    for cipher_char, expected_char in zip(ciphertext, expected):
        dut._log.info(f"Sending '{cipher_char}', expecting '{expected_char}'")
        await uart_send(dut, ord(cipher_char))
        await wait_data_valid(dut)
        result = chr(dut.uo_out.value)
        dut._log.info(f"Got '{result}'")
        assert result == expected_char, f"Expected '{expected_char}', got '{result}'"

    dut._log.info("PASS: All characters decoded correctly")
