"""Tests for the native TF03 serial frame parser."""


def _frame(distance_cm: int, strength: int) -> bytes:
    body = bytes(
        [
            0x59,
            0x59,
            distance_cm & 0xFF,
            (distance_cm >> 8) & 0xFF,
            strength & 0xFF,
            (strength >> 8) & 0xFF,
            0x00,
            0x00,
        ]
    )
    return body + bytes([sum(body) & 0xFF])


def test_parses_single_frame():
    from benewake_tf03.comms import parse_frames

    buf = bytearray(_frame(1234, 350))
    assert parse_frames(buf) == [(1234, 350)]
    assert len(buf) == 0  # fully consumed


def test_little_endian_decoding():
    from benewake_tf03.comms import parse_frames

    # 0x0102 = 258 cm, strength 0x0203 = 515
    buf = bytearray(_frame(258, 515))
    assert parse_frames(buf) == [(258, 515)]


def test_resyncs_on_leading_garbage():
    from benewake_tf03.comms import parse_frames

    buf = bytearray(b"\x00\xff\x12" + _frame(500, 200))
    assert parse_frames(buf) == [(500, 200)]


def test_drops_bad_checksum_and_keeps_next():
    from benewake_tf03.comms import parse_frames

    bad = bytearray(_frame(100, 100))
    bad[-1] ^= 0xFF  # corrupt the checksum
    buf = bytearray(bytes(bad) + _frame(700, 300))
    assert parse_frames(buf) == [(700, 300)]


def test_keeps_trailing_partial_frame():
    from benewake_tf03.comms import parse_frames

    full = _frame(900, 400)
    buf = bytearray(full + full[:4])  # one whole frame + a partial
    assert parse_frames(buf) == [(900, 400)]
    assert bytes(buf) == full[:4]  # partial retained for next read


def test_multiple_frames_in_order():
    from benewake_tf03.comms import parse_frames

    buf = bytearray(_frame(10, 50) + _frame(20, 60) + _frame(30, 70))
    assert parse_frames(buf) == [(10, 50), (20, 60), (30, 70)]
