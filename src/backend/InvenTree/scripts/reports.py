"""Report generation utilities for BEP MES requirements.

This module provides parameterized report generation capabilities
for financial reporting, government compliance, and operational metrics.

Features:
- Parameterized report templates
- Multiple output formats (PDF, CSV, Excel, JSON)
- Scheduled report generation
- Report distribution via email
"""

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.db.models import QuerySet
from django.template import Context, Template

import structlog

logger = structlog.get_logger('inventree')


@dataclass
class ReportParameter:
    """Definition of a report parameter."""

    name: str
    param_type: str
    label: str
    required: bool = True
    default: Any = None
    choices: list[Any] = field(default_factory=list)
    help_text: str = ''


@dataclass
class ReportDefinition:
    """Definition of a report template."""

    report_id: str
    name: str
    description: str
    category: str
    parameters: list[ReportParameter] = field(default_factory=list)
    query_template: str = ''
    output_formats: list[str] = field(default_factory=lambda: ['csv', 'json'])
    schedule: str = ''


class ReportGenerator:
    """Generate reports from templates and data.

    This class provides the core report generation functionality,
    supporting multiple output formats and parameterized queries.
    """

    def __init__(self):
        """Initialize the report generator."""
        self.reports: dict[str, ReportDefinition] = {}
        self._register_default_reports()

    def _register_default_reports(self):
        """Register default report definitions."""
        self.register_report(
            ReportDefinition(
                report_id='inventory_summary',
                name='Inventory Summary Report',
                description='Summary of current inventory levels by category',
                category='Inventory',
                parameters=[
                    ReportParameter(
                        name='category_id',
                        param_type='integer',
                        label='Category',
                        required=False,
                        help_text='Filter by specific category',
                    ),
                    ReportParameter(
                        name='include_zero_stock',
                        param_type='boolean',
                        label='Include Zero Stock',
                        required=False,
                        default=False,
                        help_text='Include items with zero stock',
                    ),
                ],
                output_formats=['csv', 'json', 'pdf'],
            )
        )

        self.register_report(
            ReportDefinition(
                report_id='build_order_status',
                name='Build Order Status Report',
                description='Status of all build orders within date range',
                category='Manufacturing',
                parameters=[
                    ReportParameter(
                        name='start_date',
                        param_type='date',
                        label='Start Date',
                        required=True,
                        help_text='Start of date range',
                    ),
                    ReportParameter(
                        name='end_date',
                        param_type='date',
                        label='End Date',
                        required=True,
                        help_text='End of date range',
                    ),
                    ReportParameter(
                        name='status',
                        param_type='choice',
                        label='Status Filter',
                        required=False,
                        choices=['pending', 'production', 'complete', 'cancelled'],
                        help_text='Filter by build order status',
                    ),
                ],
                output_formats=['csv', 'json', 'pdf'],
            )
        )

        self.register_report(
            ReportDefinition(
                report_id='compliance_audit',
                name='Compliance Audit Report',
                description='Audit trail report for compliance review',
                category='Compliance',
                parameters=[
                    ReportParameter(
                        name='start_date',
                        param_type='date',
                        label='Start Date',
                        required=True,
                        help_text='Start of audit period',
                    ),
                    ReportParameter(
                        name='end_date',
                        param_type='date',
                        label='End Date',
                        required=True,
                        help_text='End of audit period',
                    ),
                    ReportParameter(
                        name='event_type',
                        param_type='string',
                        label='Event Type',
                        required=False,
                        help_text='Filter by specific event type',
                    ),
                    ReportParameter(
                        name='user_id',
                        param_type='integer',
                        label='User',
                        required=False,
                        help_text='Filter by specific user',
                    ),
                ],
                output_formats=['csv', 'json', 'pdf'],
            )
        )

        self.register_report(
            ReportDefinition(
                report_id='quality_metrics',
                name='Quality Metrics Report',
                description='Quality inspection and test results summary',
                category='Quality',
                parameters=[
                    ReportParameter(
                        name='start_date',
                        param_type='date',
                        label='Start Date',
                        required=True,
                        help_text='Start of reporting period',
                    ),
                    ReportParameter(
                        name='end_date',
                        param_type='date',
                        label='End Date',
                        required=True,
                        help_text='End of reporting period',
                    ),
                    ReportParameter(
                        name='part_id',
                        param_type='integer',
                        label='Part',
                        required=False,
                        help_text='Filter by specific part',
                    ),
                ],
                output_formats=['csv', 'json', 'pdf'],
            )
        )

    def register_report(self, report_def: ReportDefinition) -> None:
        """Register a report definition.

        Args:
            report_def: The report definition to register
        """
        self.reports[report_def.report_id] = report_def
        logger.info('report_registered', report_id=report_def.report_id)

    def get_report(self, report_id: str) -> ReportDefinition | None:
        """Get a report definition by ID.

        Args:
            report_id: The report identifier

        Returns:
            ReportDefinition or None if not found
        """
        return self.reports.get(report_id)

    def list_reports(self, category: str | None = None) -> list[ReportDefinition]:
        """List available reports.

        Args:
            category: Optional category filter

        Returns:
            list: List of report definitions
        """
        reports = list(self.reports.values())
        if category:
            reports = [r for r in reports if r.category == category]
        return reports

    def validate_parameters(
        self, report_id: str, params: dict[str, Any]
    ) -> tuple[bool, list[str]]:
        """Validate report parameters.

        Args:
            report_id: The report identifier
            params: Dictionary of parameter values

        Returns:
            tuple: (is_valid, list of error messages)
        """
        report = self.get_report(report_id)
        if not report:
            return False, [f'Report {report_id} not found']

        errors = []

        for param_def in report.parameters:
            value = params.get(param_def.name)

            if param_def.required and value is None:
                errors.append(f'Required parameter {param_def.name} is missing')
                continue

            if value is not None:
                if param_def.param_type == 'integer':
                    try:
                        int(value)
                    except (ValueError, TypeError):
                        errors.append(f'Parameter {param_def.name} must be an integer')

                elif param_def.param_type == 'date':
                    if not isinstance(value, (datetime, str)):
                        errors.append(f'Parameter {param_def.name} must be a date')

                elif param_def.param_type == 'choice':
                    if value not in param_def.choices:
                        errors.append(
                            f'Parameter {param_def.name} must be one of: '
                            f'{", ".join(str(c) for c in param_def.choices)}'
                        )

        return len(errors) == 0, errors

    def generate_report(
        self,
        report_id: str,
        params: dict[str, Any],
        data: QuerySet | list[dict],
        output_format: str = 'json',
    ) -> tuple[str, bytes]:
        """Generate a report.

        Args:
            report_id: The report identifier
            params: Dictionary of parameter values
            data: QuerySet or list of dictionaries with report data
            output_format: Output format (csv, json, pdf)

        Returns:
            tuple: (content_type, report_bytes)

        Raises:
            ValueError: If report not found or invalid parameters
        """
        report = self.get_report(report_id)
        if not report:
            raise ValueError(f'Report {report_id} not found')

        is_valid, errors = self.validate_parameters(report_id, params)
        if not is_valid:
            raise ValueError(f'Invalid parameters: {"; ".join(errors)}')

        if output_format not in report.output_formats:
            raise ValueError(
                f'Output format {output_format} not supported for this report'
            )

        if isinstance(data, QuerySet):
            data = list(data.values())

        if output_format == 'csv':
            return self._generate_csv(report, data)
        elif output_format == 'json':
            return self._generate_json(report, data, params)
        else:
            raise ValueError(f'Unsupported output format: {output_format}')

    def _generate_csv(
        self, report: ReportDefinition, data: list[dict]
    ) -> tuple[str, bytes]:
        """Generate CSV output.

        Args:
            report: The report definition
            data: List of data dictionaries

        Returns:
            tuple: (content_type, csv_bytes)
        """
        if not data:
            return 'text/csv', b''

        output = io.StringIO()
        fieldnames = list(data[0].keys())

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

        return 'text/csv', output.getvalue().encode('utf-8')

    def _generate_json(
        self, report: ReportDefinition, data: list[dict], params: dict[str, Any]
    ) -> tuple[str, bytes]:
        """Generate JSON output.

        Args:
            report: The report definition
            data: List of data dictionaries
            params: Report parameters

        Returns:
            tuple: (content_type, json_bytes)
        """
        output = {
            'report_id': report.report_id,
            'report_name': report.name,
            'generated_at': datetime.now().isoformat(),
            'parameters': params,
            'record_count': len(data),
            'data': data,
        }

        json_str = json.dumps(output, indent=2, default=str)
        return 'application/json', json_str.encode('utf-8')


