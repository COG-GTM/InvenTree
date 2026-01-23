"""Tests for the scripts module.

This module provides unit tests for script generation, report generation,
and ETL functionality.
"""

from django.test import TestCase

from scripts.etl import (
    DataExtractor,
    DataLoader,
    DataTransformer,
    DataValidator,
    ETLPipelineRunner,
)
from scripts.generators import (
    APITestGenerator,
    ModelTestGenerator,
    TestSuite,
    UATTestCaseGenerator,
)
from scripts.generators import TestCase as GeneratedTestCase
from scripts.reports import (
    ReportGenerator,
    ReportTemplateEngine,
    ScheduledReportManager,
)


class ModelTestGeneratorTest(TestCase):
    """Tests for the ModelTestGenerator class."""

    def setUp(self):
        """Set up test data."""
        self.generator = ModelTestGenerator()

    def test_generator_initialization(self):
        """Test generator initializes correctly."""
        self.assertIsNotNone(self.generator.default_imports)
        self.assertIn(
            'from django.test import TestCase', self.generator.default_imports
        )

    def test_render_test_suite(self):
        """Test rendering a test suite to Python code."""
        suite = TestSuite(
            name='ExampleTestCase',
            description='Test suite for Example model',
            imports=['from django.test import TestCase'],
            test_cases=[
                GeneratedTestCase(
                    name='test_example',
                    description='Test example functionality',
                    test_type='unit',
                    code='def test_example(self):\n    pass',
                )
            ],
        )

        rendered = self.generator.render_test_suite(suite)

        self.assertIn('class ExampleTestCase(TestCase):', rendered)
        self.assertIn('def test_example(self):', rendered)


class APITestGeneratorTest(TestCase):
    """Tests for the APITestGenerator class."""

    def setUp(self):
        """Set up test data."""
        self.generator = APITestGenerator()

    def test_generator_initialization(self):
        """Test generator initializes correctly."""
        self.assertIsNotNone(self.generator.default_imports)
        self.assertIn(
            'from rest_framework.test import APIClient', self.generator.default_imports
        )

    def test_generate_endpoint_tests(self):
        """Test generating endpoint tests."""
        suite = self.generator.generate_endpoint_tests(
            endpoint_url='/api/parts/', model_name='Part', methods=['GET', 'POST']
        )

        self.assertEqual(suite.name, 'PartAPITestCase')
        self.assertGreater(len(suite.test_cases), 0)

        test_names = [tc.name for tc in suite.test_cases]
        self.assertIn('test_part_get', test_names)
        self.assertIn('test_part_post', test_names)
        self.assertIn('test_part_unauthorized', test_names)


class UATTestCaseGeneratorTest(TestCase):
    """Tests for the UATTestCaseGenerator class."""

    def setUp(self):
        """Set up test data."""
        self.generator = UATTestCaseGenerator()

    def test_generate_from_requirement(self):
        """Test generating UAT test cases from a requirement."""
        test_cases = self.generator.generate_from_requirement(
            requirement_id='REQ-001',
            requirement_text='User can create a new part',
            acceptance_criteria=[
                'Part form is displayed when clicking Add Part',
                'Part is saved when form is submitted',
            ],
        )

        self.assertEqual(len(test_cases), 2)
        self.assertEqual(test_cases[0]['test_id'], 'REQ-001-TC001')
        self.assertEqual(test_cases[1]['test_id'], 'REQ-001-TC002')
        self.assertEqual(test_cases[0]['requirement_id'], 'REQ-001')

    def test_export_to_markdown(self):
        """Test exporting test cases to Markdown."""
        test_cases = self.generator.generate_from_requirement(
            requirement_id='REQ-002',
            requirement_text='User can view inventory',
            acceptance_criteria=['Inventory list is displayed'],
        )

        markdown = self.generator.export_to_markdown(test_cases)

        self.assertIn('# UAT Test Cases', markdown)
        self.assertIn('REQ-002-TC001', markdown)
        self.assertIn('Test Steps', markdown)
        self.assertIn('Expected Results', markdown)


