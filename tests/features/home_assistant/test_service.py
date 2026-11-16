from unittest.mock import Mock

from petcam.features.home_assistant import service


def test_service_delegates_snapshot_and_publish_operations():
    config = {"MQTT_ENABLED": "true"}
    expected = {"hostname": "petcam"}
    client = Mock()
    with __import__("unittest").mock.patch.object(
        service.worker, "collect_snapshot", return_value=expected
    ) as collect, __import__("unittest").mock.patch.object(
        service.worker, "publish_once", return_value=None
    ) as publish:
        assert service.collect_snapshot(config) == expected
        service.publish(client, config)
    collect.assert_called_once_with(config, None)
    publish.assert_called_once_with(client, config)


def test_service_delegates_discovery_removal():
    with __import__("unittest").mock.patch.object(service.worker, "remove_discovery") as remove:
        service.remove_discovery({"MQTT_ENABLED": "true"})
    remove.assert_called_once_with({"MQTT_ENABLED": "true"})
