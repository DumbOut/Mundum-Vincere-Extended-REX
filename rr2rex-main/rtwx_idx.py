#!/usr/bin/env python3
"""
rtwx_idx.py - Total War .dat/.idx packer/unpacker (Pure Python)

Reimplements the XIDX tool (v1.6.2) in pure Python 3.
Supports sound (SND.PACK), animation (ANIM.PACK), skeleton (SKEL.PACK),
and event (EVT.PACK) pack files used by Rome: Total War and Medieval II.

Usage:
    python rtwx_idx.py -t <pack.idx>              # list contents
    python rtwx_idx.py -x <pack.idx>              # extract files
    python rtwx_idx.py -c -f <pack.idx> [files]   # create pack

Options:
    -t        list the contents of an idx pack file
    -x        extract an idx pack file
    -c        create an idx pack file
    -f <name> output filename when creating (required with -c)
    -a        treat as animation pack (default: auto-detect)
    -e        treat as event pack
    -s        treat as skeleton pack
    -S        treat as sound pack (default auto-detect behavior)
    -v        verbose output
    -b        strip/add '.bin' suffix (skeleton suffix manipulation)
    -p        preserve paths (disable implicit path mangling)
    -P        preserve paths fully (disable all path mangling including \\ -> /)
    -m        Medieval II format (RTW is default)

Examples:
    # List contents of skeletons.idx
    python rtwx_idx.py -t skeletons.idx

    # Extract all files from music.idx
    python rtwx_idx.py -x music.idx

    # Create a new pack from file list (stdin)
    dir data\\sounds\\SFX\\* /a:-D /s /b | python rtwx_idx.py -c -f sounds.idx

    # Create a skeleton pack from listed files
    python rtwx_idx.py -c -f skeletons.idx file1.cas file2.cas
"""

import struct
import os
import sys
import math
import io

__version__ = "1.0.0"

# ── Magic identifiers ──────────────────────────────────────────────────────
MAGIC_SOUND = b'SND.PACK'
MAGIC_ANIM = b'ANIM.PACK'
MAGIC_SKEL = b'SKEL.PACK'
MAGIC_EVENT = b'EVT.PACK'

# String delimiter used at the end of sound filenames in the idx
STRDELIM = 3452816640  # 0xCDCDCD00

SUFFIX_BIN = 'bin'

# ═══════════════════════════════════════════════════════════════════════════
#  Helpers
# ═══════════════════════════════════════════════════════════════════════════

def _read_exactly(f: io.BufferedReader, n: int, label: str = "data") -> bytes:
    """Read exactly n bytes or raise."""
    data = f.read(n)
    if len(data) != n:
        raise EOFError(f"Unexpected EOF reading {label}: wanted {n} bytes, got {len(data)}")
    return data


def _get_filesize(path: str) -> int:
    return os.path.getsize(path)


def _basename_length(name: str) -> int:
    """Return length of the filename component (after last '/')."""
    idx = name.rfind('/')
    if idx >= 0:
        return len(name) - idx - 1
    return len(name)


def _make_path_relative(path: str, keep_bslash: bool = False) -> str:
    """
    Convert to forward-slash path and try to make it relative to the
    last 'data/' or 'bi/data/' directory component.
    Returns the (possibly modified) path string.
    """
    if not keep_bslash:
        path = path.replace('\\', '/')

    # Try to find the last 'data/' or 'bi/data/'
    ld = path.rfind('data/')
    if ld < 0:
        # Try with backslash just in case
        ld = path.rfind('data\\')
    if ld >= 0:
        # Check if preceded by 'bi/'
        if ld >= 3 and path[ld - 3:ld].lower() == 'bi/':
            return path[ld - 3:]
        # Check bi\ case
        if ld >= 3 and path[ld - 3:ld].lower() == 'bi\\':
            return path[ld - 3:].replace('\\', '/')
        return path[ld:]
    return path


def _un_mangle_name(name: str, suffix: str) -> str:
    """
    When extracting with suffix manipulation, strip the added suffix.
    e.g. 'foo.bin' -> 'foo' if suffix is 'bin'
    """
    s_len = len(suffix)
    if s_len > 0 and len(name) > s_len + 1:
        if name[-(s_len + 1)] == '.' and name[-s_len:].lower() == suffix.lower():
            return name[:-(s_len + 1)]
    return name


def _mangle_name(name: str, suffix: str) -> str:
    """
    When packing with suffix manipulation, add the suffix if a basename
    is longer than suffix+1 (i.e. doesn't already end with .suffix).
    """
    s_len = len(suffix)
    base_len = _basename_length(name)
    if base_len > s_len:
        # Check if it already ends with .suffix
        ext = name[-s_len:]
        if name[-(s_len + 1)] == '.' and ext.lower() == suffix.lower():
            return name
    # Append suffix
    if base_len > 250:
        # Replace existing extension
        dot = name.rfind('.')
        if dot >= 0:
            return name[:dot] + '.' + suffix
    return name + '.' + suffix


