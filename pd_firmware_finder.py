#!/usr/bin/env python3
"""
TPS65994 USB Power Delivery Firmware Finder for Lenovo BIOS Files
Searches for TPS65994 firmware sections in Lenovo .CAP BIOS files
"""

import sys
import struct
from pathlib import Path
from typing import List, Tuple, Optional
import re


# ---------------------------------------------------------------------------
# CST1 register name map (TPS65994 configuration bundle registers)
# ---------------------------------------------------------------------------
CST1_REGISTER_NAMES = {
    0x06: "FW_VERSION",
    0x16: "POWER_PATH_CFG1",
    0x17: "POWER_PATH_CFG2",
    0x23: "PORT_CONFIG",
    0x27: "TYPEC_CONFIG",
    0x28: "RX_SRC_CAPS1",
    0x29: "RX_SRC_CAPS2",
    0x2B: "POWER_BUDGET",
    0x32: "TX_SINK_CAPS1",
    0x33: "TX_SINK_CAPS2",
    0x37: "PD_CONFIG",
    0x42: "CHARGER_DETECT",
    0x43: "LED_CONFIG",
    0x47: "TIMER_CONFIG",
    0x4A: "POWER_RULES",
    0x51: "BOOT_STATUS",
    0x52: "I2C_CONFIG",
    0x56: "SYS_CONFIG",
    0x5C: "DEADBATTERY",
    0x64: "CURRENT_SETTING",
    0x70: "SLEEP_CFG",
    0x77: "THERMAL_CFG",
}


def _parse_cst1_records(data: bytes, records_start: int):
    """
    Parse TPS65994 CST1 register records starting at *records_start*.

    Record format:  0xFF  [reg 1B]  [data_len-1 2B big-endian]  [data_len bytes]

    Returns a list of (reg, payload_bytes) tuples, or an empty list on failure.
    """
    records = []
    pos = records_start
    while pos + 4 <= len(data):
        if data[pos] != 0xFF:
            break
        reg = data[pos + 1]
        stored_len = struct.unpack_from(">H", data, pos + 2)[0]
        actual_len = stored_len + 1
        if actual_len > 300 or pos + 4 + actual_len > len(data):
            break
        payload = data[pos + 4: pos + 4 + actual_len]
        records.append((reg, payload))
        pos += 4 + actual_len
    return records