class ReportGeneratorTest(TestCase):
    """Tests for the ReportGenerator class."""

    def setUp(self):
        """Set up test data."""
        self.generator = ReportGenerator()

    def test_default_reports_registered(self):
        """Test that default reports are registered."""
        reports = self.generator.list_reports()
        self.assertGreater(len(reports), 0)

        report_ids = [r.report_id for r in reports]
        self.assertIn('inventory_summary', report_ids)
        self.assertIn('build_order_status', report_ids)
        self.assertIn('compliance_audit', report_ids)

    def test_get_report(self):
        """Test getting a report by ID."""
        report = self.generator.get_report('inventory_summary')
        self.assertIsNotNone(report)
        self.assertEqual(report.name, 'Inventory Summary Report')

    def test_get_nonexistent_report(self):
        """Test getting a nonexistent report."""
        report = self.generator.get_report('nonexistent')
        self.assertIsNone(report)

    def test_list_reports_by_category(self):
        """Test listing reports by category."""
        manufacturing_reports = self.generator.list_reports(category='Manufacturing')
        self.assertGreater(len(manufacturing_reports), 0)

        for report in manufacturing_reports:
            self.assertEqual(report.category, 'Manufacturing')

    def test_validate_parameters_valid(self):
        """Test validating valid parameters."""
        is_valid, errors = self.generator.validate_parameters(
            'build_order_status', {'start_date': '2026-01-01', 'end_date': '2026-01-31'}
        )
        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_validate_parameters_missing_required(self):
        """Test validating with missing required parameters."""
        is_valid, errors = self.generator.validate_parameters(
            'build_order_status', {'start_date': '2026-01-01'}
        )
        self.assertFalse(is_valid)
        self.assertGreater(len(errors), 0)

    def test_generate_json_report(self):
        """Test generating a JSON report."""
        data = [
            {'id': 1, 'name': 'Part A', 'quantity': 100},
            {'id': 2, 'name': 'Part B', 'quantity': 50},
        ]

        content_type, report_bytes = self.generator.generate_report(
            'inventory_summary',
            {'include_zero_stock': False},
            data,
            output_format='json',
        )

        self.assertEqual(content_type, 'application/json')
        self.assertIn(b'Part A', report_bytes)
        self.assertIn(b'Part B', report_bytes)

    def test_generate_csv_report(self):
        """Test generating a CSV report."""
        data = [
            {'id': 1, 'name': 'Part A', 'quantity': 100},
            {'id': 2, 'name': 'Part B', 'quantity': 50},
        ]

        content_type, report_bytes = self.generator.generate_report(
            'inventory_summary',
            {'include_zero_stock': False},
            data,
            output_format='csv',
        )

        self.assertEqual(content_type, 'text/csv')
        csv_content = report_bytes.decode('utf-8')
        self.assertIn('id,name,quantity', csv_content)
        self.assertIn('Part A', csv_content)


class ScheduledReportManagerTest(TestCase):
    """Tests for the ScheduledReportManager class."""

    def setUp(self):
        """Set up test data."""
        self.generator = ReportGenerator()
        self.manager = ScheduledReportManager(self.generator)

    def test_add_schedule(self):
        """Test adding a scheduled report."""
        schedule = self.manager.add_schedule(
            report_id='inventory_summary',
            params={'include_zero_stock': False},
            schedule='0 8 * * *',
            recipients=['admin@example.com'],
        )

        self.assertIsNotNone(schedule['id'])
        self.assertEqual(schedule['report_id'], 'inventory_summary')
        self.assertTrue(schedule['enabled'])

    def test_list_schedules(self):
        """Test listing scheduled reports."""
        self.manager.add_schedule(
            report_id='inventory_summary',
            params={},
            schedule='0 8 * * *',
            recipients=['admin@example.com'],
        )

        schedules = self.manager.list_schedules()
        self.assertEqual(len(schedules), 1)

    def test_remove_schedule(self):
        """Test removing a scheduled report."""
        schedule = self.manager.add_schedule(
            report_id='inventory_summary',
            params={},
            schedule='0 8 * * *',
            recipients=['admin@example.com'],
        )

        result = self.manager.remove_schedule(schedule['id'])
        self.assertTrue(result)

        schedules = self.manager.list_schedules()
        self.assertEqual(len(schedules), 0)


class ReportTemplateEngineTest(TestCase):
    """Tests for the ReportTemplateEngine class."""

    def setUp(self):
        """Set up test data."""
        self.engine = ReportTemplateEngine()

    def test_register_and_render_template(self):
        """Test registering and rendering a template."""
        self.engine.register_template(
            'test_template', 'Hello {{ name }}! You have {{ count }} items.'
        )

        result = self.engine.render('test_template', {'name': 'User', 'count': 5})

        self.assertEqual(result, 'Hello User! You have 5 items.')

    def test_render_nonexistent_template(self):
        """Test rendering a nonexistent template."""
        with self.assertRaises(ValueError):
            self.engine.render('nonexistent', {})

    def test_render_string(self):
        """Test rendering from a template string."""
        result = self.engine.render_string('Total: {{ total }}', {'total': 100})

        self.assertEqual(result, 'Total: 100')


