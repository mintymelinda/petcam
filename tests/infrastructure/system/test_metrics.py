from petcam.infrastructure.system.metrics import installed_version


def test_installed_version_searches_parent_release_directories(tmp_path):
    release = tmp_path / "current"
    package_file = release / "lib" / "petcam" / "api" / "application.py"
    package_file.parent.mkdir(parents=True)
    package_file.write_text("# package entry point\n", encoding="utf-8")
    (release / "VERSION").write_text("0.8.1\n", encoding="utf-8")

    assert installed_version(package_file) == "0.8.1"


def test_installed_version_returns_none_without_a_version_file(tmp_path):
    package_file = tmp_path / "lib" / "petcam" / "api" / "application.py"
    package_file.parent.mkdir(parents=True)
    package_file.write_text("# package entry point\n", encoding="utf-8")

    assert installed_version(package_file) is None
