# 8051-programming-AT89s52-ic-
This is a method used to program 8051 using arduino as isp (In Serial Programming)
<br>
Manual Has Provided
<br>
Make a hex file using any compiler which convert the embedded C file to hex file


# AT89S51/52 Programmer using Arduino

Program an Atmel AT89S51/AT89S52 microcontroller through its SPI-style
in-system programming (ISP) interface using an Arduino Uno.



## Hardware Required

- Arduino Uno
- AT89S51 or AT89S52 (DIP-40)
- 11.0592 MHz or 12 MHz crystal
- 2 x 30 pF ceramic capacitors
- Breadboard and jumper wires

## Wiring

| Arduino Uno | AT89S52 Pin | Signal          |
|-------------|-------------|-----------------|
| D5          | 6 (P1.5)    | MOSI            |
| D4          | 7 (P1.6)    | MISO            |
| D3          | 8 (P1.7)    | SCK             |
| D2          | 9           | RST (active HIGH) |
| 5V          | 40          | VCC             |
| 5V          | 31          | EA/VPP          |
| GND         | 20          | GND             |

Connect the crystal between pins 18 (XTAL2) and 19 (XTAL1), and a 30 pF
capacitor from each crystal pin to GND.

## Setup

1. Wire the circuit as shown above.
2. Open the sketch in the Arduino IDE and upload it to the Uno.
3. Set the host program's serial port to **115200 baud**.

## Serial Command Reference

| Command    | Function                                        |
|------------|-------------------------------------------------|
| `o`        | RST high (enter programming mode)               |
| `c`        | RST low (run the program)                       |
| `p`        | Send Programming Enable, returns response byte  |
| `e`        | Chip erase, returns ready byte                  |
| `a` + byte | Set low address byte                            |
| `A` + byte | Set high address byte                           |
| `d` + byte | Set data byte                                   |
| `w`        | Write data byte at current address              |
| `r`        | Read byte at current address                    |
| `S`        | Read signature byte 0                           |
| `s`        | Read signature bytes 1 and 2                    |

## Usage

1. Send `o` to pull RST high.
2. Send `p` to enable programming.
3. Send `e` to erase the chip.
4. For each byte: send `a`, `A`, `d`, then `w`.
5. Verify by sending `a`, `A`, then `r`.
6. Send `c` to pull RST low and run the program.

## Troubleshooting

- No response: check the crystal and capacitors, and make sure RST is high.
- Verify the signature bytes match your chip (see the datasheet).
- Use a common ground and a stable 5V supply.