def _event_code(num: int) -> str:
    """Return the sorting letter for event pack filenames."""
    if num <= 0:
        return 'a'
    c = int(math.log10(num))
    return chr(c + 97)


def _detect_pack_type(idx_path: str) -> str:
    """Read the magic from an idx file to detect pack type. Returns the magic string (without null)."""
    with open(idx_path, 'rb') as f:
        magic = f.read(9)  # read enough to cover all magics + possible null
    for m in [MAGIC_SOUND, MAGIC_ANIM, MAGIC_SKEL, MAGIC_EVENT]:
        if magic.startswith(m):
            return m.decode('ascii')
    raise ValueError(f"Unknown or invalid idx file: {idx_path}")


# ═══════════════════════════════════════════════════════════════════════════
#  Base classes
# ═══════════════════════════════════════════════════════════════════════════

class IdxSubFile:
    """Represents a single file entry inside an idx/dat archive."""

    def __init__(self):
        self.begin_file_offset: int = 0  # offset in .dat
        self.file_size: int = 0
        self.filename: str = ""
        self.buffer: bytes = None

    def extract(self, dat_fp: io.BufferedReader, outdir: str,
                suffix_manip: bool = False, suffix: str = "") -> bool:
        """Read the file data from .dat and write to disk."""
        dat_fp.seek(self.begin_file_offset)
        data = dat_fp.read(self.file_size)
        if len(data) != self.file_size:
            print(f"  ERROR: short read for {self.filename}", file=sys.stderr)
            return False

        outname = self.filename
        if suffix_manip:
            outname = _mangle_name(outname, suffix)

        # Create directories if needed
        dirpart = os.path.dirname(outname)
        if dirpart:
            os.makedirs(os.path.join(outdir, dirpart), exist_ok=True)

        outpath = os.path.join(outdir, outname)
        with open(outpath, 'wb') as f:
            f.write(data)

        if suffix_manip:
            print(f"  {outname}")
        else:
            print(f"  {self.filename}")
        return True

    def list_entry(self, suffix_manip: bool = False, suffix: str = "") -> None:
        """Print the filename (with optional suffix mangle for verbose listing)."""
        name = self.filename
        if suffix_manip:
            name = _mangle_name(name, suffix)
        print(name)


class IdxFile:
    """Base class for an idx/dat archive."""

    def __init__(self):
        self.filetype: str = ""
        self.file_version: int = 0
        self.num_files: int = 0
        self.sub_files: list = []  # list of IdxSubFile
        self.idx_path: str = ""
        self.dat_path: str = ""

    def open_files(self, filename: str, mode: str = 'rb') -> bool:
        """Given either .idx or .dat path, open both files."""
        name, ext = os.path.splitext(filename)
        ext = ext.lower()

        if ext == '.idx':
            self.idx_path = filename
            self.dat_path = name + '.dat'
        elif ext == '.dat':
            self.idx_path = name + '.idx'
            self.dat_path = filename
        else:
            self.idx_path = filename + '.idx'
            self.dat_path = filename + '.dat'

        if not os.path.exists(self.idx_path):
            print(f"ERROR: {self.idx_path} not found", file=sys.stderr)
            return False
        if not os.path.exists(self.dat_path):
            print(f"ERROR: {self.dat_path} not found", file=sys.stderr)
            return False
        return True

    def detect_from_magic(self) -> bool:
        """Auto-detect pack type from the idx file's magic."""
        magic_str = _detect_pack_type(self.idx_path)
        if magic_str == 'SND.PACK':
            self.filetype = MAGIC_SOUND
        elif magic_str == 'ANIM.PACK':
            self.filetype = MAGIC_ANIM
        elif magic_str == 'SKEL.PACK':
            self.filetype = MAGIC_SKEL
        elif magic_str == 'EVT.PACK':
            self.filetype = MAGIC_EVENT
        else:
            return False
        return True


# ═══════════════════════════════════════════════════════════════════════════
#  Sound pack (SND.PACK)
# ═══════════════════════════════════════════════════════════════════════════

