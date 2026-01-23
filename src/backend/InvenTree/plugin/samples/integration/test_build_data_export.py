"""Tests for the Build Data Export Plugin."""

from django.test import TestCase

from plugin.samples.integration.build_data_export import BuildDataExportPlugin


class BuildDataExportPluginTest(TestCase):
    """Tests for the BuildDataExportPlugin class structure."""

    def test_plugin_attributes(self):
        """Test that plugin has required attributes."""
        plugin = BuildDataExportPlugin()

        self.assertEqual(plugin.NAME, 'BuildDataExportPlugin')
        self.assertEqual(plugin.SLUG, 'build-data-export')
        self.assertEqual(plugin.VERSION, '1.0.0')

    def test_plugin_settings_defined(self):
        """Test that plugin settings are properly defined."""
        plugin = BuildDataExportPlugin()

        self.assertIn('WEBHOOK_URL', plugin.SETTINGS)
        self.assertIn('WEBHOOK_ENABLED', plugin.SETTINGS)
        self.assertIn('EXPORT_FORMAT', plugin.SETTINGS)
        self.assertIn('INCLUDE_COMPLETED', plugin.SETTINGS)
        self.assertIn('WEBHOOK_SECRET', plugin.SETTINGS)

        self.assertEqual(plugin.SETTINGS['EXPORT_FORMAT']['default'], 'json')
        self.assertEqual(plugin.SETTINGS['WEBHOOK_ENABLED']['default'], False)
        self.assertEqual(plugin.SETTINGS['INCLUDE_COMPLETED']['default'], True)

    def test_plugin_urls_defined(self):
        """Test that plugin URLs are properly defined."""
        plugin = BuildDataExportPlugin()

        urls = plugin.setup_urls()
        self.assertIsInstance(urls, list)
        self.assertEqual(len(urls), 4)

        url_names = [url.name for url in urls]
        self.assertIn('export-builds', url_names)
        self.assertIn('export-builds-csv', url_names)
        self.assertIn('export-builds-json', url_names)
        self.assertIn('test-webhook', url_names)

    def test_serialize_build_method(self):
        """Test that serialize_build method exists and has correct structure."""
        plugin = BuildDataExportPlugin()

        self.assertTrue(hasattr(plugin, 'serialize_build'))
        self.assertTrue(callable(plugin.serialize_build))

    def test_send_webhook_method(self):
        """Test that send_webhook method exists."""
        plugin = BuildDataExportPlugin()

        self.assertTrue(hasattr(plugin, 'send_webhook'))
        self.assertTrue(callable(plugin.send_webhook))
