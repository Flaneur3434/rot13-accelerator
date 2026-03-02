<!---

This file is used to generate your project datasheet. Please fill in the information below and delete any unused
sections.

You can also include images in this folder and reference them in the markdown. Each image must be less than
512 kb in size, and the combined size of all images must be less than 1 MB.
-->

## How it works

ROT13 is a simple Caesar Cipher that replaces each latin alphabet letter with the 13th letter after it, wrapping around at the end of the alphabet.

This module uses UART to receive a stream of cipher text from a host computer. UART is a simple asynchronous serial communication protocol that easy to implement. There needs to be a set baud rate that the transmitter and receiver device agree upon for communication to occur. In our design we will use 115200 baud. Baud is the unit of characters per second. Hertz and baud are numerically equivalent for UART. This value was chosen because it is the fastest common UART baud rate. We want a fast baud rate because if we use a slower value the clock divider becomes larger, taking up precious space on the chip.

The UART scheme we will use is 8N1, which means:
- 8 data bits (a full byte)
- No parity (no error checking)
- 1 stop bit (marks the end of a character)
```
Idle | Start | D0 D1 D2 D3 D4 D5 D6 D7 | Stop | Idle
  1      0        (8 data bits)          1
```

Our module will first deserialize the UART stream from the host received on `ui[0]`, then use a ROT13 algorithm implemented using combinational logic to decode the received byte. Finally, it will latch the decoded byte into a 8-bit register and drive it through `uo[0]`-`uo[7]`. A single cycle `data_valid` strobe is asserted on `uio[0]` to indicate that a new valid byte is available.

We use parallel output because we would need to implement another TX UART state machine to serialize the output. It also simplifies testing, because our test harness can just read the output pins directly instead of having to deserialize a UART stream.

## How to test

We will use cocobt framework to test our simulated DUT. We will write a simple python function to create UART frames to send to our DUT. We use `ClockCycles` to hold the correct bit value for 434 clock cycles to match the UART baud rate.

```python
CLOCKS_PER_BIT = 50_000_000 // 115200 # 434 clock cycles

async def uart_send(dut, byte):
    # start bit
    bits = [0]
    # 8 data bits, LSB first
    bits += [(byte >> i) & 1 for i in range(8)]
    # stop bit
    bits += [1]
    
    for bit in bits:
        dut.ui_in.value = bit
        await ClockCycles(dut.clk, CLOCKS_PER_BIT)
```

We will assert that decrypted cipher is correct.
```python
for char in "Uryyb":
    # convert ASCII characters into integer code point for hardware
    await uart_send(dut, ord(char))
    # read parallel output
    assert chr(dut.uo_out.value) in "Hello"
```

## External hardware

None