class SoundSubFile(IdxSubFile):
    def __init__(self):
        super().__init__()
        self.control = [0, 0, 0, 0]  # sound-specific metadata

    def read(self, fp: io.BufferedReader) -> bool:
        data = _read_exactly(fp, 4 + 4 + 16, "sound subfile header")
        self.begin_file_offset, self.file_size = struct.unpack_from('<II', data, 0)
        self.control = list(struct.unpack_from('<IIII', data, 8))

        # Read filename (null-terminated by the first null byte of STRDELIM)
        name_bytes = b''
        while True:
            ch = fp.read(1)
            if not ch or ch == b'\0':
                break
            name_bytes += ch
        self.filename = name_bytes.decode('latin-1', errors='replace')
        # Skip the remaining 3 bytes of STRDELIM (\xCD\xCD\xCD)
        _read_exactly(fp, 3, "sound delimiter padding")
        return True

    def write(self, fp: io.BufferedReader) -> bool:
        fp.write(struct.pack('<II', self.begin_file_offset, self.file_size))
        fp.write(struct.pack('<IIII', *self.control))
        fn = self.filename
        fp.write(fn.encode('latin-1', errors='replace'))
        fp.write(struct.pack('<I', STRDELIM))
        return True

    def gather_info(self) -> bool:
        """Auto-detect control values from buffer content."""
        if not self.buffer:
            return False
        # Check for mp3
        if '.mp3' in self.filename.lower():
            self.control = [0, 0, 0, 13]  # MP3TAG = 13
        else:
            # Find 'fmt ' marker in WAV data
            data = self.buffer
            fmt_mark = b'fmt '
            idx = data.find(fmt_mark)
            if idx >= 0:
                # control[0] = *(iptr+3)   -> 4 bytes starting at fmt+12
                # control[1] = 16
                # control[2] = *( (short*)(iptr) + 5 ) -> short at fmt+10
                # control[3] = *( (short*)(iptr) + 4 ) == 1 ? 1 : 2 -> short at fmt+8
                if idx + 16 <= len(data):
                    self.control[0] = struct.unpack_from('<I', data, idx + 12)[0]
                    self.control[1] = 16
                    self.control[2] = struct.unpack_from('<H', data, idx + 10)[0]
                    audio_fmt = struct.unpack_from('<H', data, idx + 8)[0]
                    self.control[3] = 1 if audio_fmt == 1 else 2
        return True


class SoundIdxFile(IdxFile):
    def __init__(self):
        super().__init__()
        self.filetype = MAGIC_SOUND
        self.file_version = 4

    def read_header(self) -> bool:
        with open(self.idx_path, 'rb') as f:
            magic = f.read(len(MAGIC_SOUND))
            if magic != MAGIC_SOUND:
                print(f"ERROR: Not a sound idx archive", file=sys.stderr)
                return False
            f.seek(12)
            raw = _read_exactly(f, 4, "numFiles")
            self.num_files = struct.unpack('<I', raw)[0]

        # Read all subfiles
        self.sub_files = []
        with open(self.idx_path, 'rb') as f:
            f.seek(24)  # skip header
            for i in range(self.num_files):
                sf = SoundSubFile()
                sf.read(f)
                self.sub_files.append(sf)
        return True

    def write_header(self, fp_idx, fp_dat) -> None:
        fp_idx.seek(0)
        fp_dat.seek(0)
        fp_idx.write(MAGIC_SOUND)
        fp_idx.write(struct.pack('<III', self.file_version, self.num_files, 0))
        fp_idx.write(struct.pack('<I', 0))
        fp_dat.write(MAGIC_SOUND)
        fp_dat.write(struct.pack('<III', self.file_version, self.num_files, 0))
        fp_dat.write(struct.pack('<I', 0))
        fp_idx.flush()
        fp_dat.flush()


# ═══════════════════════════════════════════════════════════════════════════
#  Animation pack (ANIM.PACK)
# ═══════════════════════════════════════════════════════════════════════════

