# PD-Firmware-Finder

**TPS65994 USB Power Delivery Firmware Extraction and Programming Tool**

This project provides comprehensive tools for extracting TPS65994 power delivery controller configurations from Lenovo BIOS files and reprogramming salvaged chips.

## Overview

- 🔍 **Extract CST1 configs** from Lenovo BIOS files (.CAP format)
- 📋 **Parse USB PD capabilities** and device configuration
- 💾 **Dump device firmware** via I2C for backup
- 🔧 **Program salvaged chips** with extracted configurations
- ✅ **Full workflow automation** with verification

## Quick Start

### Prerequisites

```bash
# Install Python dependencies
pip install -r requirements.txt

# For I2C programming (Linux)
sudo apt-get install python3-dev i2c-tools
sudo modprobe i2c-dev

# For Raspberry Pi I2C support
sudo modprobe i2c-bcm2835
```

### Installation

```bash
git clone https://github.com/Tech1323/PD-Firmware-Finder.git
cd PD-Firmware-Finder
```

## Usage

### 1. Extract CST1 Configuration from BIOS

Extract the TPS65994 configuration bundle from a Lenovo BIOS file:

```bash
python3 pd_firmware_finder.py EHCN71WW.cap --extract-cst1 config.bin -v
```

This will:
- Locate the CST1 magic marker in the BIOS file
- Parse all configuration registers
- Display human-readable register values
- Save the binary config to `config.bin`

**Output includes:**
- Firmware version
- USB PD capabilities and power profiles
- Port configuration (Sink/Source/DRP)
- I2C address and device settings
- Charger detection and thermal configuration

### 2. Scan BIOS for Firmware Structures (Full Analysis)

Run complete scan to find all PD firmware markers:

```bash
python3 pd_firmware_finder.py EHCN71WW.cap -v
```

**Scans for:**
- TPS65994 signatures (TPS6, TI headers)
- Lenovo BIOS markers
- Firmware headers (ELF, PE, Intel HEX)
- High-entropy firmware regions

### 3. Detect Connected Device

Check if TPS65994 is detected on I2C bus:

```bash
python3 tps65994_programmer_integration.py --verbose detect --bus 1
```

**Output:**
```
Device: TPS65994
Firmware: 1.2
Address: 0x21
Bus: 1
```

### 4. Backup Current Device Firmware

Create a backup of the chip's current configuration before reprogramming:

```bash
python3 tps65994_programmer_integration.py --verbose dump --bus 1 --address 0x21 --output backup.bin
```

Accepts both hex and decimal addresses:
- `--address 0x21` (hex)
- `--address 33` (decimal)

### 5. Program Device with Extracted Config

Write the extracted CST1 config to the device:

```bash
python3 tps65994_programmer_integration.py --verbose program --bus 1 --address 0x21 --config config.bin
```

### 6. Full Automated Workflow ⭐

Extract from BIOS and program device in one command:

```bash
python3 tps65994_programmer_integration.py --verbose workflow EHCN71WW.cap --bus 1 --address 0x21
```

**Workflow steps:**
1. ✅ Detect device on I2C bus
2. ✅ Backup current firmware (`device_backup_0x21.bin`)
3. ✅ Extract CST1 from BIOS file (`extracted_cst1.bin`)
4. ✅ Program device with new config
5. ✅ Verify programming success

**Skip backup if not needed:**
```bash
python3 tps65994_programmer_integration.py --verbose workflow EHCN71WW.cap --bus 1 --address 0x21 --no-backup
```

## Command Reference

### pd_firmware_finder.py

Extract and analyze TPS65994 firmware from BIOS files.

```bash
python3 pd_firmware_finder.py BIOS_FILE [OPTIONS]

Options:
  -v, --verbose              Show detailed scan output
  --extract-cst1 OUTPUT.bin  Extract CST1 config bundle to binary file
  -e OFFSET                  Extract section at specific offset
  -s SIZE                    Size of section to extract (default: 512)
  -o OUTPUT                  Save hex dump to file
```

**Examples:**
```bash
# Extract CST1 config from BIOS
python3 pd_firmware_finder.py EHCN71WW.cap --extract-cst1 config.bin

# Scan and show detailed output
python3 pd_firmware_finder.py EHCN81WW.cap -v

# Extract specific offset
python3 pd_firmware_finder.py EHCN71WW.cap -e 0x123456 -s 1024 -o dump.txt
```

### tps65994_programmer_integration.py

Full integration tool for chip detection, backup, and programming.

