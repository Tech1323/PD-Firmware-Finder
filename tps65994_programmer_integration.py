#!/usr/bin/env python3
"""
TPS65994 Programmer Integration Tool
Combines firmware extraction from BIOS files with direct chip programming via I2C
"""

import sys
import subprocess
import argparse
from pathlib import Path
from typing import Optional, Tuple


def hex_int(value):
    """Convert hex string (0x21) or decimal (33) to integer"""
    try:
        if isinstance(value, int):
            return value
        # Try hex first (with or without 0x prefix)
        if value.startswith(('0x', '0X')):
            return int(value, 16)
        # Try decimal
        return int(value, 10)
    except ValueError:
        raise argparse.ArgumentTypeError(f"Invalid address format: {value}. Use 0x21 or 33")


class TPS65994Integration:
    """Integration layer between firmware finder and chip programmer"""
    
    def __init__(self, finder_script: str = "pd_firmware_finder.py", 
                 programmer_script: str = "tps6599x_programmer.py", 
                 verbose: bool = False):
        self.finder_script = Path(finder_script)
        self.programmer_script = Path(programmer_script)
        self.verbose = verbose
        
    def log(self, message: str, level: str = "INFO"):
        """Print log message"""
        if self.verbose or level != "DEBUG":
            print(f"[{level}] {message}")
    
    def extract_cst1_from_bios(self, bios_file: str, output_config: str) -> bool:
        """Extract CST1 configuration from BIOS file"""
        if not self.finder_script.exists():
            self.log(f"Firmware finder script not found: {self.finder_script}", "ERROR")
            return False
        
        self.log(f"Extracting CST1 from BIOS file: {bios_file}")
        
        cmd = [
            "python3", str(self.finder_script),
            bios_file,
            "--extract-cst1", output_config
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
            
            if result.returncode != 0:
                self.log(f"Extraction failed: {result.stderr}", "ERROR")
                return False
            
            if self.verbose:
                print(result.stdout)
            
            output_path = Path(output_config)
            if output_path.exists():
                self.log(f"✓ CST1 extracted successfully: {output_config} ({output_path.stat().st_size} bytes)")
                return True
            else:
                self.log(f"Output file not created: {output_config}", "ERROR")
                return False
                
        except subprocess.TimeoutExpired:
            self.log("Extraction timed out", "ERROR")
            return False
        except Exception as e:
            self.log(f"Extraction error: {e}", "ERROR")
            return False
    
    def detect_device(self, bus: int, address: Optional[int] = None) -> Tuple[bool, str]:
        """Detect connected TPS65994 device"""
        if not self.programmer_script.exists():
            self.log(f"Programmer script not found: {self.programmer_script}", "ERROR")
            return False, ""
        
        self.log(f"Detecting device on bus {bus}...")
        
        cmd = [
            "python3", str(self.programmer_script),
            "--bus", str(bus),
            "detect"
        ]
        
        if address is not None:
            cmd.insert(3, "--address")
            cmd.insert(4, f"0x{address:02x}")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            
            if result.returncode != 0:
                self.log(f"Detection failed: {result.stderr}", "ERROR")
                return False, ""
            
            if self.verbose:
                print(result.stdout)
            
            self.log("✓ Device detected successfully")
            return True, result.stdout
                
        except subprocess.TimeoutExpired:
            self.log("Detection timed out", "ERROR")
            return False, ""
        except Exception as e:
            self.log(f"Detection error: {e}", "ERROR")
            return False, ""
    
    def dump_device_firmware(self, bus: int, address: int, output_file: str) -> bool:
        """Dump current firmware from device"""
        if not self.programmer_script.exists():
            self.log(f"Programmer script not found: {self.programmer_script}", "ERROR")
            return False
        
        self.log(f"Dumping firmware from device (0x{address:02x}) on bus {bus}...")
        
        cmd = [
            "python3", str(self.programmer_script),
            "--bus", str(bus),
            "--address", f"0x{address:02x}",
            "dump",
            "--output", output_file
        ]
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
            
            if result.returncode != 0:
                self.log(f"Dump failed: {result.stderr}", "ERROR")
                return False
            
            if self.verbose:
                print(result.stdout)
            
            output_path = Path(output_file)
            if output_path.exists():
                self.log(f"✓ Firmware dumped successfully: {output_file} ({output_path.stat().st_size} bytes)")
                return True
            else:
                self.log(f"Output file not created: {output_file}", "ERROR")
                return False
                
        except subprocess.TimeoutExpired:
            self.log("Dump operation timed out", "ERROR")
            return False
        except Exception as e:
            self.log(f"Dump error: {e}", "ERROR")
            return False
    
    def program_device(self, bus: int, address: int, config_file: str, verify: bool = True) -> bool:
        """Program configuration to device"""
        if not self.programmer_script.exists():
            self.log(f"Programmer script not found: {self.programmer_script}", "ERROR")
            return False
        
        config_path = Path(config_file)
        if not config_path.exists():
            self.log(f"Configuration file not found: {config_file}", "ERROR")
            return False
        
        self.log(f"Programming configuration to device (0x{address:02x}) on bus {bus}...")
        self.log(f"Config file: {config_file} ({config_path.stat().st_size} bytes)")
        
        cmd = [
            "python3", str(self.programmer_script),
            "--bus", str(bus),
            "--address", f"0x{address:02x}",
            "write",
            "--input", config_file
        ]
        
        if verify:
            cmd.append("--verify")
        
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
            
            if result.returncode != 0:
                self.log(f"Programming failed: {result.stderr}", "ERROR")
                return False
            
            if self.verbose:
                print(result.stdout)
            
            self.log("✓ Device programmed successfully")
            return True
                
        except subprocess.TimeoutExpired:
            self.log("Programming operation timed out", "ERROR")
            return False
        except Exception as e:
            self.log(f"Programming error: {e}", "ERROR")
            return False
    
    def extract_and_program_workflow(self, bios_file: str, bus: int, address: int, 
                                     dump_before: bool = True) -> bool:
        """
        Full workflow: Extract config from BIOS and program to device
        
        1. (Optional) Dump current firmware from device for backup
        2. Extract CST1 config from BIOS file
        3. Program device with new config
        4. Verify programming
        """
        
        self.log("="*80)
        self.log("TPS65994 EXTRACT AND PROGRAM WORKFLOW")
        self.log("="*80)
        
        # Step 0: Detect device
        detected, detect_output = self.detect_device(bus, address)
        if not detected:
            self.log("Cannot proceed without device detection", "ERROR")
            return False
        print(detect_output)
        
        # Step 1: Backup current firmware
        if dump_before:
            self.log("\nSTEP 1: Backing up current device firmware...")
            backup_file = f"device_backup_0x{address:02x}.bin"
            if not self.dump_device_firmware(bus, address, backup_file):
                self.log("Warning: Could not backup firmware, continuing anyway...", "WARN")
            else:
                self.log(f"Backup saved to: {backup_file}")
        
        # Step 2: Extract CST1 from BIOS
        self.log("\nSTEP 2: Extracting CST1 configuration from BIOS file...")
        config_file = "extracted_cst1.bin"
        if not self.extract_cst1_from_bios(bios_file, config_file):
            self.log("CST1 extraction failed", "ERROR")
            return False
        
        # Step 3: Program device
        self.log("\nSTEP 3: Programming device with extracted configuration...")
        if not self.program_device(bus, address, config_file, verify=True):
            self.log("Device programming failed", "ERROR")
            return False
        
        self.log("\n" + "="*80)
        self.log("✓ WORKFLOW COMPLETE - Device successfully programmed!")
        self.log("="*80)
        return True


def main():
    # Create main parser with global options
    parser = argparse.ArgumentParser(
        description='TPS65994 Programmer - Firmware Extraction and Device Programming'
    )
    
    # Global options BEFORE subcommands
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('--finder-script', default='pd_firmware_finder.py',
                        help='Path to firmware finder script (default: pd_firmware_finder.py)')
    parser.add_argument('--programmer-script', default='tps6599x_programmer.py',
                        help='Path to programmer script (default: tps6599x_programmer.py)')
    
    # Create subcommands
    subparsers = parser.add_subparsers(dest='command', help='Command to execute')
    
    # detect command
    detect_parser = subparsers.add_parser('detect', help='Detect connected device')
    detect_parser.add_argument('--bus', type=int, required=True, help='I2C bus number')
    detect_parser.add_argument('--address', type=hex_int, help='Device I2C address (0x20-0x23 or 32-35)')
    
    # dump command
    dump_parser = subparsers.add_parser('dump', help='Dump firmware from device')
    dump_parser.add_argument('--bus', type=int, required=True, help='I2C bus number')
    dump_parser.add_argument('--address', type=hex_int, required=True, help='Device I2C address (0x20-0x23 or 32-35)')
    dump_parser.add_argument('--output', required=True, help='Output file path')
    
    # extract command
    extract_parser = subparsers.add_parser('extract', help='Extract CST1 from BIOS file')
    extract_parser.add_argument('bios_file', help='Lenovo BIOS .CAP file')
    extract_parser.add_argument('--output', required=True, help='Output config file')
    
    # program command
    program_parser = subparsers.add_parser('program', help='Program device with configuration')
    program_parser.add_argument('--bus', type=int, required=True, help='I2C bus number')
    program_parser.add_argument('--address', type=hex_int, required=True, help='Device I2C address (0x20-0x23 or 32-35)')
    program_parser.add_argument('--config', required=True, help='Configuration file to program')
    program_parser.add_argument('--no-verify', action='store_true', help='Skip verification')
    
    # workflow command (full integration)
    workflow_parser = subparsers.add_parser('workflow', help='Full extract and program workflow')
    workflow_parser.add_argument('bios_file', help='Lenovo BIOS .CAP file')
    workflow_parser.add_argument('--bus', type=int, required=True, help='I2C bus number')
    workflow_parser.add_argument('--address', type=hex_int, required=True, help='Device I2C address (0x20-0x23 or 32-35)')
    workflow_parser.add_argument('--no-backup', action='store_true', help='Skip firmware backup')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Create integration tool
    tool = TPS65994Integration(
        finder_script=args.finder_script,
        programmer_script=args.programmer_script,
        verbose=args.verbose
    )
    
    # Execute command
    success = False
    
    if args.command == 'detect':
        detected, output = tool.detect_device(args.bus, args.address)
        success = detected
        if output:
            print(output)
    
    elif args.command == 'dump':
        success = tool.dump_device_firmware(args.bus, args.address, args.output)
    
    elif args.command == 'extract':
        success = tool.extract_cst1_from_bios(args.bios_file, args.output)
    
    elif args.command == 'program':
        success = tool.program_device(args.bus, args.address, args.config, 
                                     verify=not args.no_verify)
    
    elif args.command == 'workflow':
        success = tool.extract_and_program_workflow(
            args.bios_file, 
            args.bus, 
            args.address,
            dump_before=not args.no_backup
        )
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
