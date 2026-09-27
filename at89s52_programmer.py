#!/usr/bin/env python3
"""
at89s52_programmer.py

A cross-platform (no .NET needed) replacement for the "8051 SPI Programmer"
Windows GUI, talking to the same Tiktak/Nick Pablo Arduino sketch:

    PROGRAMMING AN ATMEL AT89S51/52 USING ARDUINO
    Credits to NICK PABLO for the Arduino Sketch, TIKTAK (C) 2014

Requires:
    pip install pyserial

Wiring (per the sketch):
    Arduino pin 4  -> AT89S52 MISO
    Arduino pin 5  -> AT89S52 MOSI
    Arduino pin 3  -> AT89S52 SCK
    Arduino pin 2  -> AT89S52 RST
    Arduino 5V/GND -> AT89S52 VCC/GND

Usage:
    python at89s52_programmer.py identify -p COM3
    python at89s52_programmer.py erase    -p COM3
    python at89s52_programmer.py upload   -p COM3 -f firmware.hex
    python at89s52_programmer.py verify   -p COM3 -f firmware.hex
    python at89s52_programmer.py dump     -p COM3 -o dump.hex --size 8192

If your Arduino/OS uses a different serial port name, list ports with:
    python at89s52_programmer.py ports
"""

import argparse
import sys
import time

try:
    import serial
    from serial.tools import list_ports
except ImportError:
    print("pyserial is required. Install it with:\n    pip install pyserial")
    sys.exit(1)

BAUD = 115200
RDY = 75
NRDY = 76
CHIP_SIZE_DEFAULT = 8192  # AT89S52 = 8KB flash. Use 4096 for AT89S51.


# --------------------------------------------------------------------------
# Intel HEX parsing / writing (minimal, dependency-free)
# --------------------------------------------------------------------------

def parse_intel_hex(path):
    """Return {address: byte_value} dict from an Intel HEX file."""
    mem = {}
    ext_addr = 0
    with open(path, "r") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise ValueError(f"Line {lineno}: does not start with ':'")
            data = bytes.fromhex(line[1:])
            byte_count = data[0]
            addr = (data[1] << 8) | data[2]
            rec_type = data[3]
            payload = data[4:4 + byte_count]
            checksum = data[4 + byte_count]

            calc_sum = (-(sum(data[:4 + byte_count]))) & 0xFF
            if calc_sum != checksum:
                raise ValueError(f"Line {lineno}: checksum mismatch")

            if rec_type == 0x00:  # data
                base = ext_addr + addr
                for i, b in enumerate(payload):
                    mem[base + i] = b
            elif rec_type == 0x01:  # EOF
                break
            elif rec_type == 0x02:  # extended segment address
                ext_addr = ((payload[0] << 8) | payload[1]) * 16
            elif rec_type == 0x04:  # extended linear address
                ext_addr = ((payload[0] << 8) | payload[1]) << 16
            # types 0x03/0x05 (start addresses) are ignored - not needed for flashing
    return mem


def write_intel_hex(path, mem_bytes, base_addr=0):
    """Write a bytes/bytearray object out as a simple Intel HEX file."""
    with open(path, "w") as f:
        addr = base_addr
        i = 0
        n = len(mem_bytes)
        while i < n:
            chunk = mem_bytes[i:i + 16]
            count = len(chunk)
            rec = bytearray()
            rec.append(count)
            rec.append((addr >> 8) & 0xFF)
            rec.append(addr & 0xFF)
            rec.append(0x00)
            rec.extend(chunk)
            checksum = (-(sum(rec))) & 0xFF
            rec.append(checksum)
            f.write(":" + rec.hex().upper() + "\n")
            addr += count
            i += count
        f.write(":00000001FF\n")


# --------------------------------------------------------------------------
# Programmer protocol
# --------------------------------------------------------------------------