```bash
python3 tps65994_programmer_integration.py [GLOBAL OPTIONS] COMMAND [COMMAND OPTIONS]

Global Options:
  -v, --verbose                    Verbose output
  --finder-script PATH             Path to pd_firmware_finder.py
  --programmer-script PATH         Path to tps6599x_programmer.py

Commands:
  detect [--bus N] [--address ADDR]
  dump --bus N --address ADDR --output FILE
  extract BIOS_FILE --output FILE
  program --bus N --address ADDR --config FILE [--no-verify]
  workflow BIOS_FILE --bus N --address ADDR [--no-backup]
```

**Address formats:**
- Hex: `--address 0x21`
- Decimal: `--address 33`

**Examples:**
```bash
# Detect device
python3 tps65994_programmer_integration.py --verbose detect --bus 1

# Dump firmware backup
python3 tps65994_programmer_integration.py dump --bus 1 --address 0x21 --output backup.bin

# Extract config from BIOS
python3 tps65994_programmer_integration.py extract EHCN71WW.cap --output config.bin

# Program device (with verification)
python3 tps65994_programmer_integration.py program --bus 1 --address 0x21 --config config.bin

# Program without verification
python3 tps65994_programmer_integration.py program --bus 1 --address 0x21 --config config.bin --no-verify

# Full workflow
python3 tps65994_programmer_integration.py --verbose workflow EHCN71WW.cap --bus 1 --address 0x21

# Workflow without backup
python3 tps65994_programmer_integration.py --verbose workflow EHCN71WW.cap --bus 1 --address 0x21 --no-backup
```

## I2C Bus Detection

### List available I2C buses (Linux)

```bash
i2cdetect -l
```

### Scan for devices on bus 1

```bash
i2cdetect -y 1
```

**Output example:**
```
     0  1  2  3  4  5  6  7  8  9  a  b  c  d  e  f
00:                         -- -- -- -- -- -- -- -- 
10: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
20: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
30: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
40: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
50: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
60: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- 
70: -- -- -- -- -- -- -- -- -- -- -- -- -- -- -- --
```

Look for `UU` which indicates a detected device.

## TPS65994 Addresses

```
TPS65993 → 0x20 (32 decimal)
TPS65994 → 0x21 (33 decimal)
TPS65991 → 0x22 (34 decimal)
TPS65992 → 0x23 (35 decimal)
```

## Supported Devices

- ✅ Lenovo ThinkPad (EHCN series BIOS)
- ✅ TPS65993, TPS65994, TPS65991, TPS65992
- ✅ Requires I2C adapter (CH340, FT232H, Raspberry Pi, etc.)

## Output Files

After running commands, you'll have:

- `config.bin` - Extracted CST1 configuration
- `device_backup_0x21.bin` - Backup of current device firmware
- `extracted_cst1.bin` - CST1 bundle from workflow
- `device_backup_0x21.bin` - Device backup from workflow

## Register Map

The CST1 configuration bundle contains these key registers:

| Register | Name | Purpose |
|----------|------|---------|
| 0x06 | FW_VERSION | Firmware version string |
| 0x23 | PORT_CONFIG | USB Type-C port role (Sink/Source/DRP) |
| 0x32 | TX_SINK_CAPS1 | USB PD sink capabilities |
| 0x37 | PD_CONFIG | USB PD protocol configuration |
| 0x52 | I2C_CONFIG | I2C device address and settings |
| 0x56 | SYS_CONFIG | System configuration |

See `pd_firmware_finder.py` for complete register map.

## Troubleshooting

### I2C device not found

```bash
# Check if I2C modules are loaded
lsmod | grep i2c

# Load modules if needed
sudo modprobe i2c-dev
sudo modprobe i2c-bcm2835  # Raspberry Pi
```

### Permission denied on I2C bus

```bash
# Add user to i2c group
sudo usermod -aG i2c $USER
# Log out and back in for group change to take effect
```

### Device detected but programming fails

- Check I2C wiring and connection
- Verify device address with `i2cdetect -y 1`
- Try dumping current firmware first to verify connection
- Check power supply to device

## Related Projects

- [tps6599x-programmer](https://github.com/Tech1323/tps6599x-programmer) - Low-level I2C programmer
- [Lenovo ThinkPad PD Controller Research](https://github.com/Tech1323) - Community research

## License

MIT License - See LICENSE file

## Contributing

Contributions welcome! Please ensure:
- Code follows Python style guidelines
- Add tests for new features
- Update README with new commands
- Document register definitions

## References

- TPS65994 Datasheet (Texas Instruments)
- Lenovo ThinkPad BIOS update documentation
- USB Power Delivery Specification (USB-IF)
