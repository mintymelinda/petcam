from petcam.infrastructure.persistence.factory_reset import write_file


def test_write_file_creates_parent_and_writes_contents(tmp_path):
    target = tmp_path / "state" / "nested" / "settings.conf"
    write_file(target, "enabled=true\n")
    assert target.read_text() == "enabled=true\n"
