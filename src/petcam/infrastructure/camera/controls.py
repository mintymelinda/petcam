"""V4L2 camera-control discovery, validation, and command execution."""

import re


CONTROL_LINE = re.compile(
    r"^\s*(?P<name>[a-zA-Z0-9_]+)\s+0x[0-9a-fA-F]+\s+"
    r"\((?P<type>[^)]+)\)\s*:\s*(?P<metadata>.*)$"
)
MENU_LINE = re.compile(r"^\s*(?P<value>-?\d+)\s*:\s*(?P<label>.+?)\s*$")


def parse_controls(output):
    """Parse v4l2-ctl control metadata without assuming a particular camera model."""
    controls = []
    current = None
    for raw_line in output.splitlines():
        match = CONTROL_LINE.match(raw_line)
        if match:
            metadata = match.group("metadata")
            values = {}
            for key in ("min", "max", "step", "default", "value"):
                value_match = re.search(rf"(?:^|\s){key}=(-?\d+)", metadata)
                if value_match:
                    values[key] = int(value_match.group(1))
            flags_match = re.search(r"(?:^|\s)flags=(.+)$", metadata)
            flags = [flag.strip() for flag in flags_match.group(1).split(",")] if flags_match else []
            control_type = match.group("type").lower()
            supported = control_type in ("bool", "int", "menu", "intmenu")
            current = {
                "name": match.group("name"),
                "type": control_type,
                "min": values.get("min"),
                "max": values.get("max"),
                "step": max(1, values.get("step", 1)),
                "default": values.get("default"),
                "value": values.get("value"),
                "flags": flags,
                "menu": [],
                "supported": supported,
                "writable": supported and not any(
                    flag in flags for flag in ("inactive", "read-only", "grabbed")
                ),
            }
            controls.append(current)
            continue
        if current:
            menu_match = MENU_LINE.match(raw_line)
            if menu_match:
                current["menu"].append({
                    "value": int(menu_match.group("value")),
                    "label": menu_match.group("label"),
                })
    for control in controls:
        control_type = control["type"]
        menu_values = {option["value"] for option in control["menu"]}

        def is_valid(value):
            if value is None:
                return False
            if control_type == "bool":
                return value in (0, 1)
            if control_type in ("menu", "intmenu"):
                return value in menu_values
            if control_type == "int":
                minimum = control["min"]
                maximum = control["max"]
                step = control["step"]
                return (
                    (minimum is None or value >= minimum)
                    and (maximum is None or value <= maximum)
                    and (minimum is None or (value - minimum) % step == 0)
                )
            return True

        if not is_valid(control["value"]):
            control["value"] = None
        if not is_valid(control["default"]):
            control["default"] = None
    return controls


def read_controls(camera, run):
    """Read controls only from a discovered camera device."""
    if not camera:
        return {
            "supported": False,
            "message": "Camera controls are available for the active USB camera. Select and apply a USB camera first.",
            "controls": [],
        }
    device = camera.get("device", "")
    if not device.startswith(("/dev/video", "/dev/v4l/by-id/", "/dev/v4l/by-path/")):
        raise ValueError("The active camera has an invalid V4L2 device path.")
    result = run(
        ["/usr/bin/v4l2-ctl", "--device", device, "--list-ctrls-menus"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Unable to read camera controls")
    return {
        "supported": True,
        "device": device,
        "label": camera.get("label", "Active USB camera"),
        "controls": parse_controls(result.stdout),
    }


def set_control(data, camera, read_current, run):
    """Validate a requested value against live camera metadata before applying it."""
    name = data.get("name")
    value = data.get("value")
    if not isinstance(name, str) or not re.fullmatch(r"[a-zA-Z0-9_]+", name):
        raise ValueError("Invalid camera control name.")
    if not camera:
        raise ValueError("There is no active USB camera.")
    current = read_current(camera)
    control = next((item for item in current["controls"] if item["name"] == name), None)
    if not control:
        raise ValueError("That control is not supported by the active camera.")
    if not control["writable"]:
        raise ValueError("That camera control is currently inactive or read-only.")
    if control["type"] == "bool":
        if isinstance(value, bool):
            value = int(value)
        if not isinstance(value, int) or value not in (0, 1):
            raise ValueError("Boolean camera controls must be true or false.")
    else:
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Camera control values must be integers.")
        if control["min"] is not None and value < control["min"]:
            raise ValueError("Camera control value is below the supported minimum.")
        if control["max"] is not None and value > control["max"]:
            raise ValueError("Camera control value is above the supported maximum.")
        if control["min"] is not None and (value - control["min"]) % control["step"]:
            raise ValueError("Camera control value does not match the supported step.")
        if control["type"] in ("menu", "intmenu") and value not in {
            option["value"] for option in control["menu"]
        }:
            raise ValueError("Camera control value is not an advertised menu option.")
    result = run(
        ["/usr/bin/v4l2-ctl", "--device", camera["device"], f"--set-ctrl={name}={value}"],
        capture_output=True, text=True, timeout=10, check=False,
    )
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or "Unable to update camera control")
    return read_current(camera)
