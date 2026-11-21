"""Frame an Annex-B H.264 byte stream into complete access units without decoding."""

from __future__ import annotations

MAX_NAL_BYTES = 16 * 1024 * 1024
MAX_ACCESS_UNIT_BYTES = 32 * 1024 * 1024
_START_3 = b"\x00\x00\x01"
_START_4 = b"\x00\x00\x00\x01"


class H264FramingError(ValueError):
    """Raised when an encoded H.264 boundary cannot be identified safely."""


def _start_codes(data: bytearray) -> list[tuple[int, int]]:
    result = []
    index = 0
    while index + 3 <= len(data):
        if data[index:index + 4] == _START_4:
            result.append((index, 4))
            index += 4
        elif data[index:index + 3] == _START_3:
            result.append((index, 3))
            index += 3
        else:
            index += 1
    return result


class AnnexBNalFramer:
    """Split arbitrary read chunks into complete Annex-B NAL units."""

    def __init__(self):
        self.buffer = bytearray()

    def feed(self, chunk: bytes) -> list[bytes]:
        self.buffer.extend(chunk)
        output = []
        while True:
            starts = _start_codes(self.buffer)
            if not starts:
                if len(self.buffer) > 3:
                    del self.buffer[:-3]
                break
            if starts[0][0]:
                del self.buffer[:starts[0][0]]
                continue
            if len(starts) < 2:
                if len(self.buffer) > MAX_NAL_BYTES:
                    raise H264FramingError("H.264 NAL unit exceeded the size limit.")
                break
            boundary = starts[1][0]
            nal = bytes(self.buffer[:boundary])
            if len(nal) > starts[0][1]:
                output.append(nal)
            del self.buffer[:boundary]
        return output

    def flush(self) -> list[bytes]:
        starts = _start_codes(self.buffer)
        if not starts:
            self.buffer.clear()
            return []
        if starts[0][0]:
            del self.buffer[:starts[0][0]]
            starts = _start_codes(self.buffer)
        if not starts or len(self.buffer) <= starts[0][1]:
            self.buffer.clear()
            return []
        nal = bytes(self.buffer)
        self.buffer.clear()
        return [nal]


def _nal_header(nal: bytes) -> tuple[int, int]:
    if nal.startswith(_START_4):
        offset = 4
    elif nal.startswith(_START_3):
        offset = 3
    else:
        raise H264FramingError("H.264 NAL is missing its Annex-B start code.")
    if len(nal) <= offset:
        raise H264FramingError("H.264 NAL is missing its header.")
    return offset, nal[offset] & 0x1F


def _first_mb_in_slice(nal: bytes) -> int | None:
    """Read only first_mb_in_slice; no video decoding or codec conversion occurs."""
    offset, nal_type = _nal_header(nal)
    if nal_type not in (1, 2, 5):
        return None

    rbsp = bytearray()
    zero_count = 0
    for value in nal[offset + 1:]:
        if zero_count >= 2 and value == 0x03:
            continue
        rbsp.append(value)
        zero_count = zero_count + 1 if value == 0 else 0

    bit_position = 0

    def read_bit() -> int:
        nonlocal bit_position
        if bit_position >= len(rbsp) * 8:
            raise H264FramingError("Truncated H.264 slice header.")
        value = (rbsp[bit_position // 8] >> (7 - bit_position % 8)) & 1
        bit_position += 1
        return value

    leading_zero_bits = 0
    while read_bit() == 0:
        leading_zero_bits += 1
        if leading_zero_bits > 31:
            raise H264FramingError("Invalid H.264 first_mb_in_slice value.")

    suffix = 0
    for _ in range(leading_zero_bits):
        suffix = (suffix << 1) | read_bit()
    return (1 << leading_zero_bits) - 1 + suffix


class H264AccessUnitFramer:
    """Group NAL units into access units suitable for rtph264pay alignment=au."""

    _PREFIX_NAL_TYPES = {6, 7, 8, 14, 15, 16, 17, 18, 19, 20, 21}

    def __init__(self):
        self.nals = AnnexBNalFramer()
        self.current: list[bytes] = []
        self.current_size = 0
        self.has_vcl = False

    def _take_access_unit(self) -> bytes | None:
        if not self.current or not self.has_vcl:
            self.current.clear()
            self.current_size = 0
            self.has_vcl = False
            return None
        result = b"".join(self.current)
        self.current.clear()
        self.current_size = 0
        self.has_vcl = False
        return result

    def _append(self, nal: bytes) -> None:
        self.current.append(nal)
        self.current_size += len(nal)
        if self.current_size > MAX_ACCESS_UNIT_BYTES:
            raise H264FramingError("H.264 access unit exceeded the size limit.")

    def _consume_nals(self, nals: list[bytes]) -> list[bytes]:
        output = []
        for nal in nals:
            _offset, nal_type = _nal_header(nal)
            if nal_type == 9:  # AUD marks the beginning of an access unit.
                if self.has_vcl:
                    previous = self._take_access_unit()
                    if previous is not None:
                        output.append(previous)
                self._append(nal)
                continue

            if nal_type in (1, 2, 5):  # Coded slice; first_mb==0 starts a new picture.
                first_mb = _first_mb_in_slice(nal)
                if self.has_vcl and first_mb == 0:
                    previous = self._take_access_unit()
                    if previous is not None:
                        output.append(previous)
                self._append(nal)
                self.has_vcl = True
                continue

            if self.has_vcl and nal_type in self._PREFIX_NAL_TYPES:
                previous = self._take_access_unit()
                if previous is not None:
                    output.append(previous)
            self._append(nal)
        return output

    def feed(self, chunk: bytes) -> list[bytes]:
        return self._consume_nals(self.nals.feed(chunk))

    def flush(self) -> list[bytes]:
        output = self._consume_nals(self.nals.flush())
        final = self._take_access_unit()
        if final is not None:
            output.append(final)
        else:
            self.current.clear()
            self.current_size = 0
        return output



def inspect_h264_access_unit(access_unit: bytes) -> dict:
    """Extract in-band parameter sets and IDR presence without decoding."""
    framer = AnnexBNalFramer()
    nals = framer.feed(access_unit)
    nals.extend(framer.flush())
    result = {"sps": b"", "pps": b"", "has_sps": False, "has_pps": False, "has_idr": False}
    for nal in nals:
        _offset, nal_type = _nal_header(nal)
        if nal_type == 7:
            result["sps"] = nal
            result["has_sps"] = True
        elif nal_type == 8:
            result["pps"] = nal
            result["has_pps"] = True
        elif nal_type == 5:
            result["has_idr"] = True
    return result
