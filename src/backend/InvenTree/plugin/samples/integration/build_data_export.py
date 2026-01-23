"""Build Data Export Plugin for InvenTree.

This plugin provides functionality to export build order and production data
to external systems in CSV/JSON format, with support for webhooks and
real-time data synchronization.
"""

import csv
import io
import json
import logging
from datetime import datetime

import requests
from django.http import HttpResponse, JsonResponse
from django.urls import path
from django.utils.translation import gettext_lazy as _

from build.models import Build
from build.status_codes import BuildStatus
from plugin import InvenTreePlugin
from plugin.mixins import APICallMixin, SettingsMixin, UrlsMixin

logger = logging.getLogger('inventree')


class BuildDataExportPlugin(APICallMixin, SettingsMixin, UrlsMixin, InvenTreePlugin):
    """Plugin for exporting build order data to external systems.

    Features:
    - Export build orders to CSV or JSON format
    - Filter exports by status, date range, and part
    - Webhook support for real-time notifications on build status changes
    - Configurable export fields and formats
    """

    NAME = 'BuildDataExportPlugin'
    SLUG = 'build-data-export'
    TITLE = _('Build Data Export')
    DESCRIPTION = _('Export build order and production data to external systems')
    VERSION = '1.0.0'
    AUTHOR = 'InvenTree Contributors'

    SETTINGS = {
        'WEBHOOK_URL': {
            'name': _('Webhook URL'),
            'description': _('URL to send webhook notifications when build orders change status'),
            'default': '',
        },
        'WEBHOOK_ENABLED': {
            'name': _('Enable Webhooks'),
            'description': _('Enable webhook notifications for build order status changes'),
            'default': False,
            'validator': bool,
        },
        'EXPORT_FORMAT': {
            'name': _('Default Export Format'),
            'description': _('Default format for data exports'),
            'choices': [('csv', 'CSV'), ('json', 'JSON')],
            'default': 'json',
        },
        'INCLUDE_COMPLETED': {
            'name': _('Include Completed Builds'),
            'description': _('Include completed build orders in exports by default'),
            'default': True,
            'validator': bool,
        },
        'WEBHOOK_SECRET': {
            'name': _('Webhook Secret'),
            'description': _('Secret key for webhook authentication (sent in X-Webhook-Secret header)'),
            'default': '',
            'protected': True,
        },
    }

    def setup_urls(self):
        """Define URL patterns for the plugin."""
        return [
            path('export/', self.export_builds, name='export-builds'),
            path('export/csv/', self.export_builds_csv, name='export-builds-csv'),
            path('export/json/', self.export_builds_json, name='export-builds-json'),
            path('webhook/test/', self.test_webhook, name='test-webhook'),
        ]

    def get_build_queryset(self, request):
        """Get filtered build queryset based on request parameters."""
        queryset = Build.objects.all()

        status = request.GET.get('status')
        if status:
            try:
                queryset = queryset.filter(status=int(status))
            except ValueError:
                pass

        part_id = request.GET.get('part')
        if part_id:
            try:
                queryset = queryset.filter(part_id=int(part_id))
            except ValueError:
                pass

        start_date = request.GET.get('start_date')
        if start_date:
            try:
                start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
                queryset = queryset.filter(creation_date__gte=start_dt)
            except ValueError:
                pass

        end_date = request.GET.get('end_date')
        if end_date:
            try:
                end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
                queryset = queryset.filter(creation_date__lte=end_dt)
            except ValueError:
                pass

        if not self.get_setting('INCLUDE_COMPLETED'):
            queryset = queryset.exclude(status=BuildStatus.COMPLETE.value)

        return queryset.select_related('part', 'responsible', 'issued_by')

    def serialize_build(self, build):
        """Serialize a build order to a dictionary."""
        return {
            'id': build.pk,
            'reference': build.reference,
            'title': build.title,
            'part_id': build.part.pk if build.part else None,
            'part_name': build.part.name if build.part else None,
            'part_ipn': build.part.IPN if build.part else None,
            'quantity': float(build.quantity),
            'completed': float(build.completed),
            'status': build.status,
            'status_text': build.get_status_display(),
            'creation_date': build.creation_date.isoformat() if build.creation_date else None,
            'start_date': build.start_date.isoformat() if build.start_date else None,
            'target_date': build.target_date.isoformat() if build.target_date else None,
            'completion_date': build.completion_date.isoformat() if build.completion_date else None,
            'issued_by': build.issued_by.username if build.issued_by else None,
            'responsible': str(build.responsible) if build.responsible else None,
            'link': build.link,
            'notes': build.notes,
            'priority': build.priority,
            'batch': build.batch,
        }

    def export_builds(self, request):
        """Export builds in the configured default format."""
        export_format = self.get_setting('EXPORT_FORMAT')

        if export_format == 'csv':
            return self.export_builds_csv(request)
        else:
            return self.export_builds_json(request)

    def export_builds_json(self, request):
        """Export builds as JSON."""
        queryset = self.get_build_queryset(request)
        builds = [self.serialize_build(build) for build in queryset]

        response_data = {
            'count': len(builds),
            'exported_at': datetime.now().isoformat(),
            'builds': builds,
        }

        return JsonResponse(response_data, safe=False)

    def export_builds_csv(self, request):
        """Export builds as CSV."""
        queryset = self.get_build_queryset(request)

        output = io.StringIO()
        writer = csv.writer(output)

        headers = [
            'ID', 'Reference', 'Title', 'Part ID', 'Part Name', 'Part IPN',
            'Quantity', 'Completed', 'Status', 'Status Text',
            'Creation Date', 'Start Date', 'Target Date', 'Completion Date',
            'Issued By', 'Responsible', 'Priority', 'Batch', 'Link', 'Notes'
        ]
        writer.writerow(headers)

        for build in queryset:
            row = [
                build.pk,
                build.reference,
                build.title,
                build.part.pk if build.part else '',
                build.part.name if build.part else '',
                build.part.IPN if build.part else '',
                float(build.quantity),
                float(build.completed),
                build.status,
                build.get_status_display(),
                build.creation_date.isoformat() if build.creation_date else '',
                build.start_date.isoformat() if build.start_date else '',
                build.target_date.isoformat() if build.target_date else '',
                build.completion_date.isoformat() if build.completion_date else '',
                build.issued_by.username if build.issued_by else '',
                str(build.responsible) if build.responsible else '',
                build.priority,
                build.batch,
                build.link,
                build.notes or '',
            ]
            writer.writerow(row)

        output.seek(0)
        response = HttpResponse(output.getvalue(), content_type='text/csv')
        response['Content-Disposition'] = f'attachment; filename="builds_export_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv"'

        return response

    def send_webhook(self, build, event_type):
        """Send a webhook notification for a build order event.

        Args:
            build: The Build instance that triggered the event
            event_type: Type of event (e.g., 'status_changed', 'created', 'completed')
        """
        webhook_url = self.get_setting('WEBHOOK_URL')
        webhook_enabled = self.get_setting('WEBHOOK_ENABLED')

        if not webhook_enabled or not webhook_url:
            return False

        payload = {
            'event_type': event_type,
            'timestamp': datetime.now().isoformat(),
            'build': self.serialize_build(build),
        }

        headers = {
            'Content-Type': 'application/json',
            'X-InvenTree-Event': event_type,
        }

        webhook_secret = self.get_setting('WEBHOOK_SECRET')
        if webhook_secret:
            headers['X-Webhook-Secret'] = webhook_secret

        try:
            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            logger.info(f'Webhook sent successfully for build {build.reference}: {event_type}')
            return True
        except requests.RequestException as e:
            logger.error(f'Failed to send webhook for build {build.reference}: {e}')
            return False

    def test_webhook(self, request):
        """Test the webhook configuration by sending a test payload."""
        webhook_url = self.get_setting('WEBHOOK_URL')
        webhook_enabled = self.get_setting('WEBHOOK_ENABLED')

        if not webhook_url:
            return JsonResponse({
                'success': False,
                'error': 'Webhook URL is not configured'
            }, status=400)

        if not webhook_enabled:
            return JsonResponse({
                'success': False,
                'error': 'Webhooks are not enabled'
            }, status=400)

        test_payload = {
            'event_type': 'test',
            'timestamp': datetime.now().isoformat(),
            'message': 'This is a test webhook from InvenTree Build Data Export Plugin',
            'build': {
                'id': 0,
                'reference': 'TEST-0000',
                'title': 'Test Build Order',
                'status': 'test',
            }
        }

        headers = {
            'Content-Type': 'application/json',
            'X-InvenTree-Event': 'test',
        }

        webhook_secret = self.get_setting('WEBHOOK_SECRET')
        if webhook_secret:
            headers['X-Webhook-Secret'] = webhook_secret

        try:
            response = requests.post(
                webhook_url,
                json=test_payload,
                headers=headers,
                timeout=10
            )
            response.raise_for_status()
            return JsonResponse({
                'success': True,
                'message': 'Test webhook sent successfully',
                'status_code': response.status_code
            })
        except requests.RequestException as e:
            return JsonResponse({
                'success': False,
                'error': str(e)
            }, status=500)