class ScheduledReportManager:
    """Manage scheduled report generation and distribution.

    This class handles scheduling reports to run at specified intervals
    and distributing the results via email or other channels.
    """

    def __init__(self, report_generator: ReportGenerator):
        """Initialize the scheduled report manager.

        Args:
            report_generator: The report generator instance to use
        """
        self.generator = report_generator
        self.schedules: list[dict] = []

    def add_schedule(
        self,
        report_id: str,
        params: dict[str, Any],
        schedule: str,
        recipients: list[str],
        output_format: str = 'csv',
    ) -> dict:
        """Add a scheduled report.

        Args:
            report_id: The report identifier
            params: Report parameters
            schedule: Cron-style schedule string
            recipients: List of email addresses
            output_format: Output format for the report

        Returns:
            dict: The schedule configuration
        """
        schedule_config = {
            'id': len(self.schedules) + 1,
            'report_id': report_id,
            'params': params,
            'schedule': schedule,
            'recipients': recipients,
            'output_format': output_format,
            'enabled': True,
            'last_run': None,
            'next_run': None,
        }

        self.schedules.append(schedule_config)
        logger.info(
            'report_scheduled',
            report_id=report_id,
            schedule=schedule,
            recipients=recipients,
        )

        return schedule_config

    def remove_schedule(self, schedule_id: int) -> bool:
        """Remove a scheduled report.

        Args:
            schedule_id: The schedule identifier

        Returns:
            bool: True if removed, False if not found
        """
        for i, schedule in enumerate(self.schedules):
            if schedule['id'] == schedule_id:
                self.schedules.pop(i)
                return True
        return False

    def list_schedules(self, report_id: str | None = None) -> list[dict]:
        """List scheduled reports.

        Args:
            report_id: Optional filter by report ID

        Returns:
            list: List of schedule configurations
        """
        if report_id:
            return [s for s in self.schedules if s['report_id'] == report_id]
        return self.schedules


class ReportTemplateEngine:
    """Template engine for custom report formatting.

    This class provides Django template-based report formatting
    for creating custom report layouts.
    """

    def __init__(self):
        """Initialize the template engine."""
        self.templates: dict[str, str] = {}

    def register_template(self, template_id: str, template_string: str) -> None:
        """Register a report template.

        Args:
            template_id: Unique identifier for the template
            template_string: Django template string
        """
        self.templates[template_id] = template_string

    def render(self, template_id: str, context: dict[str, Any]) -> str:
        """Render a report using a template.

        Args:
            template_id: The template identifier
            context: Context dictionary for template rendering

        Returns:
            str: Rendered report content

        Raises:
            ValueError: If template not found
        """
        template_string = self.templates.get(template_id)
        if not template_string:
            raise ValueError(f'Template {template_id} not found')

        template = Template(template_string)
        return template.render(Context(context))

    def render_string(self, template_string: str, context: dict[str, Any]) -> str:
        """Render a report from a template string.

        Args:
            template_string: Django template string
            context: Context dictionary for template rendering

        Returns:
            str: Rendered report content
        """
        template = Template(template_string)
        return template.render(Context(context))