class At89Programmer:
    def __init__(self, port, baud=BAUD, timeout=2, verbose=False):
        self.verbose = verbose
        self.ser = serial.Serial(port, baud, timeout=timeout)
        # Arduino Uno auto-resets when the serial port opens; give the
        # bootloader + sketch time to start up before talking to it.
        time.sleep(2.0)
        self.ser.reset_input_buffer()

    def close(self):
        self.ser.close()

    def _log(self, *a):
        if self.verbose:
            print(*a)

    def _send_cmd(self, ch):
        self.ser.write(ch.encode("ascii"))

    def _send_byte(self, val):
        self.ser.write(bytes([val & 0xFF]))

    def _read_byte(self, what=""):
        b = self.ser.read(1)
        if len(b) != 1:
            raise TimeoutError(f"No response from Arduino{': ' + what if what else ''}")
        return b[0]

    # -- low-level commands mirroring the sketch's switch-case -------------

    def prog_enable(self):
        """'p' -> returns the echoed sync byte from progEnable()."""
        self._send_cmd("p")
        return self._read_byte("progEnable")

    def reset_high(self):
        self._send_cmd("o")

    def reset_low(self):
        self._send_cmd("c")

    def set_address(self, addr16):
        ah = (addr16 >> 8) & 0xFF
        al = addr16 & 0xFF
        self._send_cmd("A")
        self._send_byte(ah)
        self._send_cmd("a")
        self._send_byte(al)

    def read_sig_high(self):
        """'S' -> manufacturer/signature byte at (AH=0, AL=0)."""
        self._send_cmd("S")
        return self._read_byte("SigH")

    def read_sig_low_pair(self):
        """'s' -> two signature bytes, per the sketch's fixed order."""
        self._send_cmd("s")
        b1 = self._read_byte("Sig byte 1")
        b2 = self._read_byte("Sig byte 2")
        return b1, b2

    def erase_chip(self):
        self._send_cmd("e")
        return self._read_byte("erase RDY") == RDY

    def write_byte(self, addr16, value, write_delay=0.02):
        self.set_address(addr16)
        self._send_cmd("d")
        self._send_byte(value)
        self._send_cmd("w")
        # The sketch does not send an ack after 'w'; AT89S flash needs a
        # short internal write cycle. Adjust write_delay if you see
        # verify failures (try 0.03-0.05 if bytes come back wrong).
        time.sleep(write_delay)

    def read_byte(self, addr16):
        self.set_address(addr16)
        self._send_cmd("r")
        return self._read_byte(f"read @0x{addr16:04X}")

    # -- high-level operations ---------------------------------------------

    def connect(self, retries=5):
        for i in range(retries):
            try:
                self.reset_low()
                time.sleep(0.05)
                self.reset_high()
                time.sleep(0.05)
                echo = self.prog_enable()
                self._log(f"progEnable attempt {i+1}: got 0x{echo:02X}")
                return True
            except TimeoutError:
                time.sleep(0.2)
        return False

    def identify(self):
        sig_h = self.read_sig_high()
        b1, b2 = self.read_sig_low_pair()
        return sig_h, b1, b2

    def erase(self):
        return self.erase_chip()

    def upload(self, hex_path, progress=True):
        mem = parse_intel_hex(hex_path)
        if not mem:
            raise ValueError("Hex file contains no data records")
        addrs = sorted(mem.keys())
        total = len(addrs)
        for i, addr in enumerate(addrs):
            self.write_byte(addr, mem[addr])
            if progress and (i % 64 == 0 or i == total - 1):
                pct = (i + 1) * 100 // total
                print(f"\rWriting: {pct:3d}% ({i+1}/{total})", end="", flush=True)
        if progress:
            print()
        return total

    def verify(self, hex_path, progress=True):
        mem = parse_intel_hex(hex_path)
        addrs = sorted(mem.keys())
        total = len(addrs)
        mismatches = []
        for i, addr in enumerate(addrs):
            expected = mem[addr]
            actual = self.read_byte(addr)
            if actual != expected:
                mismatches.append((addr, expected, actual))
            if progress and (i % 64 == 0 or i == total - 1):
                pct = (i + 1) * 100 // total
                print(f"\rVerifying: {pct:3d}% ({i+1}/{total})", end="", flush=True)
        if progress:
            print()
        return mismatches

    def dump(self, size, progress=True):
        out = bytearray()
        for addr in range(size):
            out.append(self.read_byte(addr))
            if progress and (addr % 256 == 0 or addr == size - 1):
                pct = (addr + 1) * 100 // size
                print(f"\rReading: {pct:3d}% ({addr+1}/{size})", end="", flush=True)
        if progress:
            print()
        return out


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def cmd_ports(args):
    ports = list(list_ports.comports())
    if not ports:
        print("No serial ports found.")
        return
    for p in ports:
        print(f"{p.device}  -  {p.description}")


