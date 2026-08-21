#!/usr/bin/env python3
"""
TPS6599x Series USB Power Delivery Controller Programmer
Supports: TPS65993, TPS65994, and variants
Operations: Dump, Write, Erase
"""

import sys
import argparse
import logging
import time
import hashlib
import struct
from pathlib import Path
from enum import Enum
from typing import Optional, Tuple, List
from dataclasses import dataclass

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


class TPS6599xVariant(Enum):
    """Supported TPS6599x device variants"""
    TPS65993 = 0x20
    TPS65994 = 0x21
    TPS65991 = 0x22
    TPS65992 = 0x23


@dataclass
class DeviceInfo:
    """Device information structure"""
    variant: TPS6599xVariant
    firmware_version: str
    device_id: int
    address: int
    bus: int


class TPS6599xProgrammer:
    """Main programmer class for TPS6599x devices"""
    
    # Register addresses
    REG_DEVICE_ID = 0x00
    REG_FIRMWARE_VERSION = 0x01
    REG_STATUS = 0x02
    REG_CONTROL = 0x03
    REG_DATA_START = 0x10
    REG_ERASE_CMD = 0x04
    REG_WRITE_CMD = 0x05
    
    # Memory configuration
    MEMORY_SIZE = 0x10000  # 64KB
    PAGE_SIZE = 256
    MAX_PAGES = MEMORY_SIZE // PAGE_SIZE
    
    # Command constants
    CMD_ERASE_ALL = 0xAA
    CMD_ERASE_PAGE = 0x55
    CMD_WRITE_PAGE = 0x33
    CMD_READ_PAGE = 0x11
    
    # Timeouts
    ERASE_TIMEOUT = 10  # seconds
    WRITE_TIMEOUT = 5   # seconds
    READ_TIMEOUT = 2    # seconds
    
    def __init__(self, bus: int = 1, address: int = 0x20, verbose: bool = False):
        """
        Initialize the programmer
        
        Args:
            bus: I2C bus number
            address: I2C slave address (default 0x20 for TPS65993)
            verbose: Enable verbose logging
        """
        self.bus = bus
        self.address = address
        self.verbose = verbose
        self.device = None
        
        if verbose:
            logger.setLevel(logging.DEBUG)
        
        if not HAS_SMBUS:
            raise RuntimeError("smbus2 module required. Install with: pip install smbus2")
    
    def connect(self) -> bool:
        """
        Connect to the I2C device
        
        Returns:
            True if connection successful
        """
        try:
            self.device = smbus2.SMBus(self.bus)
            logger.info(f"Connected to I2C bus {self.bus}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to I2C bus {self.bus}: {e}")
            return False
    
    def disconnect(self):
        """Disconnect from the I2C device"""
        if self.device:
            self.device.close()
            logger.info("Disconnected from device")
    
    def detect(self) -> Optional[DeviceInfo]:
        """
        Detect and identify the device
        
        Returns:
            DeviceInfo if device found, None otherwise
        """
        if not self.device:
            logger.error("Not connected to device")
            return None
        
        try:
            # Read device ID
            device_id = self.device.read_byte_data(self.address, self.REG_DEVICE_ID)
            
            # Identify variant
            variant = None
            for v in TPS6599xVariant:
                if v.value == device_id:
                    variant = v
                    break
            
            if not variant:
                logger.error(f"Unknown device ID: 0x{device_id:02X}")
                return None
            
            # Read firmware version
            fw_version = self.device.read_byte_data(self.address, self.REG_FIRMWARE_VERSION)
            fw_str = f"{(fw_version >> 4) & 0xF}.{fw_version & 0xF}"
            
            info = DeviceInfo(
                variant=variant,
                firmware_version=fw_str,
                device_id=device_id,
                address=self.address,
                bus=self.bus
            )
            
            logger.info(f"Device detected: {variant.name}")
            logger.info(f"Firmware version: {fw_str}")
            logger.info(f"Device ID: 0x{device_id:02X}")
            
            return info
        except Exception as e:
            logger.error(f"Device detection failed: {e}")
            return None
    
    def read_page(self, page_num: int) -> Optional[bytes]:
        """
        Read a single page from device memory
        
        Args:
            page_num: Page number (0-255)
        
        Returns:
            Page data (256 bytes) or None on error
        """
        if not self.device:
            logger.error("Not connected to device")
            return None
        
        if page_num >= self.MAX_PAGES:
            logger.error(f"Page number {page_num} exceeds maximum {self.MAX_PAGES-1}")
            return None
        
        try:
            # Send read command
            self.device.write_byte_data(self.address, self.REG_CONTROL, page_num)
            self.device.write_byte_data(self.address, self.REG_WRITE_CMD, self.CMD_READ_PAGE)
            
            # Wait for completion
            start_time = time.time()
            while time.time() - start_time < self.READ_TIMEOUT:
                status = self.device.read_byte_data(self.address, self.REG_STATUS)
                if status & 0x01:  # Ready bit
                    break
                time.sleep(0.01)
            else:
                logger.warning(f"Read timeout for page {page_num}")
                return None
            
            # Read data
            data = self.device.read_i2c_block_data(self.address, self.REG_DATA_START, self.PAGE_SIZE)
            return bytes(data)
        
        except Exception as e:
            logger.error(f"Failed to read page {page_num}: {e}")
            return None
    
    def write_page(self, page_num: int, data: bytes) -> bool:
        """
        Write a single page to device memory
        
        Args:
            page_num: Page number (0-255)
            data: Page data (must be 256 bytes)
        
        Returns:
            True if successful
        """
        if not self.device:
            logger.error("Not connected to device")
            return False
        
        if len(data) != self.PAGE_SIZE:
            logger.error(f"Invalid data length: {len(data)}, expected {self.PAGE_SIZE}")
            return False
        
        if page_num >= self.MAX_PAGES:
            logger.error(f"Page number {page_num} exceeds maximum {self.MAX_PAGES-1}")
            return False
        
        try:
            # Write data to buffer
            self.device.write_i2c_block_data(self.address, self.REG_DATA_START, list(data))
            
            # Send write command
            self.device.write_byte_data(self.address, self.REG_CONTROL, page_num)
            self.device.write_byte_data(self.address, self.REG_WRITE_CMD, self.CMD_WRITE_PAGE)
            
            # Wait for completion
            start_time = time.time()
            while time.time() - start_time < self.WRITE_TIMEOUT:
                status = self.device.read_byte_data(self.address, self.REG_STATUS)
                if status & 0x01:  # Ready bit
                    break
                time.sleep(0.01)
            else:
                logger.warning(f"Write timeout for page {page_num}")
                return False
            
            return True
        
        except Exception as e:
            logger.error(f"Failed to write page {page_num}: {e}")
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
        
        for page_num in range(self.MAX_PAGES):
            logger.info(f"Reading page {page_num}/{self.MAX_PAGES-1}...")
            
            page_data = self.read_page(page_num)
            if page_data is None:
                logger.error(f"Failed to read page {page_num}")
                return False
            
            all_data.extend(page_data)
        
        try:
            with open(output_file, 'wb') as f:
                f.write(all_data)
            
            checksum = hashlib.sha256(all_data).hexdigest()
            logger.info(f"Firmware dumped successfully ({len(all_data)} bytes)")
            logger.info(f"SHA256: {checksum}")
            return True
        
        except Exception as e:
            logger.error(f"Failed to write output file: {e}")
            return False
    
    def write(self, input_file: str, verify: bool = True) -> bool:
        """
        Write firmware from file to device
        
        Args:
            input_file: Input file path
            verify: Verify after write
        
        Returns:
            True if successful
        """
        logger.info(f"Starting firmware write from {input_file}")
        
        try:
            with open(input_file, 'rb') as f:
                file_data = f.read()
        except Exception as e:
            logger.error(f"Failed to read input file: {e}")
            return False
        
        if len(file_data) > self.MEMORY_SIZE:
            logger.error(f"File size ({len(file_data)}) exceeds device memory ({self.MEMORY_SIZE})")
            return False
        
        # Pad to full memory size
        if len(file_data) < self.MEMORY_SIZE:
            file_data += b'\xFF' * (self.MEMORY_SIZE - len(file_data))
        
        logger.info(f"Writing {len(file_data)} bytes to device")
        
        for page_num in range(self.MAX_PAGES):
            page_start = page_num * self.PAGE_SIZE
            page_end = page_start + self.PAGE_SIZE
            page_data = file_data[page_start:page_end]
            
            logger.info(f"Writing page {page_num}/{self.MAX_PAGES-1}...")
            
            if not self.write_page(page_num, page_data):
                logger.error(f"Failed to write page {page_num}")
                return False
        
        logger.info("Firmware write completed")
        
        if verify:
            logger.info("Starting verification...")
            if not self._verify_write(file_data):
                logger.error("Verification failed")
                return False
        
        return True
    
    def _verify_write(self, expected_data: bytes) -> bool:
        """
        Verify written data
        
        Args:
            expected_data: Expected data to verify against
        
        Returns:
            True if verification successful
        """
        read_data = bytearray()
        
        for page_num in range(self.MAX_PAGES):
            page_data = self.read_page(page_num)
            if page_data is None:
                return False
            read_data.extend(page_data)
        
        if read_data == expected_data:
            logger.info("Verification successful")
            return True
        else:
            logger.error("Verification failed: data mismatch")
            return False
    
    def erase(self, confirm: bool = False) -> bool:
        """
        Erase device memory
        
        Args:
            confirm: Confirmation flag
        
        Returns:
            True if successful
        """
        if not confirm:
            logger.error("Erase operation requires confirmation")
            return False
        
        logger.warning("Erasing device memory...")
        
        if not self.device:
            logger.error("Not connected to device")
            return False
        
        try:
            # Send erase command
            self.device.write_byte_data(self.address, self.REG_ERASE_CMD, self.CMD_ERASE_ALL)
            
            # Wait for completion
            start_time = time.time()
            while time.time() - start_time < self.ERASE_TIMEOUT:
                status = self.device.read_byte_data(self.address, self.REG_STATUS)
                if status & 0x01:  # Ready bit
                    break
                time.sleep(0.1)
            else:
                logger.warning("Erase timeout")
                return False
            
            logger.info("Device memory erased successfully")
            return True
        
        except Exception as e:
            logger.error(f"Erase operation failed: {e}")
            return False


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description='TPS6599x I2C Programmer - Dump, Write, and Erase firmware'
    )
    
    # Global options
    parser.add_argument('--bus', type=int, default=1, help='I2C bus number (default: 1)')
    parser.add_argument('--address', type=str, default='0x20', help='I2C address (default: 0x20)')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    
    # Subcommands
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # Detect command
    detect_parser = subparsers.add_parser('detect', help='Detect device')
    
    # Dump command
    dump_parser = subparsers.add_parser('dump', help='Dump firmware from device')
    dump_parser.add_argument('--output', '-o', required=True, help='Output file path')
    
    # Write command
    write_parser = subparsers.add_parser('write', help='Write firmware to device')
    write_parser.add_argument('--input', '-i', required=True, help='Input file path')
    write_parser.add_argument('--verify', action='store_true', help='Verify after write')
    
    # Erase command
    erase_parser = subparsers.add_parser('erase', help='Erase device memory')
    erase_parser.add_argument('--confirm', action='store_true', help='Confirm erase operation')
    
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
    
    # Create programmer instance
    programmer = TPS6599xProgrammer(bus=args.bus, address=address, verbose=args.verbose)
    
    try:
        # Connect to device
        if not programmer.connect():
            return 1
        
        # Detect device
        device_info = programmer.detect()
        if not device_info:
            return 1
        
        # Execute command
        if args.command == 'detect':
            print(f"\nDevice: {device_info.variant.name}")
            print(f"Firmware: {device_info.firmware_version}")
            print(f"Address: 0x{device_info.address:02X}")
            print(f"Bus: {device_info.bus}")
            return 0
        
        elif args.command == 'dump':
            if programmer.dump(args.output):
                return 0
            return 1
        
        elif args.command == 'write':
            if programmer.write(args.input, verify=args.verify):
                return 0
            return 1
        
        elif args.command == 'erase':
            if programmer.erase(confirm=args.confirm):
                return 0
            return 1
        
        return 1
    
    finally:
        programmer.disconnect()


if __name__ == '__main__':
    sys.exit(main())
