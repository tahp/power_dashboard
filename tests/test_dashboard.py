import os
import unittest
from unittest.mock import patch

os.environ['DASHBOARD_SKIP_CAMERA_INIT'] = '1'
os.environ['DASHBOARD_DISABLE_POLLING'] = '1'

import dashboard_host as dashboard


class DashboardSmokeTests(unittest.TestCase):
    def setUp(self):
        self.client = dashboard.app.test_client()
        self.power_headers = {
            'Content-Type': 'application/json',
            'X-Power-Token': dashboard.POWER_ACTION_TOKEN,
        }

    def test_dashboard_uses_only_local_browser_assets(self):
        response = self.client.get('/')
        html = response.get_data(as_text=True)

        self.assertEqual(response.status_code, 200)
        self.assertIn('/static/vendor/plotly.min.js', html)
        self.assertNotIn('cdn.plot.ly', html)
        self.assertNotIn('fonts.googleapis.com', html)

    def test_core_api_endpoints(self):
        data_response = self.client.get('/api_data')
        graph_response = self.client.get('/api_graph')

        self.assertEqual(data_response.status_code, 200)
        self.assertIn(data_response.json['mode'], {'ACTIVE', 'MOCKED'})
        self.assertEqual(set(graph_response.json), {'time', 'voltage', 'amps'})

    def test_security_headers_are_present(self):
        response = self.client.get('/api_data')

        self.assertEqual(response.headers['X-Content-Type-Options'], 'nosniff')
        self.assertEqual(response.headers['X-Frame-Options'], 'DENY')
        self.assertIn("frame-ancestors 'none'", response.headers['Content-Security-Policy'])

    def test_power_action_rejects_remote_clients(self):
        response = self.client.post(
            '/api/power',
            json={'action': 'restart'},
            headers=self.power_headers,
            environ_base={'REMOTE_ADDR': '192.168.1.50'},
        )

        self.assertEqual(response.status_code, 403)

    def test_power_action_rejects_missing_token(self):
        response = self.client.post('/api/power', json={'action': 'restart'})

        self.assertEqual(response.status_code, 403)

    @patch('dashboard_host.subprocess.run')
    def test_power_action_accepts_local_authenticated_request(self, run):
        run.return_value.returncode = 0
        run.return_value.stderr = ''
        run.return_value.stdout = ''

        response = self.client.post(
            '/api/power', json={'action': 'restart'}, headers=self.power_headers
        )

        self.assertEqual(response.status_code, 200)
        run.assert_called_once_with(
            ['/usr/bin/sudo', '-n', '/usr/bin/systemctl', 'reboot'],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )

    def test_vendored_plotly_is_served(self):
        response = self.client.get('/static/vendor/plotly.min.js')

        self.assertEqual(response.status_code, 200)
        self.assertGreater(len(response.data), 1_000_000)
        response.close()


if __name__ == '__main__':
    unittest.main()
