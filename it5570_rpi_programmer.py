#!/usr/bin/env python3
"""
IT5570 USB PD Controller Programmer for Raspberry Pi
Supports: Dump, Erase, and Flash operations via SPI/I2C
Compatible with: Raspberry Pi 3/4/5
"""

import sys
import argparse
import logging
import time
import hashlib
from pathlib import Path
from enum import Enum
from typing import Optional, Tuple, List
from dataclasses import dataclass

try:
    import RPi.GPIO as GPIO
    HAS_GPIO = True
except ImportError:
    HAS_GPIO = False
    print("Warning: RPi.GPIO not installed. Install with: sudo pip install RPi.GPIO")

try:
    import spidev
    HAS_SPIDEV = True
except ImportError:
    HAS_SPIDEV = False
    print("Warning: spidev not installed. Install with: sudo pip install spidev")

try:
    import smbus2
    HAS_SMBUS = True
except ImportError:
    HAS_SMBUS = False
    print("Warning: smbus2 not installed. Install with: pip install smbus2")


# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class IT5570Interface(Enum):
    """IT5570 communication interface options"""
    SPI = "spi"
    I2C = "i2c"


class IT5570Memory(Enum):
    """IT5570 memory regions"""
    FLASH = 0x00
    EEPROM = 0x01
    RAM = 0x02


@dataclass
class IT5570Config:
    """IT5570 chip configuration"""
    interface: IT5570Interface
    bus: int = 1
    address: int = 0x60  # Default I2C address for IT5570
    spi_bus: int = 0
    spi_device: int = 0
    spi_speed: int = 1000000  # 1MHz default
    chip_select_pin: int = 8  # GPIO pin for chip select
    reset_pin: int = 7  # GPIO pin for reset


@dataclass
class IT5570Info:
    """Device information structure"""
    device_id: str
    firmware_version: str
    memory_size: int
    page_size: int
    interface: IT5570Interface
    address: int


