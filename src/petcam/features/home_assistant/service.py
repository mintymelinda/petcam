"""Application-facing Home Assistant publishing service."""

from . import worker


def collect_snapshot(config, health=None):
    """Build the public device snapshot consumed by Home Assistant entities."""
    return worker.collect_snapshot(config, health)


def publish(client, config):
    """Publish retained discovery and current state through the MQTT client."""
    return worker.publish_once(client, config)


def remove_discovery(config):
    """Remove the Home Assistant discovery entities for this device."""
    return worker.remove_discovery(config)