class TPS65994Scanner:
    """Scanner for TPS65994 firmware in Lenovo BIOS files"""
    
    # TPS65994 specific signatures
    TPS65994_SIGNATURES = {
        'TPS65994_MAGIC': b'TPS6',  # TPS65994 magic bytes
        'TI_HEADER': b'\x54\x49',  # 'TI' header
        'FIRMWARE_BLOCK': b'\xFF\xFF\xFF\xFF',  # Common firmware block marker
    }
    
    # Lenovo BIOS specific markers
    LENOVO_MARKERS = {
        'LENOVO_HEADER': b'Lenovo',
        'BIOS_REGION': b'$BIOS',
        'PD_SECTION': b'PD\x00\x00',  # Power Delivery section marker
    }
    
    # Common firmware section headers
    FIRMWARE_HEADERS = {
        'ELF': b'\x7fELF',
        'PE': b'MZ',
        'INTEL_HEX': b':',
    }
    
    # TPS65994 firmware size range (typically 16KB - 256KB)
    MIN_FW_SIZE = 16 * 1024  # 16 KB
    MAX_FW_SIZE = 256 * 1024  # 256 KB

    # Magic that marks the start of a TPS65994 CST1 configuration bundle
    CST1_MAGIC = b'CST1'
    # Size of the CST1 header that precedes the first FF record (magic + 6 bytes)
    CST1_HEADER_SIZE = 10
    
    def __init__(self, filepath: str, verbose: bool = False, fast_mode: bool = False):
        self.filepath = Path(filepath)
        self.data = None
        self.results = []
        self.verbose = verbose
        self.fast_mode = fast_mode  # Skip lengthy scans if true
        
    def log(self, message: str, level: str = "INFO"):
        """Print log message"""
        if self.verbose or level != "DEBUG":
            print(f"[{level}] {message}")
    
    def load_file(self) -> bool:
        """Load BIOS file"""
        try:
            with open(self.filepath, 'rb') as f:
                self.data = f.read()
            self.log(f"Loaded BIOS file: {self.filepath} ({len(self.data):,} bytes)")
            return True
        except FileNotFoundError:
            self.log(f"File not found: {self.filepath}", "ERROR")
            return False
        except Exception as e:
            self.log(f"Error loading file: {e}", "ERROR")
            return False
    
    def find_all_occurrences(self, pattern: bytes, start: int = 0, limit: int = None) -> List[int]:
        """Find all occurrences of a pattern, optionally limiting results"""
        positions = []
        offset = start
        while True:
            offset = self.data.find(pattern, offset)
            if offset == -1:
                break
            positions.append(offset)
            if limit and len(positions) >= limit:
                break
            offset += 1
        return positions
    
    def scan_tps65994_signatures(self):
        """Scan for TPS65994 specific signatures"""
        self.log("\n[*] Scanning for TPS65994 signatures...")
        
        for sig_name, sig_bytes in self.TPS65994_SIGNATURES.items():
            # In fast mode, limit to first few occurrences
            limit = 5 if self.fast_mode else None
            positions = self.find_all_occurrences(sig_bytes, limit=limit)
            
            if positions:
                self.log(f"    Found {sig_name}: {len(positions)} occurrence(s)")
                for offset in positions:
                    context = self.data[max(0, offset-16):min(len(self.data), offset+48)]
                    self.results.append({
                        'type': 'TPS65994_SIGNATURE',
                        'subtype': sig_name,
                        'offset': offset,
                        'offset_hex': hex(offset),
                        'context': context,
                    })
                    self.log(f"        @ 0x{offset:08x}", "DEBUG")
            else:
                self.log(f"    {sig_name}: Not found")
    
    def scan_lenovo_markers(self):
        """Scan for Lenovo BIOS structure markers"""
        if self.fast_mode:
            return  # Skip in fast mode
            
        self.log("\n[*] Scanning for Lenovo BIOS markers...")
        
        for marker_name, marker_bytes in self.LENOVO_MARKERS.items():
            positions = self.find_all_occurrences(marker_bytes, limit=5)
            
            if positions:
                self.log(f"    Found {marker_name}: {len(positions)} occurrence(s)")
                for offset in positions:
                    context = self.data[max(0, offset-8):min(len(self.data), offset+32)]
                    self.results.append({
                        'type': 'LENOVO_MARKER',
                        'subtype': marker_name,
                        'offset': offset,
                        'offset_hex': hex(offset),
                        'context': context,
                    })
                    self.log(f"        @ 0x{offset:08x}", "DEBUG")
    
    def scan_firmware_headers(self):
        """Scan for common firmware headers near PD sections"""
        if self.fast_mode:
            return  # Skip in fast mode
            
        self.log("\n[*] Scanning for firmware headers...")
        
        for header_name, header_bytes in self.FIRMWARE_HEADERS.items():
            positions = self.find_all_occurrences(header_bytes, limit=10)
            
            if positions:
                self.log(f"    Found {header_name}: {len(positions)} occurrence(s)")
                for offset in positions:
                    # Check if this looks like a real firmware section
                    if self._validate_firmware_section(offset):
                        context = self.data[max(0, offset-8):min(len(self.data), offset+32)]
                        self.results.append({
                            'type': 'FIRMWARE_HEADER',
                            'subtype': header_name,
                            'offset': offset,
                            'offset_hex': hex(offset),
                            'context': context,
                        })
                        self.log(f"        @ 0x{offset:08x} (valid)", "DEBUG")
    
    def _validate_firmware_section(self, offset: int) -> bool:
        """Validate if offset looks like a real firmware section"""
        if offset + 8 >= len(self.data):
            return False
        
        # Check for minimum reasonable size
        section = self.data[offset:offset+256]
        
        # Firmware sections should have varied byte patterns (entropy check)
        unique_bytes = len(set(section))
        return unique_bytes > 10  # At least some variation
    
    def scan_suspicious_regions(self):
        """Scan for suspicious/continuous byte patterns that might be firmware"""
        if self.fast_mode:
            return  # Skip in fast mode
            
        self.log("\n[*] Scanning for suspicious firmware regions...")
        
        # Look for repeating patterns that might indicate firmware blocks
        chunk_size = 512
        suspicious_regions = []
        
        for i in range(0, len(self.data) - chunk_size, chunk_size):
            chunk = self.data[i:i+chunk_size]
            
            # Check for high entropy (firmware-like)
            unique_bytes = len(set(chunk))
            entropy_ratio = unique_bytes / 256.0
            
            if entropy_ratio > 0.7:  # High entropy suggests binary firmware
                suspicious_regions.append((i, entropy_ratio))
        
        if suspicious_regions:
            self.log(f"    Found {len(suspicious_regions)} suspicious regions (high entropy)")
            
            # Report top candidates
            suspicious_regions.sort(key=lambda x: x[1], reverse=True)
            for offset, entropy in suspicious_regions[:10]:
                self.log(f"        @ 0x{offset:08x} (entropy: {entropy:.2f})", "DEBUG")
                self.results.append({
                    'type': 'SUSPICIOUS_REGION',
                    'offset': offset,
                    'offset_hex': hex(offset),
                    'entropy': entropy,
                })
    
    def extract_section(self, offset: int, size: int = 512) -> bytes:
        """Extract a section of firmware"""
        end = min(offset + size, len(self.data))
        return self.data[offset:end]
    
    def hexdump(self, data: bytes, offset: int = 0, length: int = None) -> str:
        """Create hex dump of data"""
        if length is None:
            length = len(data)
        
        lines = []
        for i in range(0, min(length, len(data)), 16):
            chunk = data[i:i+16]
            hex_str = ' '.join(f'{b:02x}' for b in chunk)
            ascii_str = ''.join(chr(b) if 32 <= b < 127 else '.' for b in chunk)
            lines.append(f"0x{offset+i:08x}: {hex_str:<48} {ascii_str}")
        
        return '\n'.join(lines)
    
    # ------------------------------------------------------------------
    # CST1 (TPS65994 configuration bundle) support
    # ------------------------------------------------------------------

    def find_cst1(self) -> Optional[int]:
        """Return the file offset of the first CST1 magic, or None."""
        offset = self.data.find(self.CST1_MAGIC)
        return offset if offset != -1 else None

    def extract_cst1(self) -> Optional[bytes]:
        """
        Locate and extract the CST1 TPS65994 configuration bundle.

        The bundle starts at the CST1 magic (10-byte header) and ends after
        the last 0xFF register record.  Returns the raw bytes of the entire
        CST1 section (header + all records), or None if not found.
        """
        cst1_off = self.find_cst1()
        if cst1_off is None:
            return None

        records_start = cst1_off + self.CST1_HEADER_SIZE
        records = _parse_cst1_records(self.data, records_start)
        if not records:
            return None

        # Walk the records again to find the exact end offset
        pos = records_start
        for _ in records:
            stored_len = struct.unpack_from(">H", self.data, pos + 2)[0]
            pos += 4 + stored_len + 1

        return self.data[cst1_off:pos]

    def _decode_sink_pdos(self, payload: bytes) -> List[str]:
        """Decode USB PD sink PDOs from a TX_SINK_CAPS payload."""
        descriptions = []
        if not payload:
            return descriptions
        pdo_count = payload[0]
        for i in range(min(pdo_count, 7)):
            off = 1 + i * 4
            if off + 4 > len(payload):
                break
            pdo = struct.unpack_from("<I", payload, off)[0]
            pdo_type = (pdo >> 30) & 0x3
            if pdo_type == 0:  # Fixed supply
                voltage_mv = ((pdo >> 10) & 0x3FF) * 50
                current_ma = (pdo & 0x3FF) * 10
                descriptions.append(f"Fixed {voltage_mv}mV @ {current_ma}mA")
            elif pdo_type == 2:  # Variable supply
                vmax = ((pdo >> 20) & 0x3FF) * 50
                vmin = ((pdo >> 10) & 0x3FF) * 50
                current_ma = (pdo & 0x3FF) * 10
                descriptions.append(f"Variable {vmin}-{vmax}mV @ {current_ma}mA")
            elif pdo_type == 3:  # PPS APDO
                pps_v_max = ((pdo >> 17) & 0xFF) * 100
                pps_v_min = ((pdo >> 8) & 0xFF) * 100
                pps_i_max = (pdo & 0x7F) * 50
                descriptions.append(f"PPS {pps_v_min}-{pps_v_max}mV @ max {pps_i_max}mA")
            else:
                descriptions.append(f"type={pdo_type} raw=0x{pdo:08x}")
        return descriptions

    def print_cst1_summary(self, cst1_bytes: bytes):
        """Print a human-readable summary of a CST1 bundle."""
        if len(cst1_bytes) < self.CST1_HEADER_SIZE:
            print("  [!] CST1 data too short")
            return

        header = cst1_bytes[:self.CST1_HEADER_SIZE]
        checksum = struct.unpack_from("<H", header, 4)[0]
        records = _parse_cst1_records(cst1_bytes, self.CST1_HEADER_SIZE)

        print(f"\n  CST1 header : {header.hex()}")
        print(f"  Checksum    : 0x{checksum:04x}")
        print(f"  Records     : {len(records)}")
        print(f"  Total size  : {len(cst1_bytes)} bytes\n")

        for reg, payload in records:
            name = CST1_REGISTER_NAMES.get(reg, f"UNKNOWN_0x{reg:02x}")
            hex_val = payload.hex()

            # Extra decoded info for key registers
            extra = ""
            if reg == 0x06:
                try:
                    extra = f'  → "{payload.decode("ascii", errors="replace")}"'
                except Exception:
                    pass
            elif reg == 0x23:
                roles = {0: "Sink", 1: "Source", 2: "DRP", 3: "DRP (prefer)"}
                role_idx = (payload[3] >> 1) & 0x3 if len(payload) >= 4 else 0
                extra = f"  → port role: {roles.get(role_idx, str(role_idx))}"
            elif reg == 0x52 and len(payload) >= 2:
                addr = payload[1] >> 1
                extra = f"  → I2C address: 0x{addr:02x}"
            elif reg in (0x32, 0x33):
                pdos = self._decode_sink_pdos(payload)
                if pdos:
                    extra = "  → " + ", ".join(pdos)

            print(f"  [0x{reg:02x}] {name:<20} {hex_val}{extra}")

    def scan_cst1(self):
        """Scan for CST1 configuration bundle and record the result."""
        self.log("\n[*] Scanning for TPS65994 CST1 configuration bundle (CST1)...")
        offset = self.find_cst1()
        if offset is None:
            self.log("    CST1: Not found")
            return

        cst1_bytes = self.extract_cst1()
        records_start = offset + self.CST1_HEADER_SIZE
        records = _parse_cst1_records(self.data, records_start)

        self.log(f"    Found CST1 @ 0x{offset:08x} — {len(records)} records, "
                 f"{len(cst1_bytes) if cst1_bytes else '?'} bytes")

        self.results.append({
            'type': 'CST1_CONFIG_BUNDLE',
            'offset': offset,
            'offset_hex': hex(offset),
            'record_count': len(records),
            'size': len(cst1_bytes) if cst1_bytes else 0,
            'cst1_bytes': cst1_bytes,
        })

    def generate_report(self):
        """Generate detailed report"""
        print("\n" + "="*80)
        print("TPS65994 USB POWER DELIVERY FIRMWARE SCAN REPORT")
        print("="*80)
        print(f"File: {self.filepath}")
        print(f"File Size: {len(self.data):,} bytes (0x{len(self.data):x})")
        print(f"Total Findings: {len(self.results)}")
        print("-"*80)
        
        # Group results by type
        results_by_type = {}
        for result in self.results:
            result_type = result['type']
            if result_type not in results_by_type:
                results_by_type[result_type] = []
            results_by_type[result_type].append(result)
        
        # Print grouped results
        for result_type, items in results_by_type.items():
            print(f"\n{result_type} ({len(items)}):")
            for item in items[:5]:  # Show first 5 of each type
                offset_hex = item.get('offset_hex', hex(item.get('offset', 0)))
                subtype = item.get('subtype', '')
                entropy = item.get('entropy', '')
                
                details = f"  @ {offset_hex}"
                if subtype:
                    details += f" [{subtype}]"
                if entropy:
                    details += f" entropy={entropy:.2f}"
                
                print(details)
            
            if len(items) > 5:
                print(f"  ... and {len(items) - 5} more")
        
        print("\n" + "="*80)
        print("RECOMMENDATIONS:")
        print("-"*80)
        
        if any(r['type'] == 'CST1_CONFIG_BUNDLE' for r in self.results):
            for r in self.results:
                if r['type'] == 'CST1_CONFIG_BUNDLE':
                    print(f"✓ TPS65994 CST1 config bundle found @ {r['offset_hex']} "
                          f"({r['record_count']} records, {r['size']} bytes)")
                    print("  → Use --extract-cst1 <output.bin> to save for chip reprogramming")
        else:
            print("✗ No TPS65994 CST1 configuration bundle found")

        if any(r['type'] == 'TPS65994_SIGNATURE' for r in self.results):
            print("✓ TPS65994 signatures detected!")
            print("  → Use offsets above to extract firmware sections")
        else:
            print("✗ No TPS65994 signatures found")
            print("  → Check if this is a valid Lenovo BIOS file")
        
        if any(r['type'] == 'FIRMWARE_HEADER' for r in self.results):
            print("✓ Firmware headers detected")
            print("  → Firmware sections identified at listed offsets")
        
        print("="*80)
    
    def scan(self, full_scan: bool = True) -> bool:
        """Execute scan with optional full mode"""
        if not self.load_file():
            return False
        
        if not full_scan:
            # Fast mode - only scan CST1
            self.log("\n[*] Fast mode: Scanning only for CST1 configuration bundle...")
            self.scan_cst1()
            return True
        
        self.scan_tps65994_signatures()
        self.scan_lenovo_markers()
        self.scan_firmware_headers()
        self.scan_suspicious_regions()
        self.scan_cst1()
        self.generate_report()
        
        return True