class IT5570Programmer:
    """Main programmer class for IT5570 devices"""
    
    # IT5570 Command Set (from datasheet)
    CMD_READ_ID = 0x9F
    CMD_READ_STATUS = 0x05
    CMD_WRITE_STATUS = 0x01
    CMD_READ_DATA = 0x03
    CMD_FAST_READ = 0x0B
    CMD_PAGE_PROGRAM = 0x02
    CMD_SECTOR_ERASE = 0x20
    CMD_BLOCK_ERASE_32K = 0x52
    CMD_BLOCK_ERASE_64K = 0xD8
    CMD_CHIP_ERASE = 0xC7
    CMD_WRITE_ENABLE = 0x06
    CMD_WRITE_DISABLE = 0x04
    CMD_POWER_DOWN = 0xB9
    CMD_RELEASE_POWER_DOWN = 0xAB
    
    # Memory configuration
    FLASH_SIZE = 0x100000  # 1MB
    PAGE_SIZE = 256
    SECTOR_SIZE = 0x1000  # 4KB
    BLOCK_SIZE_64K = 0x10000  # 64KB
    
    # Timeouts
    PAGE_WRITE_TIMEOUT = 5  # seconds
    SECTOR_ERASE_TIMEOUT = 30  # seconds
    CHIP_ERASE_TIMEOUT = 120  # seconds
    
    def __init__(self, config: IT5570Config, verbose: bool = False):
        """
        Initialize the programmer
        
        Args:
            config: IT5570Config instance
            verbose: Enable verbose logging
        """
        self.config = config
        self.verbose = verbose
        self.device = None
        self.bus = None
        
        if verbose:
            logger.setLevel(logging.DEBUG)
        
        # Validate dependencies
        if config.interface == IT5570Interface.SPI:
            if not HAS_SPIDEV or not HAS_GPIO:
                raise RuntimeError("SPI requires spidev and RPi.GPIO")
        elif config.interface == IT5570Interface.I2C:
            if not HAS_SMBUS:
                raise RuntimeError("I2C requires smbus2")
    
    def connect(self) -> bool:
        """
        Connect to the IT5570 device
        
        Returns:
            True if connection successful
        """
        try:
            if self.config.interface == IT5570Interface.SPI:
                return self._connect_spi()
            elif self.config.interface == IT5570Interface.I2C:
                return self._connect_i2c()
        except Exception as e:
            logger.error(f"Connection failed: {e}")
            return False
    
    def _connect_spi(self) -> bool:
        """Connect via SPI"""
        try:
            # Setup GPIO for chip select and reset
            GPIO.setmode(GPIO.BCM)
            GPIO.setwarnings(False)
            GPIO.setup(self.config.chip_select_pin, GPIO.OUT, initial=GPIO.HIGH)
            GPIO.setup(self.config.reset_pin, GPIO.OUT, initial=GPIO.HIGH)
            
            # Initialize SPI
            self.device = spidev.SpiDev()
            self.device.open(self.config.spi_bus, self.config.spi_device)
            self.device.max_speed_hz = self.config.spi_speed
            
            logger.info(f"Connected to IT5570 via SPI (bus={self.config.spi_bus}, device={self.config.spi_device}, speed={self.config.spi_speed}Hz)")
            
            # Reset device
            self._reset_device()
            time.sleep(0.1)
            
            return True
        except Exception as e:
            logger.error(f"SPI connection failed: {e}")
            return False
    
    def _connect_i2c(self) -> bool:
        """Connect via I2C"""
        try:
            self.device = smbus2.SMBus(self.config.bus)
            logger.info(f"Connected to IT5570 via I2C (bus={self.config.bus}, address=0x{self.config.address:02X})")
            return True
        except Exception as e:
            logger.error(f"I2C connection failed: {e}")
            return False
    
    def _reset_device(self):
        """Reset the device via GPIO"""
        if self.config.interface == IT5570Interface.SPI:
            try:
                GPIO.output(self.config.reset_pin, GPIO.LOW)
                time.sleep(0.01)
                GPIO.output(self.config.reset_pin, GPIO.HIGH)
                time.sleep(0.1)
                logger.debug("Device reset completed")
            except Exception as e:
                logger.warning(f"Reset failed: {e}")
    
    def disconnect(self):
        """Disconnect from the device"""
        try:
            if self.config.interface == IT5570Interface.SPI:
                if self.device:
                    self.device.close()
                GPIO.cleanup()
            elif self.config.interface == IT5570Interface.I2C:
                if self.device:
                    self.device.close()
            logger.info("Disconnected from device")
        except Exception as e:
            logger.warning(f"Disconnect error: {e}")
    
    def detect(self) -> Optional[IT5570Info]:
        """
        Detect and identify the device
        
        Returns:
            IT5570Info if device found, None otherwise
        """
        if not self.device:
            logger.error("Not connected to device")
            return None
        
        try:
            if self.config.interface == IT5570Interface.SPI:
                return self._detect_spi()
            elif self.config.interface == IT5570Interface.I2C:
                return self._detect_i2c()
        except Exception as e:
            logger.error(f"Device detection failed: {e}")
            return None
    
    def _detect_spi(self) -> Optional[IT5570Info]:
        """Detect device via SPI"""
        try:
            # Read device ID
            response = self._spi_transfer([self.CMD_READ_ID, 0x00, 0x00, 0x00])
            
            if len(response) < 4:
                logger.error("Invalid response from device")
                return None
            
            # IT5570 returns: manufacturer ID, device ID (high byte), device ID (low byte)
            manufacturer = response[0]
            device_id_high = response[1]
            device_id_low = response[2]
            
            device_id_str = f"0x{manufacturer:02X}{device_id_high:02X}{device_id_low:02X}"
            
            logger.info(f"Device detected: IT5570 (ID: {device_id_str})")
            
            info = IT5570Info(
                device_id=device_id_str,
                firmware_version="Unknown",
                memory_size=self.FLASH_SIZE,
                page_size=self.PAGE_SIZE,
                interface=IT5570Interface.SPI,
                address=0
            )
            
            return info
        except Exception as e:
            logger.error(f"SPI detection failed: {e}")
            return None
    
    def _detect_i2c(self) -> Optional[IT5570Info]:
        """Detect device via I2C"""
        try:
            # Try to read status register
            status = self.device.read_byte_data(self.config.address, 0x00)
            
            logger.info(f"Device detected: IT5570 (I2C address: 0x{self.config.address:02X})")
            
            info = IT5570Info(
                device_id="IT5570",
                firmware_version="Unknown",
                memory_size=self.FLASH_SIZE,
                page_size=self.PAGE_SIZE,
                interface=IT5570Interface.I2C,
                address=self.config.address
            )
            
            return info
        except Exception as e:
            logger.error(f"I2C detection failed: {e}")
            return None
    
    def _spi_transfer(self, data: List[int]) -> List[int]:
        """
        Perform SPI transfer
        
        Args:
            data: Bytes to send
        
        Returns:
            Response bytes
        """
        try:
            GPIO.output(self.config.chip_select_pin, GPIO.LOW)
            response = self.device.xfer2(data)
            GPIO.output(self.config.chip_select_pin, GPIO.HIGH)
            return response
        except Exception as e:
            logger.error(f"SPI transfer failed: {e}")
            return []
    
    def _write_enable_spi(self):
        """Enable writes via SPI"""
        self._spi_transfer([self.CMD_WRITE_ENABLE])
        logger.debug("Write enable sent")
    
    def _read_status_spi(self) -> int:
        """Read status register via SPI"""
        response = self._spi_transfer([self.CMD_READ_STATUS, 0x00])
        if len(response) > 1:
            return response[1]
        return 0
    
    def _wait_ready_spi(self, timeout: float = 10):
        """Wait for device to be ready (WIP bit clear)"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            status = self._read_status_spi()
            if not (status & 0x01):  # WIP bit
                return True
            time.sleep(0.01)
        return False
    
    def dump(self, output_file: str) -> bool:
        """
        Dump firmware from device to file
        
        Args:
            output_file: Output file path
        
        Returns:
            True if successful
        """
        logger.info(f"Starting firmware dump to {output_file}")
        
        all_data = bytearray()
        
        try:
            if self.config.interface == IT5570Interface.SPI:
                # Read entire flash via SPI
                for offset in range(0, self.FLASH_SIZE, self.PAGE_SIZE):
                    progress = (offset / self.FLASH_SIZE) * 100
                    logger.info(f"Reading 0x{offset:06X} ({progress:.1f}%)...")
                    
                    # Prepare read command: READ_DATA (0x03) + 24-bit address
                    cmd = [
                        self.CMD_READ_DATA,
                        (offset >> 16) & 0xFF,
                        (offset >> 8) & 0xFF,
                        offset & 0xFF
                    ]
                    
                    # Add dummy bytes for page read
                    cmd.extend([0x00] * self.PAGE_SIZE)
                    
                    response = self._spi_transfer(cmd)
                    page_data = response[4:4+self.PAGE_SIZE]
                    all_data.extend(page_data)
            else:
                logger.error("I2C dump not implemented yet")
                return False
            
            # Write to file
            with open(output_file, 'wb') as f:
                f.write(all_data)
            
            checksum = hashlib.sha256(all_data).hexdigest()
            logger.info(f"Firmware dumped successfully ({len(all_data)} bytes)")
            logger.info(f"SHA256: {checksum}")
            return True
        
        except Exception as e:
            logger.error(f"Dump failed: {e}")
            return False
    
    def erase(self, erase_type: str = "chip", confirm: bool = False) -> bool:
        """
        Erase device memory
        
        Args:
            erase_type: "chip", "sector", or "block"
            confirm: Confirmation flag
        
        Returns:
            True if successful
        """
        if not confirm:
            logger.error("Erase operation requires confirmation")
            return False
        
        if self.config.interface != IT5570Interface.SPI:
            logger.error("Erase only supported via SPI currently")
            return False
        
        try:
            if erase_type == "chip":
                logger.warning("⚠️  Erasing entire chip memory...")
                self._write_enable_spi()
                self._spi_transfer([self.CMD_CHIP_ERASE])
                
                if not self._wait_ready_spi(self.CHIP_ERASE_TIMEOUT):
                    logger.error("Chip erase timeout")
                    return False
                
                logger.info("✓ Chip erased successfully")
                return True
            
            elif erase_type == "sector":
                logger.warning("⚠️  Erasing first sector...")
                self._write_enable_spi()
                cmd = [self.CMD_SECTOR_ERASE, 0x00, 0x00, 0x00]
                self._spi_transfer(cmd)
                
                if not self._wait_ready_spi(self.SECTOR_ERASE_TIMEOUT):
                    logger.error("Sector erase timeout")
                    return False
                
                logger.info("✓ Sector erased successfully")
                return True
            
            else:
                logger.error(f"Unknown erase type: {erase_type}")
                return False
        
        except Exception as e:
            logger.error(f"Erase failed: {e}")
            return False
    
    def flash(self, input_file: str, verify: bool = True) -> bool:
        """
        Flash firmware from file to device
        
        Args:
            input_file: Input file path
            verify: Verify after write
        
        Returns:
            True if successful
        """
        logger.info(f"Starting firmware flash from {input_file}")
        
        try:
            with open(input_file, 'rb') as f:
                file_data = f.read()
        except Exception as e:
            logger.error(f"Failed to read input file: {e}")
            return False
        
        if len(file_data) > self.FLASH_SIZE:
            logger.error(f"File size ({len(file_data)}) exceeds device memory ({self.FLASH_SIZE})")
            return False
        
        if self.config.interface != IT5570Interface.SPI:
            logger.error("Flash only supported via SPI currently")
            return False
        
        try:
            # Program data page by page
            for offset in range(0, len(file_data), self.PAGE_SIZE):
                progress = (offset / len(file_data)) * 100
                logger.info(f"Writing page at 0x{offset:06X} ({progress:.1f}%)...")
                
                page_end = min(offset + self.PAGE_SIZE, len(file_data))
                page_data = file_data[offset:page_end]
                
                # Pad to full page size
                if len(page_data) < self.PAGE_SIZE:
                    page_data = page_data + b'\xFF' * (self.PAGE_SIZE - len(page_data))
                
                # Enable write
                self._write_enable_spi()
                
                # Prepare write command
                cmd = [
                    self.CMD_PAGE_PROGRAM,
                    (offset >> 16) & 0xFF,
                    (offset >> 8) & 0xFF,
                    offset & 0xFF
                ]
                cmd.extend(list(page_data))
                
                self._spi_transfer(cmd)
                
                # Wait for write to complete
                if not self._wait_ready_spi(self.PAGE_WRITE_TIMEOUT):
                    logger.error(f"Write timeout at 0x{offset:06X}")
                    return False
            
            logger.info("Firmware flash completed")
            
            if verify:
                logger.info("Starting verification...")
                if not self._verify_flash(file_data):
                    logger.error("Verification failed")
                    return False
            
            return True
        
        except Exception as e:
            logger.error(f"Flash failed: {e}")
            return False
    
    def _verify_flash(self, expected_data: bytes) -> bool:
        """
        Verify flashed data
        
        Args:
            expected_data: Expected data
        
        Returns:
            True if verification successful
        """
        try:
            read_data = bytearray()
            
            for offset in range(0, len(expected_data), self.PAGE_SIZE):
                page_size = min(self.PAGE_SIZE, len(expected_data) - offset)
                
                cmd = [
                    self.CMD_FAST_READ,
                    (offset >> 16) & 0xFF,
                    (offset >> 8) & 0xFF,
                    offset & 0xFF,
                    0x00  # Dummy byte for fast read
                ]
                cmd.extend([0x00] * page_size)
                
                response = self._spi_transfer(cmd)
                page_data = response[5:5+page_size]
                read_data.extend(page_data)
            
            if bytes(read_data) == expected_data:
                logger.info("✓ Verification successful")
                return True
            else:
                logger.error("Verification failed: data mismatch")
                return False
        
        except Exception as e:
            logger.error(f"Verification error: {e}")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='IT5570 Raspberry Pi Programmer - Dump, Erase, and Flash'
    )
    
    # Global options
    parser.add_argument('--interface', choices=['spi', 'i2c'], default='spi',
                       help='Communication interface (default: spi)')
    parser.add_argument('--bus', type=int, default=1,
                       help='I2C bus number (default: 1) or SPI bus (default: 0)')
    parser.add_argument('--address', type=str, default='0x60',
                       help='I2C address (default: 0x60)')
    parser.add_argument('--spi-speed', type=int, default=1000000,
                       help='SPI speed in Hz (default: 1000000)')
    parser.add_argument('--cs-pin', type=int, default=8,
                       help='Chip select GPIO pin (default: 8)')
    parser.add_argument('--reset-pin', type=int, default=7,
                       help='Reset GPIO pin (default: 7)')
    parser.add_argument('-v', '--verbose', action='store_true',
                       help='Verbose output')
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Detect command
    subparsers.add_parser('detect', help='Detect device')
    
    # Dump command
    dump_parser = subparsers.add_parser('dump', help='Dump firmware from device')
    dump_parser.add_argument('--output', '-o', required=True, help='Output file path')
    
    # Erase command
    erase_parser = subparsers.add_parser('erase', help='Erase device memory')
    erase_parser.add_argument('--type', choices=['chip', 'sector', 'block'],
                             default='chip', help='Erase type (default: chip)')
    erase_parser.add_argument('--confirm', action='store_true', help='Confirm erase')
    
    # Flash command
    flash_parser = subparsers.add_parser('flash', help='Flash firmware to device')
    flash_parser.add_argument('--input', '-i', required=True, help='Input file path')
    flash_parser.add_argument('--verify', action='store_true', help='Verify after flash')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 1
    
    # Parse address
    try:
        address = int(args.address, 0)
    except ValueError:
        print(f"Invalid address: {args.address}")
        return 1
    
    # Create config
    interface = IT5570Interface.SPI if args.interface == 'spi' else IT5570Interface.I2C
    config = IT5570Config(
        interface=interface,
        bus=args.bus,
        address=address,
        spi_speed=args.spi_speed,
        chip_select_pin=args.cs_pin,
        reset_pin=args.reset_pin
    )
    
    # Create programmer
    programmer = IT5570Programmer(config, verbose=args.verbose)
    
    try:
        # Connect to device
        if not programmer.connect():
            return 1
        
        # Detect device
        device_info = programmer.detect()
        if not device_info:
            return 1
        
        print(f"\nDevice: {device_info.device_id}")
        print(f"Memory: {device_info.memory_size} bytes")
        print(f"Page size: {device_info.page_size} bytes")
        print(f"Interface: {device_info.interface.value.upper()}")
        
        # Execute command
        if args.command == 'detect':
            return 0
        
        elif args.command == 'dump':
            if programmer.dump(args.output):
                return 0
            return 1
        
        elif args.command == 'erase':
            if programmer.erase(erase_type=args.type, confirm=args.confirm):
                return 0
            return 1
        
        elif args.command == 'flash':
            if programmer.flash(args.input, verify=args.verify):
                return 0
            return 1
        
        return 1
    
    finally:
        programmer.disconnect()


if __name__ == '__main__':
    sys.exit(main())