class DataExtractorTest(TestCase):
    """Tests for the DataExtractor class."""

    def setUp(self):
        """Set up test data."""
        self.extractor = DataExtractor()

    def test_extractor_initialization(self):
        """Test extractor initializes correctly."""
        self.assertEqual(self.extractor.extraction_stats['total_records'], 0)
        self.assertEqual(self.extractor.extraction_stats['extracted_records'], 0)


class DataTransformerTest(TestCase):
    """Tests for the DataTransformer class."""

    def setUp(self):
        """Set up test data."""
        self.transformer = DataTransformer()

    def test_transform_with_field_mapping(self):
        """Test transforming data with field mapping."""
        data = [
            {'old_name': 'value1', 'other': 'data1'},
            {'old_name': 'value2', 'other': 'data2'},
        ]

        transform = DataTransformer.create_field_mapping_transform({
            'old_name': 'new_name'
        })

        result = self.transformer.transform(data, [transform])

        self.assertEqual(result[0]['new_name'], 'value1')
        self.assertEqual(result[0]['other'], 'data1')

    def test_transform_with_value_conversion(self):
        """Test transforming data with value conversion."""
        data = [{'value': '100'}, {'value': '200'}]

        transform = DataTransformer.create_value_conversion_transform('value', int)

        result = self.transformer.transform(data, [transform])

        self.assertEqual(result[0]['value'], 100)
        self.assertEqual(result[1]['value'], 200)

    def test_transform_with_computed_field(self):
        """Test transforming data with computed field."""
        data = [{'quantity': 10, 'price': 5.0}, {'quantity': 20, 'price': 3.0}]

        transform = DataTransformer.create_computed_field_transform(
            'total', lambda r: r['quantity'] * r['price']
        )

        result = self.transformer.transform(data, [transform])

        self.assertEqual(result[0]['total'], 50.0)
        self.assertEqual(result[1]['total'], 60.0)


class DataValidatorTest(TestCase):
    """Tests for the DataValidator class."""

    def setUp(self):
        """Set up test data."""
        self.validator = DataValidator()

    def test_validate_required_field_valid(self):
        """Test validating required field with valid data."""
        data = [{'name': 'Test', 'value': 100}]
        rule = DataValidator.create_required_field_rule('name')

        valid, invalid = self.validator.validate(data, [rule])

        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 0)

    def test_validate_required_field_missing(self):
        """Test validating required field with missing data."""
        data = [{'value': 100}]
        rule = DataValidator.create_required_field_rule('name')

        valid, invalid = self.validator.validate(data, [rule])

        self.assertEqual(len(valid), 0)
        self.assertEqual(len(invalid), 1)

    def test_validate_type_check(self):
        """Test validating field type."""
        data = [{'value': 100}, {'value': 'not a number'}]
        rule = DataValidator.create_type_check_rule('value', int)

        valid, invalid = self.validator.validate(data, [rule])

        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 1)

    def test_validate_range_check(self):
        """Test validating field range."""
        data = [{'value': 50}, {'value': 150}]
        rule = DataValidator.create_range_check_rule(
            'value', min_value=0, max_value=100
        )

        valid, invalid = self.validator.validate(data, [rule])

        self.assertEqual(len(valid), 1)
        self.assertEqual(len(invalid), 1)


class DataLoaderTest(TestCase):
    """Tests for the DataLoader class."""

    def setUp(self):
        """Set up test data."""
        self.loader = DataLoader()

    def test_loader_initialization(self):
        """Test loader initializes correctly."""
        self.assertEqual(self.loader.load_stats['total_records'], 0)
        self.assertEqual(self.loader.load_stats['loaded_records'], 0)


class ETLPipelineRunnerTest(TestCase):
    """Tests for the ETLPipelineRunner class."""

    def setUp(self):
        """Set up test data."""
        self.runner = ETLPipelineRunner()

    def test_runner_initialization(self):
        """Test runner initializes correctly."""
        self.assertIsNotNone(self.runner.extractor)
        self.assertIsNotNone(self.runner.transformer)
        self.assertIsNotNone(self.runner.validator)
        self.assertIsNotNone(self.runner.loader)
