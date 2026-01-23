"""Django app configuration for the compliance module."""

from django.apps import AppConfig


class ComplianceConfig(AppConfig):
    """App configuration for the compliance module."""

    default_auto_field = 'django.db.models.BigAutoField'
    name = 'compliance'
    verbose_name = 'Compliance'

    def ready(self):
        """Initialize the compliance module when Django starts."""
        # Import signal handlers
        from compliance import signals  # noqa: F401
