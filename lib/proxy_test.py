import os
import subprocess
import sys
import unittest
from unittest import TestCase, mock
from unittest.mock import Mock, call

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.data import Service
from lib.proxy import (
    get_internal_map,
    get_passthrough_map,
    get_terminate_map,
    reload_proxy,
    write_maps,
    write_nginx,
    write_proxy,
    write_terminate,
)


class TestProxy(TestCase):
    @mock.patch("lib.proxy.get_terminate_services")
    def test_get_internal_map(self, mock_get_terminate_services):
        # Mock the get_terminate_services function
        mock_get_terminate_services.return_value = [
            Service(svc="bla", domain="example.com", upstream=False, port=8080),
            Service(svc="dida", domain="example.org", upstream=True, port=8080),
        ]

        # Call the function under test
        internal_map = get_internal_map()

        # Assert the result
        expected_map = {
            "example.com": "terminate:8443",
            "example.org": "terminate:8443",
        }
        self.assertEqual(internal_map, expected_map)

    @mock.patch("lib.proxy.get_terminate_services")
    def test_get_terminate_map(self, mock_get_terminate_services):
        # Mock the get_terminate_services function
        mock_get_terminate_services.return_value = [
            Service(
                domain="example.com",
                project="my_project",
                svc="my_service",
                port=8080,
                upstream=True,
            ),
            Service(
                domain="example.org",
                project="my_project",
                svc="my_service",
                port=8080,
                upstream=False,
            ),
        ]

        # Call the function under test
        terminate_map = get_terminate_map()

        # Assert the result
        expected_map = {
            "example.com": "my_project-my_service:8080",
            "example.org": "my_service:8080",
        }
        self.assertEqual(terminate_map, expected_map)

    @mock.patch("lib.proxy.get_services")
    def test_get_passthrough_map(self, mock_get_services):
        # Mock the get_services function
        mock_get_services.return_value = [
            Service(
                domain="example.com", svc="my_service", port=8080, passthrough=True
            ),
        ]

        # Call the function under test
        passthrough_map = get_passthrough_map()

        # Assert the result
        expected_map = {
            "example.com": "my_service:8080",
        }
        self.assertEqual(passthrough_map, expected_map)

    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch("jinja2.Template")
    @mock.patch("lib.proxy.get_internal_map")
    @mock.patch("lib.proxy.get_passthrough_map")
    @mock.patch("lib.proxy.get_terminate_map")
    def test_write_maps(
        self,
        mock_get_terminate_map: Mock,
        mock_get_passthrough_map: Mock,
        mock_get_internal_map: Mock,
        mock_template: Mock,
        mock_open: Mock,
    ):
        # Mock the get_internal_map function
        mock_get_internal_map.return_value = {
            "example.com": "terminate:8080",
            "example.org": "terminate:8080",
        }

        # Mock the get_passthrough_map function
        mock_get_passthrough_map.return_value = {
            "example.com": "my_service:8080",
            "example.org": "my_service:8080",
        }

        # Mock the get_terminate_map function
        mock_get_terminate_map.return_value = {
            "example.com": "my_project-my_service:8080",
            "example.org": "my_service:8080",
        }

        mock_template.return_value = {"render": Mock()}

        # Call the function under test
        write_maps()

        self.assertEqual(
            mock_open.call_args_list,
            [
                mock.call("proxy/tpl/map.conf.j2", encoding="utf-8"),
                mock.call("proxy/map/internal.conf", "w", encoding="utf-8"),
                mock.call("proxy/map/passthrough.conf", "w", encoding="utf-8"),
                mock.call("proxy/map/terminate.conf", "w", encoding="utf-8"),
            ],
        )

    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch("lib.proxy.get_project")
    def test_write_proxy(self, _: Mock, mock_open: Mock):

        # Call the function under test
        write_proxy()

        # Assert that 'open' is called twice with the correct arguments
        self.assertEqual(
            mock_open.call_args_list,
            [
                call("proxy/tpl/proxy.conf.j2", encoding="utf-8"),
                call("proxy/proxy.conf", "w", encoding="utf-8"),
            ],
        )

    @mock.patch("builtins.open", new_callable=mock.mock_open)
    @mock.patch("lib.proxy.get_domains")
    @mock.patch("lib.proxy.get_project")
    def test_write_terminate(self, _, mock_get_domains: Mock, mock_open: Mock):
        mock_get_domains.return_value = ["example.com", "example.org"]

        # Call the function under test
        write_terminate()

        # Assert that 'open' is called twice with the correct arguments
        self.assertEqual(
            mock_open.call_args_list,
            [
                call("proxy/tpl/terminate.conf.j2", encoding="utf-8"),
                call("proxy/terminate.conf", "w", encoding="utf-8"),
            ],
        )

    @mock.patch("lib.proxy.write_maps")
    @mock.patch("lib.proxy.write_proxy")
    @mock.patch("lib.proxy.write_terminate")
    def test_write_nginx(
        self, mock_write_terminate: Mock, mock_write_proxy: Mock, mock_write_maps: Mock
    ):
        # Call the function under test
        write_nginx()

        # Assert that the write_maps, write_proxy, and write_terminate functions are called
        mock_write_maps.assert_called_once()
        mock_write_proxy.assert_called_once()
        mock_write_terminate.assert_called_once()

    @mock.patch("subprocess.Popen")
    @mock.patch("lib.proxy.stream_output")
    def test_reload_proxy(self, mock_stream_output: Mock, mock_popen: Mock):
        # Mock the subprocess.Popen object
        mock_process = mock.Mock()
        mock_popen.return_value = mock_process

        # Call the function under test
        reload_proxy()

        # Assert that the subprocess.Popen was called twice
        mock_popen.assert_has_calls(
            [
                call(
                    ["docker", "compose", "exec", "proxy", "nginx", "-s", "reload"],
                    cwd="proxy",
                    stdout=subprocess.PIPE,
                ),
                call().wait(),
                call(
                    ["docker", "compose", "exec", "terminate", "nginx", "-s", "reload"],
                    cwd="proxy",
                    stdout=subprocess.PIPE,
                ),
                call().wait(),
            ]
        )

        # Assert that the stream_output function is called twice
        self.assertEqual(mock_stream_output.call_count, 2)

    @mock.patch("subprocess.Popen")
    @mock.patch("lib.proxy.stream_output")
    def test_reload_proxy_with_service(
        self, mock_stream_output: Mock, mock_popen: Mock
    ):
        # Mock the subprocess.Popen object
        mock_process = mock.Mock()
        mock_popen.return_value = mock_process

        # Call the function under test
        reload_proxy(service="terminate")

        # Assert that the subprocess.Popen was called with the correct arguments
        mock_popen.assert_called_once_with(
            ["docker", "compose", "exec", "terminate", "nginx", "-s", "reload"],
            cwd="proxy",
            stdout=subprocess.PIPE,
        )

        # Assert that the stream_output function is called
        mock_stream_output.assert_called_once_with(mock_process)


if __name__ == "__main__":
    unittest.main()