class AnimSubFile(IdxSubFile):
    def __init__(self, allow_scaling: bool = False):
        super().__init__()
        self.entry_size: int = 0
        self.scale: float = 1.0
        self.num_frames: int = 0
        self.num_bones: int = 0
        self.type: int = 0
        self.allow_scaling = allow_scaling

    def read(self, fp: io.BufferedReader) -> bool:
        data = _read_exactly(fp, 4 + 4 + 4 + 4 + 2 + 2 + 1, "anim subfile header")
        self.entry_size = struct.unpack_from('<I', data, 0)[0]
        self.begin_file_offset = struct.unpack_from('<I', data, 4)[0]
        self.file_size = struct.unpack_from('<I', data, 8)[0]
        self.scale = struct.unpack_from('<f', data, 12)[0]
        self.num_frames = struct.unpack_from('<h', data, 16)[0]
        self.num_bones = struct.unpack_from('<h', data, 18)[0]
        self.type = struct.unpack_from('<b', data, 20)[0]

        sz = self.entry_size - 9
        if sz > 256:
            sz = 256  # safety cap
        name_bytes = _read_exactly(fp, sz, "anim filename")
        # Find null terminator
        null_pos = name_bytes.find(b'\0')
        if null_pos >= 0:
            name_bytes = name_bytes[:null_pos]
        self.filename = name_bytes.decode('latin-1', errors='replace')
        return True

    def write(self, fp: io.BufferedReader) -> bool:
        # Recalculate entry size
        fname_bytes = self.filename.encode('latin-1', errors='replace')
        ll = len(fname_bytes) + 1  # + null terminator
        esize = ll + 9

        fp.write(struct.pack('<I', esize))
        fp.write(struct.pack('<I', self.begin_file_offset))
        fp.write(struct.pack('<I', self.file_size))
        fp.write(struct.pack('<f', self.scale))
        fp.write(struct.pack('<h', self.num_frames))
        fp.write(struct.pack('<h', self.num_bones))
        fp.write(struct.pack('<b', self.type))
        fp.write(fname_bytes + b'\0')
        return True

    def scale_buffer(self) -> bool:
        if not self.buffer:
            return False
        if self.scale != 1.0 and self.buffer[4] == 1:
            offset = self.num_frames * self.num_bones * 16 + 5
            loop = self.num_frames * 3 * 2 + (4 * ((self.num_frames - 1) // 2)) + 8
            buf_len = len(self.buffer)
            data_arr = bytearray(self.buffer)
            for i in range(loop):
                f_offset = offset + i * 4
                if f_offset + 4 <= buf_len:
                    val = struct.unpack_from('<f', data_arr, f_offset)[0]
                    struct.pack_into('<f', data_arr, f_offset, val * self.scale)
            self.buffer = bytes(data_arr)
        return True

    def prepare_data_out(self) -> bool:
        if self.allow_scaling:
            self.scale = 1.0 / self.scale
            self.scale_buffer()
            self.scale = 1.0 / self.scale
        return True

    def parse_filename(self, name: str) -> bool:
        if not self.allow_scaling:
            self.filename = name
            return True
        idx = name.lower().rfind(';scale=')
        if idx >= 0:
            try:
                self.scale = float(name[idx+7:])
            except ValueError:
                self.scale = 1.0
            self.filename = name[:idx]
        else:
            self.scale = 1.0
            self.filename = name
        return True

    def gather_info(self) -> bool:
        if not self.buffer:
            return False
        self.entry_size = len(self.filename) + 10
        self.num_frames = struct.unpack_from('<h', self.buffer, 0)[0]
        self.num_bones = struct.unpack_from('<h', self.buffer, 2)[0]
        self.type = self.buffer[4]
        if self.allow_scaling:
            self.scale_buffer()
        return True


class AnimIdxFile(IdxFile):
    def __init__(self):
        super().__init__()
        self.filetype = MAGIC_ANIM
        self.file_version = 4  # RTW version

    def read_header(self) -> bool:
        with open(self.idx_path, 'rb') as f:
            magic = f.read(len(MAGIC_ANIM))
            if magic != MAGIC_ANIM:
                print(f"ERROR: Not an animation idx archive", file=sys.stderr)
                return False
            f.seek(16)
            raw = _read_exactly(f, 4, "numFiles")
            self.num_files = struct.unpack('<I', raw)[0]

        # Read all subfiles
        self.sub_files = []
        with open(self.idx_path, 'rb') as f:
            f.seek(20)  # header size: 10(magic+null) + 2(short) + 4(ver) + 4(num)
            for i in range(self.num_files):
                sf = AnimSubFile(allow_scaling=(self.file_version == 4))
                sf.read(f)
                self.sub_files.append(sf)
        return True

    def write_header(self, fp_idx, fp_dat) -> None:
        fp_idx.seek(0)
        fp_dat.seek(0)
        zero16 = struct.pack('<h', 0)
        fp_idx.write(MAGIC_ANIM + b'\0')
        fp_idx.write(zero16)
        fp_idx.write(struct.pack('<II', self.file_version, self.num_files))
        fp_dat.write(MAGIC_ANIM + b'\0')
        fp_dat.write(zero16)
        fp_dat.write(struct.pack('<II', self.file_version, self.num_files))
        fp_idx.flush()
        fp_dat.flush()


# ═══════════════════════════════════════════════════════════════════════════
#  Skeleton pack (SKEL.PACK)
# ═══════════════════════════════════════════════════════════════════════════

class SkeletonSubFile(IdxSubFile):
    def __init__(self):
        super().__init__()
        self.name_len: int = 0

    def read(self, fp: io.BufferedReader) -> bool:
        data = _read_exactly(fp, 4 + 4 + 4, "skel subfile")
        self.name_len = struct.unpack_from('<I', data, 0)[0]
        self.begin_file_offset = struct.unpack_from('<I', data, 4)[0]
        self.file_size = struct.unpack_from('<I', data, 8)[0]
        name_bytes = _read_exactly(fp, self.name_len, "skel filename")
        self.filename = name_bytes.rstrip(b'\0').decode('latin-1', errors='replace')
        return True

    def write(self, fp: io.BufferedReader) -> bool:
        fname_bytes = (self.filename + '\0').encode('latin-1', errors='replace')
        self.name_len = len(fname_bytes)
        fp.write(struct.pack('<I', self.name_len))
        fp.write(struct.pack('<I', self.begin_file_offset))
        fp.write(struct.pack('<I', self.file_size))
        fp.write(fname_bytes)
        return True

    def gather_info(self) -> bool:
        if not self.buffer:
            return False
        self.name_len = len(self.filename) + 1
        return True


class SkeletonIdxFile(IdxFile):
    def __init__(self):
        super().__init__()
        self.filetype = MAGIC_SKEL
        self.file_version = 3  # RTW version

    def read_header(self) -> bool:
        with open(self.idx_path, 'rb') as f:
            magic = f.read(len(MAGIC_SKEL))
            if magic != MAGIC_SKEL:
                print(f"ERROR: Not a skeleton idx archive", file=sys.stderr)
                return False
            f.seek(16)
            raw = _read_exactly(f, 4, "numFiles")
            self.num_files = struct.unpack('<I', raw)[0]

        self.sub_files = []
        with open(self.idx_path, 'rb') as f:
            f.seek(20)
            for i in range(self.num_files):
                sf = SkeletonSubFile()
                sf.read(f)
                self.sub_files.append(sf)
        return True

    def write_header(self, fp_idx, fp_dat) -> None:
        fp_idx.seek(0)
        fp_dat.seek(0)
        zero16 = struct.pack('<h', 0)
        fp_idx.write(MAGIC_SKEL + b'\0')
        fp_idx.write(zero16)
        fp_idx.write(struct.pack('<II', self.file_version, self.num_files))
        fp_dat.write(MAGIC_SKEL + b'\0')
        fp_dat.write(zero16)
        fp_dat.write(struct.pack('<II', self.file_version, self.num_files))
        fp_idx.flush()
        fp_dat.flush()


# ═══════════════════════════════════════════════════════════════════════════
#  Event pack (EVT.PACK)
# ═══════════════════════════════════════════════════════════════════════════

class EventSubFile(IdxSubFile):
    def __init__(self):
        super().__init__()
        self.frame_id: int = 0
        self.num: int = 0
        self.tainted: bool = False

    def read(self, fp: io.BufferedReader) -> bool:
        rlen_data = _read_exactly(fp, 4, "event record_len")
        rlen = struct.unpack('<I', rlen_data)[0]
        if rlen != 4:
            print(f"ERROR: Bad record length {rlen}", file=sys.stderr)
            return False
        data = _read_exactly(fp, 4 + 4 + 4, "event subfile")
        self.begin_file_offset = struct.unpack('<I', data, 0)[0]
        self.file_size = struct.unpack('<I', data, 4)[0]
        new_frame = struct.unpack('<I', data, 8)[0]
        if new_frame != getattr(self, '_last_frame', -1):
            self.num = 0
            self._last_frame = new_frame
        self.frame_id = new_frame
        self.num += 1
        self.filename = f"{self.frame_id}_{_event_code(self.num)}_{self.num}.bin"
        return True

    def write(self, fp: io.BufferedReader) -> bool:
        fp.write(struct.pack('<I', 4))  # record length = 4
        fp.write(struct.pack('<I', self.begin_file_offset))
        fp.write(struct.pack('<I', self.file_size))
        fp.write(struct.pack('<I', self.frame_id))
        return True

    def parse_filename(self, name: str) -> bool:
        """Parse event filename to extract frame_id."""
        base = os.path.basename(name)
        self.filename = base
        # Expect format: <type>_<letter>_<num>.bin
        # We need the type number (frameId)
        parts = base.split('_')
        if parts and parts[0].isdigit():
            self.frame_id = int(parts[0])
            if self.frame_id < 1 or self.frame_id > 4:
                print(f"WARNING: Invalid event type {self.frame_id} in {base}", file=sys.stderr)
                self.tainted = True
                return False
            self.tainted = False
            return True
        self.tainted = True
        return False

    def gather_info(self) -> bool:
        return self.buffer is not None


class EventIdxFile(IdxFile):
    def __init__(self):
        super().__init__()
        self.filetype = MAGIC_EVENT
        self.file_version = 0x30  # RTW version

    def read_header(self) -> bool:
        with open(self.idx_path, 'rb') as f:
            magic = f.read(len(MAGIC_EVENT))
            if magic != MAGIC_EVENT:
                print(f"ERROR: Not an event idx archive", file=sys.stderr)
                return False
            f.seek(16)
            raw = _read_exactly(f, 4, "numFiles")
            self.num_files = struct.unpack('<I', raw)[0]

        self.sub_files = []
        with open(self.idx_path, 'rb') as f:
            f.seek(22)  # header: 9(magic+null) + 4(zero) + 4(ver) + 4(num) = 21? Let's compute:
                         # magic+null=9, zero int=4 => 13, ver=4 => 17, numFiles=4 => 21
                         # Actually after fseek(16) we read numFiles at offset 18... hmm
                         # Let me just skip to 21 to be safe based on WriteHeader
            # WriteHeader: magic+null (9), zero int (4), fileVersion (4), numFiles (4) = 21 total for idx
            # But ReadHeader fseeks to 16, reads numFiles... that could read at different offset
            # This is a quirk of the original. Let's just start reading subfiles after the header.
            # The subfile entries follow numFiles. We'll skip ahead.
            # Actually let's just seek past what we know:
            # Header size = f.tell() after header read + 4 bytes for numFiles
            # Let me recalculate: for EVT, ReadHeader fseeks to 16 and reads numFiles (4 bytes) at offset 16
            # So 16 + 4 = 20 is where subfiles start.
            f.seek(20)

            # Track frameId across entries
            last_frame = -1
            running_num = 0
            for i in range(self.num_files):
                sf = EventSubFile()
                # Read manually to handle sequential numbering
                rlen_data = _read_exactly(f, 4, "event record_len")
                rlen = struct.unpack('<I', rlen_data)[0]
                if rlen != 4:
                    print(f"ERROR: Bad record length {rlen}", file=sys.stderr)
                    return False
                data = _read_exactly(f, 4 + 4 + 4, "event subfile")
                sf.begin_file_offset = struct.unpack('<I', data, 0)[0]
                sf.file_size = struct.unpack('<I', data, 4)[0]
                new_frame = struct.unpack('<I', data, 8)[0]
                if new_frame != last_frame:
                    running_num = 0
                    last_frame = new_frame
                sf.frame_id = new_frame
                running_num += 1
                sf.num = running_num
                sf.filename = f"{sf.frame_id}_{_event_code(sf.num)}_{sf.num}.bin"
                self.sub_files.append(sf)
        return True

    def write_header(self, fp_idx, fp_dat) -> None:
        fp_idx.seek(0)
        fp_dat.seek(0)
        fp_idx.write(MAGIC_EVENT + b'\0')
        fp_idx.write(struct.pack('<III', 0, self.file_version, self.num_files))
        fp_dat.write(MAGIC_EVENT + b'\0')
        fp_dat.write(struct.pack('<III', 0, self.file_version, self.num_files))
        fp_idx.flush()
        fp_dat.flush()


# ═══════════════════════════════════════════════════════════════════════════
#  Factory
# ═══════════════════════════════════════════════════════════════════════════

def create_idx_file(magic_str: str, is_medieval: bool = False) -> IdxFile:
    """Create the appropriate IdxFile instance based on magic string."""
    if magic_str == 'SND.PACK':
        sf = SoundIdxFile()
        if is_medieval:
            sf.file_version = 5
        return sf
    elif magic_str == 'ANIM.PACK':
        af = AnimIdxFile()
        if is_medieval:
            af.file_version = 9
        return af
    elif magic_str == 'SKEL.PACK':
        kf = SkeletonIdxFile()
        if is_medieval:
            kf.file_version = 0x18000E  # 1572878
        return kf
    elif magic_str == 'EVT.PACK':
        ef = EventIdxFile()
        if is_medieval:
            ef.file_version = 0x49  # 73
        return ef
    raise ValueError(f"Unknown pack type: {magic_str}")


# ═══════════════════════════════════════════════════════════════════════════
#  Packing logic
# ═══════════════════════════════════════════════════════════════════════════

def _build_pack(pack: IdxFile, output_name: str, files: list,
                suffix_manip: bool = False, suffix: str = "",
                preserve_paths: bool = False, keep_bslash: bool = False) -> bool:
    """
    Build an idx/dat pack from a list of file paths.
    """
    pack.file_version = getattr(pack, 'file_version', 4)
    pack.num_files = 0

    # Open output files
    if output_name.endswith('.idx'):
        idx_path = output_name
        dat_path = output_name[:-4] + '.dat'
    elif output_name.endswith('.dat'):
        idx_path = output_name[:-4] + '.idx'
        dat_path = output_name
    else:
        idx_path = output_name + '.idx'
        dat_path = output_name + '.dat'

    fp_idx = open(idx_path, 'wb')
    fp_dat = open(dat_path, 'wb')
    pack.write_header(fp_idx, fp_dat)

    # Pre-process file list to expand any directories while preserving relative structure inside them
    expanded_files = []
    for fpath in files:
        fpath = fpath.strip()
        if not fpath:
            continue
        if os.path.isdir(fpath):
            for root, _, filenames in os.walk(fpath):
                for filename in filenames:
                    file_on_disk = os.path.join(root, filename)
                    # Path inside the folder
                    rel_path = os.path.relpath(file_on_disk, fpath)
                    expanded_files.append((file_on_disk, rel_path, True))
        else:
            expanded_files.append((fpath, fpath, False))

    success_count = 0
    for fpath, rel_path, is_walked in expanded_files:
        # If fpath has a scale suffix, strip it to read the physical file on disk
        scale_idx = fpath.lower().rfind(';scale=')
        actual_fpath = fpath[:scale_idx] if scale_idx >= 0 else fpath

        if not os.path.isfile(actual_fpath):
            print(f"  SKIP (not a file): {actual_fpath}", file=sys.stderr)
            continue

        # Determine filename to store in the index (retaining scale if present)
        if isinstance(pack, SkeletonIdxFile) and not preserve_paths:
            # Skeleton packs store only basename by default
            # But if walked from a directory and has subfolders, preserve the structure!
            if is_walked and '/' in rel_path.replace('\\', '/'):
                stored_name = rel_path.replace('\\', '/')
            else:
                stored_name = os.path.basename(fpath)
        else:
            if preserve_paths:
                stored_name = rel_path.replace('\\', '/') if not keep_bslash else rel_path
            else:
                stored_name = _make_path_relative(rel_path, keep_bslash)

        # Handle suffix manipulation for packing
        if suffix_manip:
            stored_name = _un_mangle_name(stored_name, suffix)

        # Create the appropriate subfile
        sf = None
        if isinstance(pack, SoundIdxFile):
            sf = SoundSubFile()
        elif isinstance(pack, AnimIdxFile):
            sf = AnimSubFile(allow_scaling=(pack.file_version == 4))
        elif isinstance(pack, SkeletonIdxFile):
            sf = SkeletonSubFile()
        elif isinstance(pack, EventIdxFile):
            sf = EventSubFile()

        if sf is None:
            print(f"  ERROR: Unknown pack type", file=sys.stderr)
            continue

        if hasattr(sf, 'parse_filename'):
            if not sf.parse_filename(stored_name):
                print(f"  SKIP (bad name parsing): {fpath}", file=sys.stderr)
                continue
        else:
            sf.filename = stored_name

        # Read file data from the physical path
        try:
            with open(actual_fpath, 'rb') as f:
                sf.buffer = f.read()
        except (IOError, OSError) as e:
            print(f"  ERROR reading {actual_fpath}: {e}", file=sys.stderr)
            continue

        sf.file_size = len(sf.buffer)
        sf.begin_file_offset = fp_dat.tell()

        # Gather metadata (e.g. control values for sound, frames/bones for anim)
        if not sf.gather_info():
            print(f"  ERROR gathering info for {fpath}", file=sys.stderr)
            continue

        # Write to dat
        fp_dat.write(sf.buffer)

        # Write to idx
        if not sf.write(fp_idx):
            print(f"  ERROR writing index entry for {fpath}", file=sys.stderr)
            continue

        pack.num_files += 1
        success_count += 1
        print(f"  Packed: {fpath} -> {stored_name}")

    # Update header with final numFiles
    pack.write_header(fp_idx, fp_dat)
    fp_idx.close()
    fp_dat.close()
    print(f"\nPacked {success_count} file(s) into {idx_path} / {dat_path}")
    return success_count > 0


def _extract_pack(pack: IdxFile, filename: str, list_only: bool = False,
                  suffix_manip: bool = False, suffix: str = "", outdir: str = None) -> bool:
    """Extract or list the contents of an idx/dat archive."""
    if not pack.open_files(filename):
        return False

    if not pack.read_header():
        return False

    if outdir is None:
        outdir = os.path.splitext(os.path.basename(filename))[0] + "_unpacked"
    if not list_only:
        os.makedirs(outdir, exist_ok=True)
        print(f"Extracting to: {outdir}/")

    with open(pack.dat_path, 'rb') as dat_fp:
        success = 0
        extracted_paths = []
        for i, sf in enumerate(pack.sub_files):
            if list_only:
                sf.list_entry(suffix_manip, suffix)
                success += 1
            else:
                # Read the data from dat
                dat_fp.seek(sf.begin_file_offset)
                data = dat_fp.read(sf.file_size)
                if len(data) != sf.file_size:
                    print(f"  ERROR: short read for {sf.filename}", file=sys.stderr)
                    continue

                outname = sf.filename
                if suffix_manip:
                    outname = _mangle_name(outname, suffix)

                dirpart = os.path.dirname(outname)
                if dirpart:
                    os.makedirs(os.path.join(outdir, dirpart), exist_ok=True)

                disk_path = os.path.join(outdir, outname)

                # Prepare data out (e.g. unscale scaled anims)
                sf.buffer = data
                if hasattr(sf, 'prepare_data_out'):
                    sf.prepare_data_out()
                    data = sf.buffer

                with open(disk_path, 'wb') as outf:
                    outf.write(data)
                print(f"  {outname}")

                list_name = outname
                if getattr(sf, 'scale', 1.0) != 1.0:
                    list_name = f"{outname};scale={sf.scale}"
                extracted_paths.append(os.path.join(outdir, list_name).replace('\\', '/'))
                success += 1

        if not list_only and success > 0:
            files_txt_path = os.path.join(outdir, 'files.txt')
            with open(files_txt_path, 'w', encoding='utf-8') as f_list:
                for p in extracted_paths:
                    f_list.write(p + '\n')
            print(f"Generated extraction file list: {files_txt_path}")

    if not list_only:
        print(f"\nExtracted {success}/{pack.num_files} files")
    return True


# ═══════════════════════════════════════════════════════════════════════════
#  Main CLI
# ═══════════════════════════════════════════════════════════════════════════

def main():
    import getopt

    try:
        opts, args = getopt.gnu_getopt(sys.argv[1:],
                                       'txcf:o:aseSvbpmPi:',
                                       ['help'])
    except getopt.GetoptError as e:
        print(f"Error: {e}", file=sys.stderr)
        print(usage())
        sys.exit(1)

    list_mode = False
    extract_mode = False
    create_mode = False
    force_type = None  # 'a', 'e', 's', 'S' (None = auto-detect)
    output_name = None
    output_dir = None
    verbose = False
    suffix_manip = False
    suffix = SUFFIX_BIN
    preserve_paths = False
    keep_bslash = False
    medieval = False
    input_list_file = None

    for opt, val in opts:
        if opt == '-t':
            list_mode = True
        elif opt == '-x':
            extract_mode = True
        elif opt == '-c':
            create_mode = True
        elif opt == '-f':
            output_name = val
        elif opt == '-o':
            output_dir = val
        elif opt == '-a':
            force_type = 'ANIM.PACK'
        elif opt == '-s':
            force_type = 'SKEL.PACK'
        elif opt == '-e':
            force_type = 'EVT.PACK'
        elif opt == '-S':
            force_type = 'SND.PACK'
        elif opt == '-v':
            verbose = True
        elif opt == '-b':
            suffix_manip = True
            suffix = 'bin'
        elif opt == '-B':
            suffix_manip = True
            # The -B option takes an argument in XIDX
            # But we handle it differently since getopt doesn't support -B with arg in short opts
            # We'll re-parse manually if needed
            print("WARNING: -B option not fully supported, use -b for .bin suffix", file=sys.stderr)
        elif opt == '-p':
            preserve_paths = True
        elif opt == '-P':
            preserve_paths = True
            keep_bslash = True
        elif opt == '-m':
            medieval = True
        elif opt == '-i':
            input_list_file = val
        elif opt in ('--help', '-h'):
            print(usage())
            sys.exit(0)

    # Validate modes
    modes = sum([list_mode, extract_mode, create_mode])
    if modes == 0:
        print("ERROR: Must specify one of -t (list), -x (extract), or -c (create)", file=sys.stderr)
        print(usage())
        sys.exit(1)
    if modes > 1:
        print("ERROR: May only specify one of -t, -x, -c", file=sys.stderr)
        sys.exit(1)

    if create_mode and not output_name:
        print("ERROR: -f <output> is required with -c (create)", file=sys.stderr)
        sys.exit(1)

    # ── List or Extract mode ──
    if list_mode or extract_mode:
        if not args:
            print("ERROR: No idx file specified", file=sys.stderr)
            print(usage())
            sys.exit(1)

        filename = args[0]

        # Auto-detect type or use forced type
        if force_type:
            magic_str = force_type
        else:
            try:
                magic_str = _detect_pack_type(filename)
            except ValueError as e:
                print(f"ERROR: {e}", file=sys.stderr)
                sys.exit(1)

        pack = create_idx_file(magic_str, medieval)
        success = _extract_pack(pack, filename, list_only=list_mode,
                                suffix_manip=suffix_manip, suffix=suffix, outdir=output_dir)
        sys.exit(0 if success else 1)

    # ── Create mode ──
    if create_mode:
        files = list(args)  # files on command line

        if input_list_file:
            if os.path.exists(input_list_file):
                with open(input_list_file, 'r', encoding='utf-8') as f_list:
                    files = [line.strip() for line in f_list if line.strip()]
            else:
                print(f"ERROR: File list '{input_list_file}' not found", file=sys.stderr)
                sys.exit(1)

        # If no files given, read from stdin
        elif not files:
            files = [line.strip() for line in sys.stdin if line.strip()]

        if not files:
            print("ERROR: No files specified for packing", file=sys.stderr)
            sys.exit(1)

        if not force_type:
            # Try to auto-detect from the output name? No, default to sound.
            # Without -a/-e/-s/-S, XIDX defaults to sound.
            print("Assuming sound pack type (use -a, -e, -s, -S to specify)", file=sys.stderr)
            magic_str = 'SND.PACK'
        else:
            magic_str = force_type

        pack = create_idx_file(magic_str, medieval)
        success = _build_pack(pack, output_name or 'default', files,
                              suffix_manip=suffix_manip, suffix=suffix,
                              preserve_paths=preserve_paths, keep_bslash=keep_bslash)
        sys.exit(0 if success else 1)


def usage() -> str:
    return f"""\
rtwx_idx.py v{__version__} - Total War .dat/.idx packer/unpacker

Usage: python rtwx_idx.py [options] [files...]

Options:
  -t              List contents of an idx pack
  -x              Extract an idx pack
  -c              Create an idx pack
  -f <name>       Output filename when creating (required with -c)
  -o <dir>        Output directory when extracting (optional)
  -a              Animation pack (ANIM.PACK)
  -e              Event pack (EVT.PACK)
  -s              Skeleton pack (SKEL.PACK)
  -S              Sound pack (SND.PACK)
  -m              Medieval II format (default: RTW)
  -v              Verbose output
  -b              Strip/add '.bin' suffix (skeleton suffix manipulation)
  -i <file>       Text file containing a list of files to pack (one per line)
  -p              Preserve paths (disable implicit path mangling)
  -P              Preserve paths fully (disable all path mangling)
  --help, -h      Show this help

Examples:
  python rtwx_idx.py -t skeletons.idx          # list contents
  python rtwx_idx.py -x music.idx              # extract
  python rtwx_idx.py -c -f pack.idx file1 file2  # create from args
  type files.txt | python rtwx_idx.py -c -f pack.idx  # create from stdin
"""


if __name__ == '__main__':
    main()