import struct
import zlib

GRF_HEADER_SIZE = 0x2E
SIGNATURE = b'Master of Magic\x00'
EVENT_HORIZON_SIGNATURE = b'Event Horizon\x00c\x00'


class GrfFile:
    def __init__(self, path):
        self.path = path
        self.f = open(path, 'rb')
        try:
            self.f.seek(0, 2)
            self.file_size = self.f.tell()
            self.f.seek(0)
            self._load_table()
        except Exception:
            self.f.close()
            raise

    def _read_exact(self, size, description):
        if size < 0 or size > self.file_size - self.f.tell():
            raise ValueError('truncated %s' % description)
        raw = self.f.read(size)
        if len(raw) != size:
            raise ValueError('truncated %s' % description)
        return raw

    @staticmethod
    def _inflate(raw, expected_size, description):
        try:
            inflater = zlib.decompressobj()
            data = inflater.decompress(raw) + inflater.flush()
        except zlib.error as error:
            raise ValueError('invalid compressed %s: %s' % (description, error)) from error
        if not inflater.eof or inflater.unused_data or inflater.unconsumed_tail:
            raise ValueError('incomplete or trailing compressed %s' % description)
        if len(data) != expected_size:
            raise ValueError('size mismatch for %s: got %d expected %d' %
                             (description, len(data), expected_size))
        return data

    def _load_table(self):
        header = self._read_exact(GRF_HEADER_SIZE, 'GRF header')
        if header[:16] == SIGNATURE:
            file_table_offset, seed, encoded_file_count, self.version = struct.unpack_from('<IIII', header, 0x1E)
            # +0x22 is the count seed; +0x2A is the version, not a count.
            file_count = encoded_file_count - seed - 7
            self.format = 'master_of_magic'
            entry_struct = struct.Struct('<IIIBI')
        elif header[:16] == EVENT_HORIZON_SIGNATURE:
            # Exact installed v0x300 profile: uint64 table offset at +1E,
            # direct uint32 count at +26, version at +2A; no seeded count.
            file_table_offset, file_count, self.version = struct.unpack_from('<QII', header, 0x1E)
            if self.version != 0x300:
                raise ValueError('unsupported Event Horizon version: %#x' % self.version)
            self.format = 'event_horizon_300'
            entry_struct = struct.Struct('<IIIBQ')
        else:
            raise ValueError('not a supported GRF file (bad signature): %r' % header[:16])
        if file_count < 0:
            raise ValueError('negative GRF entry count')
        self.file_count = file_count
        self.f.seek(GRF_HEADER_SIZE + file_table_offset)
        if self.format == 'event_horizon_300':
            reserved, table_compressed_size, table_real_size = struct.unpack('<III', self._read_exact(12, 'Event Horizon table header'))
            if reserved != 0:
                raise ValueError('unsupported Event Horizon table reserved value: %#x' % reserved)
        else:
            table_compressed_size, table_real_size = struct.unpack('<II', self._read_exact(8, 'GRF table header'))
        table_compressed = self._read_exact(table_compressed_size, 'GRF compressed table')
        table = self._inflate(table_compressed, table_real_size, 'GRF table')
        self.entries = {}
        pos = 0
        for _ in range(file_count):
            end = table.find(b'\x00', pos)
            if end < 0 or end + 1 + entry_struct.size > len(table):
                raise ValueError('truncated GRF table entry')
            name = table[pos:end].decode('cp949', errors='replace')
            pos = end + 1
            compressed_size, compressed_size_aligned, uncompressed_size, flags, offset = entry_struct.unpack_from(table, pos)
            pos += entry_struct.size
            self.entries[name.replace('\\', '/').lower()] = {
                'name': name,
                'compressed_size': compressed_size,
                'uncompressed_size': uncompressed_size,
                'flags': flags,
                'offset': offset,
            }
        if self.format == 'event_horizon_300' and pos != len(table):
            raise ValueError('Event Horizon direct entry count does not consume table exactly')

    def list_matching(self, substring):
        substring = substring.lower()
        return [e['name'] for k, e in self.entries.items() if substring in k]

    def read(self, name_lower_key):
        entry = self.entries.get(name_lower_key)
        if entry is None:
            return None
        if not (entry['flags'] & 1):
            return None  # directory entry, not a file
        self.f.seek(GRF_HEADER_SIZE + entry['offset'])
        raw = self._read_exact(entry['compressed_size'], 'GRF file ' + name_lower_key)
        return self._inflate(raw, entry['uncompressed_size'], name_lower_key)

    def close(self):
        self.f.close()
