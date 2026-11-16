import unittest
from unittest import mock

from petcam import process_control as MODULE


class ProcessControlTests(unittest.TestCase):
    def test_systemctl_command_uses_absolute_binary_without_shell(self):
        self.assertEqual(
            MODULE.systemctl_command("show", "petcam-web.service"),
            ["/usr/bin/systemctl", "show", "petcam-web.service"],
        )

    def test_privileged_systemctl_command_uses_noninteractive_sudo(self):
        self.assertEqual(
            MODULE.systemctl_command("restart", "petcam-stream.service", sudo=True),
            ["sudo", "-n", "/usr/bin/systemctl", "restart", "petcam-stream.service"],
        )

    def test_run_command_forwards_argument_vector_and_options_to_runner(self):
        runner = mock.Mock(return_value="result")
        result = MODULE.run_command(["/usr/bin/example", "--check"], runner=runner, check=False)
        self.assertEqual(result, "result")
        runner.assert_called_once_with(["/usr/bin/example", "--check"], check=False)

    def test_run_command_rejects_invalid_argument_vectors(self):
        for command in ([], [""], "not-a-command"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                MODULE.run_command(command)

    def test_run_systemctl_forwards_command_and_options_to_runner(self):
        runner = mock.Mock(return_value="result")
        result = MODULE.run_systemctl(
            "stop", "petcam-web.service", runner=runner, check=False,
        )
        self.assertEqual(result, "result")
        runner.assert_called_once_with(
            ["/usr/bin/systemctl", "stop", "petcam-web.service"], check=False,
        )

    def test_stream_instance_unit_accepts_safe_profile_ids(self):
        self.assertEqual(
            MODULE.stream_instance_unit("front-door-2"),
            "petcam-stream@front-door-2.service",
        )

    def test_stream_instance_unit_rejects_unsafe_profile_ids(self):
        for profile_id in ("", "../web", "front/door", "UPPER", "bad name"):
            with self.subTest(profile_id=profile_id), self.assertRaises(ValueError):
                MODULE.stream_instance_unit(profile_id)

    def test_systemctl_command_rejects_empty_arguments(self):
        for arguments in ((), ("",)):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                MODULE.systemctl_command(*arguments)


if __name__ == "__main__":
    unittest.main()