def cmd_identify(args):
    prog = At89Programmer(args.port, verbose=args.verbose)
    try:
        if not prog.connect():
            print("Could not sync with the Arduino (no response to 'p'). "
                  "Check wiring, port, and that the sketch is uploaded.")
            sys.exit(1)
        sig_h, b1, b2 = prog.identify()
        print(f"Signature bytes: 0x{sig_h:02X} 0x{b1:02X} 0x{b2:02X}")
        if sig_h == 0x1E:
            print("Manufacturer byte 0x1E matches Atmel/Microchip.")
        else:
            print("Warning: manufacturer byte does not match the expected "
                  "0x1E for Atmel. Check wiring/power/connection.")
    finally:
        prog.close()


def cmd_erase(args):
    prog = At89Programmer(args.port, verbose=args.verbose)
    try:
        if not prog.connect():
            print("Could not sync with the Arduino.")
            sys.exit(1)
        print("Erasing chip...")
        ok = prog.erase()
        print("Erase complete." if ok else "Erase did not return RDY - check chip/wiring.")
    finally:
        prog.close()


def cmd_upload(args):
    prog = At89Programmer(args.port, verbose=args.verbose)
    try:
        if not prog.connect():
            print("Could not sync with the Arduino.")
            sys.exit(1)
        if not args.no_erase:
            print("Erasing chip before upload...")
            prog.erase()
        print(f"Uploading {args.file} ...")
        count = prog.upload(args.file)
        print(f"Wrote {count} bytes.")
        if not args.no_verify:
            print("Verifying...")
            mismatches = prog.verify(args.file)
            if mismatches:
                print(f"VERIFY FAILED: {len(mismatches)} mismatch(es), e.g.:")
                for addr, exp, act in mismatches[:10]:
                    print(f"  0x{addr:04X}: expected 0x{exp:02X}, got 0x{act:02X}")
                sys.exit(2)
            else:
                print("Verify OK.")
    finally:
        prog.close()


def cmd_verify(args):
    prog = At89Programmer(args.port, verbose=args.verbose)
    try:
        if not prog.connect():
            print("Could not sync with the Arduino.")
            sys.exit(1)
        mismatches = prog.verify(args.file)
        if mismatches:
            print(f"VERIFY FAILED: {len(mismatches)} mismatch(es), e.g.:")
            for addr, exp, act in mismatches[:10]:
                print(f"  0x{addr:04X}: expected 0x{exp:02X}, got 0x{act:02X}")
            sys.exit(2)
        print("Verify OK.")
    finally:
        prog.close()


def cmd_dump(args):
    prog = At89Programmer(args.port, verbose=args.verbose)
    try:
        if not prog.connect():
            print("Could not sync with the Arduino.")
            sys.exit(1)
        data = prog.dump(args.size)
        write_intel_hex(args.output, data)
        print(f"Dumped {args.size} bytes to {args.output}")
    finally:
        prog.close()


def main():
    ap = argparse.ArgumentParser(description="AT89S51/52 Arduino SPI programmer (Tiktak protocol)")
    sub = ap.add_subparsers(dest="command", required=True)

    sp = sub.add_parser("ports", help="List available serial ports")
    sp.set_defaults(func=cmd_ports)

    common_args = argparse.ArgumentParser(add_help=False)
    common_args.add_argument("-p", "--port", required=True, help="Serial port, e.g. COM3 or /dev/ttyUSB0")
    common_args.add_argument("-v", "--verbose", action="store_true")

    sp = sub.add_parser("identify", parents=[common_args], help="Read and print chip signature bytes")
    sp.set_defaults(func=cmd_identify)

    sp = sub.add_parser("erase", parents=[common_args], help="Erase the chip")
    sp.set_defaults(func=cmd_erase)

    sp = sub.add_parser("upload", parents=[common_args], help="Erase, write, and verify a hex file")
    sp.add_argument("-f", "--file", required=True, help="Intel HEX file to upload")
    sp.add_argument("--no-erase", action="store_true", help="Skip erasing before upload")
    sp.add_argument("--no-verify", action="store_true", help="Skip verification after upload")
    sp.set_defaults(func=cmd_upload)

    sp = sub.add_parser("verify", parents=[common_args], help="Verify chip contents against a hex file")
    sp.add_argument("-f", "--file", required=True, help="Intel HEX file to verify against")
    sp.set_defaults(func=cmd_verify)

    sp = sub.add_parser("dump", parents=[common_args], help="Read the whole chip out to a hex file")
    sp.add_argument("-o", "--output", required=True, help="Output hex file path")
    sp.add_argument("--size", type=int, default=CHIP_SIZE_DEFAULT, help="Bytes to read (default 8192 for AT89S52)")
    sp.set_defaults(func=cmd_dump)

    args = ap.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
