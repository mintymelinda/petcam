from pathlib import Path

from petcam.infrastructure.camera.discovery import usb_parent_for_video_node


def test_usb_parent_resolution_finds_physical_device(tmp_path):
    usb = tmp_path / "sys" / "devices" / "usb1" / "1-1"
    interface = usb / "1-1:1.0"
    video = tmp_path / "sys" / "class" / "video4linux" / "video0"
    interface.mkdir(parents=True)
    video.mkdir(parents=True)
    (usb / "idVendor").write_text("046d")
    (usb / "idProduct").write_text("085c")
    (video / "device").symlink_to(interface)
    assert usb_parent_for_video_node(video) == usb
