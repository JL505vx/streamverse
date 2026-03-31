from django.test import SimpleTestCase

from config.env_utils import build_csrf_trusted_origins


class CsrfTrustedOriginsTests(SimpleTestCase):
    def test_builds_explicit_and_allowed_host_origins(self):
        origins = build_csrf_trusted_origins(
            ['192.168.0.144:8011', 'https://streamverse.example.com'],
            ['127.0.0.1', 'localhost'],
        )

        self.assertIn('http://192.168.0.144:8011', origins)
        self.assertIn('https://streamverse.example.com', origins)
        self.assertIn('http://127.0.0.1', origins)
        self.assertIn('https://localhost', origins)

    def test_supports_wildcard_hosts(self):
        origins = build_csrf_trusted_origins([], ['.streamverse.test'])

        self.assertIn('http://*.streamverse.test', origins)
        self.assertIn('https://*.streamverse.test', origins)
