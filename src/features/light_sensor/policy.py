"""Light-sensor configuration and hysteresis policy, independent of I/O."""

DEFAULTS = {
    "ENABLED": "false",
    "I2C_BUS": "1",
    "I2C_ADDRESS": "0x29",
    "BRIGHT_THRESHOLD_LUX": "100",
    "DARK_THRESHOLD_LUX": "30",
    "POLL_SECONDS": "10",
}


class SensorError(RuntimeError):
    """Invalid or unavailable light-sensor configuration."""


def validate(values):
    if str(values["ENABLED"]).lower() not in {"true", "false"}:
        raise SensorError("ENABLED must be true or false.")
    try:
        bus = int(str(values["I2C_BUS"]))
        address = int(str(values["I2C_ADDRESS"]), 0)
        bright = float(str(values["BRIGHT_THRESHOLD_LUX"]))
        dark = float(str(values["DARK_THRESHOLD_LUX"]))
        poll = int(str(values["POLL_SECONDS"]))
    except ValueError as error:
        raise SensorError("Light sensor settings contain an invalid number.") from error
    if not 0 <= bus <= 255 or not 0x03 <= address <= 0x77:
        raise SensorError("I2C bus or 7-bit device address is out of range.")
    if not 0 <= dark < bright <= 100000:
        raise SensorError("Thresholds must satisfy 0 <= dark < bright <= 100000 lux.")
    if not 2 <= poll <= 300:
        raise SensorError("POLL_SECONDS must be between 2 and 300.")
    return {
        "ENABLED": str(values["ENABLED"]).lower() == "true",
        "I2C_BUS": bus,
        "I2C_ADDRESS": address,
        "BRIGHT_THRESHOLD_LUX": bright,
        "DARK_THRESHOLD_LUX": dark,
        "POLL_SECONDS": poll,
    }


def classify(lux, previous, bright, dark):
    if lux >= bright:
        return "bright"
    if lux <= dark:
        return "dark"
    return previous if previous in {"bright", "dark"} else "unknown"
