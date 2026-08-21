"""File format handlers for TPS6599x programmer"""

import struct
from typing import Optional, Tuple
from pathlib import Path


class HexFile:
    """Intel HEX file handler"""
    
    def __init__(self):
        self.data = bytearray(0x10000)  # 64KB
    
    def read(self, filename: str) -> bool:
        """
        Read Intel HEX file
        
        Returns:
            True if successful
        """
        try:
            with open(filename, 'r') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith(':'):
                        if not self._parse_hex_line(line):
                            return False
            return True
        except Exception as e:
            print(f"Error reading HEX file: {e}")
            return False
    
    def write(self, filename: str, data: bytes) -> bool:
        """Write data to Intel HEX file"""
        try:
            with open(filename, 'w') as f:
                offset = 0
                while offset < len(data):
                    chunk = data[offset:offset+16]
                    checksum = (len(chunk) + (offset >> 8) + (offset & 0xFF)) & 0xFF
                    for byte in chunk:
                        checksum = (checksum + byte) & 0xFF
                    checksum = (0x100 - checksum) & 0xFF
                    
                    hex_line = f":{len(chunk):02X}{offset:04X}00"
                    for byte in chunk:
                        hex_line += f"{byte:02X}"
                    hex_line += f"{checksum:02X}\n"
                    
                    f.write(hex_line)
                    offset += len(chunk)
                
                f.write(":00000001FF\n")
            return True
        except Exception as e:
            print(f"Error writing HEX file: {e}")
            return False
    
    def _parse_hex_line(self, line: str) -> bool:
        """Parse a single HEX line"""
        if not line.startswith(':'):
            return True
        
        try:
            line = line[1:]
            byte_count = int(line[0:2], 16)
            address = int(line[2:6], 16)
            record_type = int(line[6:8], 16)
            
            if record_type == 0x00:  # Data record
                data_start = 8
                data_end = 8 + byte_count * 2
                for i in range(byte_count):
                    byte_val = int(line[data_start + i*2:data_start + i*2 + 2], 16)
                    self.data[address + i] = byte_val
            
            elif record_type == 0x01:  # End of file
                return True
            
            return True
        except Exception:
            return False
    
    def get_bytes(self) -> bytes:
        """Get binary data"""
        return bytes(self.data)


def detect_file_format(filename: str) -> Optional[str]:
    """
    Detect file format
    
    Returns:
        'binary', 'hex', or None
    """
    ext = Path(filename).suffix.lower()
    
    if ext in ['.bin', '.image']:
        return 'binary'
    elif ext in ['.hex', '.ihex']:
        return 'hex'
    
    # Try to detect by content
    try:
        with open(filename, 'rb') as f:
            header = f.read(2)
            if header.startswith(b':'):
                return 'hex'
            return 'binary'
    except Exception:
        return None


def read_firmware_file(filename: str) -> Optional[bytes]:
    """
    Read firmware file in any supported format
    
    Returns:
        Firmware bytes or None
    """
    fmt = detect_file_format(filename)
    
    if fmt == 'hex':
        hex_file = HexFile()
        if hex_file.read(filename):
            return hex_file.get_bytes()
    elif fmt == 'binary':
        try:
            with open(filename, 'rb') as f:
                return f.read()
        except Exception as e:
            print(f"Error reading binary file: {e}")
    
    return None
