from petcam.infrastructure.camera.csi import extract_jpeg_frames


def test_jpeg_frame_extractor_handles_multiple_frames_and_partial_tail():
    first = b"\xff\xd8first\xff\xd9"
    second = b"\xff\xd8second\xff\xd9"
    buffer = bytearray(b"noise" + first + second + b"\xff\xd8partial")
    frames = extract_jpeg_frames(buffer)
    assert frames == [first, second]
    assert buffer == b"\xff\xd8partial"