def main():
    import argparse
    
    parser = argparse.ArgumentParser(
        description='TPS65994 USB Power Delivery Firmware Finder for Lenovo BIOS files'
    )
    parser.add_argument('bios_file', help='Lenovo BIOS .CAP file to scan')
    parser.add_argument('-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument('-o', '--output', help='Save results to file')
    parser.add_argument('-e', '--extract', type=int, metavar='OFFSET', 
                        help='Extract firmware section at given offset (in hex, no 0x prefix)')
    parser.add_argument('-s', '--size', type=int, default=512, metavar='SIZE',
                        help='Size of section to extract (default: 512)')
    parser.add_argument('--extract-cst1', metavar='OUTPUT_FILE', dest='extract_cst1',
                        help='Extract TPS65994 CST1 config bundle and save to OUTPUT_FILE '
                             '(e.g. cst1.bin).  Also prints a register summary.')
    
    args = parser.parse_args()
    
    # Use fast mode if only extracting CST1
    fast_mode = args.extract_cst1 is not None
    scanner = TPS65994Scanner(args.bios_file, verbose=args.verbose, fast_mode=fast_mode)
    
    # Perform scan (full or fast)
    if not scanner.scan(full_scan=not fast_mode):
        sys.exit(1)
    
    if args.extract is not None:
        print(f"\n[*] Extracting section at offset 0x{args.extract:x}...")
        section = scanner.extract_section(args.extract, args.size)
        print(scanner.hexdump(section, offset=args.extract))
        
        if args.output:
            with open(args.output, 'wb') as f:
                f.write(section)
            print(f"[+] Saved to {args.output}")

    if args.extract_cst1:
        print(f"\n[*] Extracting TPS65994 CST1 configuration bundle...")
        cst1_bytes = scanner.extract_cst1()
        if cst1_bytes is None:
            print("[!] CST1 bundle not found in this BIOS file.", file=sys.stderr)
            sys.exit(1)
        scanner.print_cst1_summary(cst1_bytes)
        out_path = Path(args.extract_cst1)
        with open(out_path, 'wb') as f:
            f.write(cst1_bytes)
        print(f"\n[+] CST1 bundle saved to {out_path} ({len(cst1_bytes)} bytes)")


if __name__ == "__main__":
    main()
