"""Test script generators for InvenTree models and APIs.

This module provides automated test script generation capabilities
aligned with BEP MES testing and quality assurance requirements.

Features:
- Model unit test generation
- API integration test generation
- Regression test suite maintenance
- UAT test case generation from business requirements
"""

import textwrap
from dataclasses import dataclass, field
from typing import Any

from django.db import models

import structlog

logger = structlog.get_logger('inventree')


@dataclass
class TestCase:
    """Represents a generated test case."""

    name: str
    description: str
    test_type: str
    code: str
    setup_code: str = ''
    teardown_code: str = ''
    tags: list[str] = field(default_factory=list)


@dataclass
class TestSuite:
    """Collection of related test cases."""

    name: str
    description: str
    test_cases: list[TestCase] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    fixtures: list[str] = field(default_factory=list)


class ModelTestGenerator:
    """Generate unit tests for Django models.

    This generator creates comprehensive test suites for Django models
    including CRUD operations, validation tests, and relationship tests.

    Example:
        generator = ModelTestGenerator()
        suite = generator.generate_test_suite(Part)
        print(suite.render())
    """

    def __init__(self):
        """Initialize the model test generator."""
        self.default_imports = [
            'from django.test import TestCase',
            'from django.contrib.auth.models import User',
            'from django.core.exceptions import ValidationError',
        ]

    def generate_test_suite(self, model_class: type[models.Model]) -> TestSuite:
        """Generate a complete test suite for a Django model.

        Args:
            model_class: The Django model class to generate tests for

        Returns:
            TestSuite: A complete test suite with all generated tests
        """
        model_name = model_class.__name__
        app_label = model_class._meta.app_label

        suite = TestSuite(
            name=f'{model_name}TestCase',
            description=f'Automated test suite for {model_name} model',
            imports=[
                *self.default_imports,
                f'from {app_label}.models import {model_name}',
            ],
        )

        suite.test_cases.extend(self._generate_crud_tests(model_class))
        suite.test_cases.extend(self._generate_field_validation_tests(model_class))
        suite.test_cases.extend(self._generate_relationship_tests(model_class))

        return suite

    def _generate_crud_tests(self, model_class: type[models.Model]) -> list[TestCase]:
        """Generate CRUD operation tests for a model.

        Args:
            model_class: The Django model class

        Returns:
            list: List of TestCase objects for CRUD operations
        """
        model_name = model_class.__name__
        tests = []

        tests.append(
            TestCase(
                name=f'test_{model_name.lower()}_create',
                description=f'Test creating a new {model_name} instance',
                test_type='unit',
                code=textwrap.dedent(f'''
                    def test_{model_name.lower()}_create(self):
                        """Test creating a new {model_name} instance."""
                        # Create instance with required fields
                        instance = {model_name}.objects.create(
                            # Add required field values here
                        )
                        self.assertIsNotNone(instance.pk)
                        self.assertTrue({model_name}.objects.filter(pk=instance.pk).exists())
                ''').strip(),
                tags=['crud', 'create'],
            )
        )

        tests.append(
            TestCase(
                name=f'test_{model_name.lower()}_read',
                description=f'Test reading a {model_name} instance',
                test_type='unit',
                code=textwrap.dedent(f'''
                    def test_{model_name.lower()}_read(self):
                        """Test reading a {model_name} instance."""
                        # Create instance first
                        instance = {model_name}.objects.create(
                            # Add required field values here
                        )
                        # Read it back
                        retrieved = {model_name}.objects.get(pk=instance.pk)
                        self.assertEqual(instance.pk, retrieved.pk)
                ''').strip(),
                tags=['crud', 'read'],
            )
        )

        tests.append(
            TestCase(
                name=f'test_{model_name.lower()}_update',
                description=f'Test updating a {model_name} instance',
                test_type='unit',
                code=textwrap.dedent(f'''
                    def test_{model_name.lower()}_update(self):
                        """Test updating a {model_name} instance."""
                        # Create instance first
                        instance = {model_name}.objects.create(
                            # Add required field values here
                        )
                        # Update a field
                        # instance.field_name = new_value
                        instance.save()
                        # Verify update
                        instance.refresh_from_db()
                        # self.assertEqual(instance.field_name, new_value)
                ''').strip(),
                tags=['crud', 'update'],
            )
        )

        tests.append(
            TestCase(
                name=f'test_{model_name.lower()}_delete',
                description=f'Test deleting a {model_name} instance',
                test_type='unit',
                code=textwrap.dedent(f'''
                    def test_{model_name.lower()}_delete(self):
                        """Test deleting a {model_name} instance."""
                        # Create instance first
                        instance = {model_name}.objects.create(
                            # Add required field values here
                        )
                        pk = instance.pk
                        # Delete it
                        instance.delete()
                        # Verify deletion
                        self.assertFalse({model_name}.objects.filter(pk=pk).exists())
                ''').strip(),
                tags=['crud', 'delete'],
            )
        )

        return tests

    def _generate_field_validation_tests(
        self, model_class: type[models.Model]
    ) -> list[TestCase]:
        """Generate field validation tests for a model.

        Args:
            model_class: The Django model class

        Returns:
            list: List of TestCase objects for field validation
        """
        model_name = model_class.__name__
        tests = []

        for field_obj in model_class._meta.fields:
            field_name = field_obj.name

            if field_name in ['id', 'pk']:
                continue

            if not field_obj.blank and not field_obj.null:
                tests.append(
                    TestCase(
                        name=f'test_{model_name.lower()}_{field_name}_required',
                        description=f'Test that {field_name} is required',
                        test_type='validation',
                        code=textwrap.dedent(f'''
                            def test_{model_name.lower()}_{field_name}_required(self):
                                """Test that {field_name} field is required."""
                                with self.assertRaises(ValidationError):
                                    instance = {model_name}()
                                    instance.full_clean()
                        ''').strip(),
                        tags=['validation', 'required', field_name],
                    )
                )

            if hasattr(field_obj, 'max_length') and field_obj.max_length:
                tests.append(
                    TestCase(
                        name=f'test_{model_name.lower()}_{field_name}_max_length',
                        description=f'Test {field_name} max length validation',
                        test_type='validation',
                        code=textwrap.dedent(f'''
                            def test_{model_name.lower()}_{field_name}_max_length(self):
                                """Test that {field_name} enforces max length of {field_obj.max_length}."""
                                instance = {model_name}()
                                instance.{field_name} = 'x' * {field_obj.max_length + 1}
                                with self.assertRaises(ValidationError):
                                    instance.full_clean()
                        ''').strip(),
                        tags=['validation', 'max_length', field_name],
                    )
                )

        return tests

    def _generate_relationship_tests(
        self, model_class: type[models.Model]
    ) -> list[TestCase]:
        """Generate relationship tests for a model.

        Args:
            model_class: The Django model class

        Returns:
            list: List of TestCase objects for relationships
        """
        model_name = model_class.__name__
        tests = []

        for field_obj in model_class._meta.fields:
            if isinstance(field_obj, models.ForeignKey):
                related_model = field_obj.related_model.__name__
                field_name = field_obj.name

                tests.append(
                    TestCase(
                        name=f'test_{model_name.lower()}_{field_name}_relationship',
                        description=f'Test {field_name} foreign key relationship',
                        test_type='relationship',
                        code=textwrap.dedent(f'''
                            def test_{model_name.lower()}_{field_name}_relationship(self):
                                """Test {field_name} foreign key to {related_model}."""
                                # Create related instance
                                related = {related_model}.objects.create(
                                    # Add required field values
                                )
                                # Create instance with relationship
                                instance = {model_name}.objects.create(
                                    {field_name}=related,
                                    # Add other required fields
                                )
                                self.assertEqual(instance.{field_name}, related)
                        ''').strip(),
                        tags=['relationship', 'foreign_key', field_name],
                    )
                )

        return tests

    def render_test_suite(self, suite: TestSuite) -> str:
        """Render a test suite to Python code.

        Args:
            suite: The TestSuite to render

        Returns:
            str: Python code for the test suite
        """
        lines = ['"""Auto-generated test suite."""', '']

        for import_line in suite.imports:
            lines.append(import_line)
        lines.append('')
        lines.append('')

        lines.append(f'class {suite.name}(TestCase):')
        lines.append(f'    """{suite.description}."""')
        lines.append('')

        for test_case in suite.test_cases:
            for line in test_case.code.split('\n'):
                lines.append(f'    {line}')
            lines.append('')

        return '\n'.join(lines)


class APITestGenerator:
    """Generate integration tests for Django REST Framework APIs.

    This generator creates comprehensive API test suites including
    endpoint tests, authentication tests, and permission tests.
    """

    def __init__(self):
        """Initialize the API test generator."""
        self.default_imports = [
            'from django.test import TestCase',
            'from django.contrib.auth.models import User',
            'from rest_framework.test import APIClient',
            'from rest_framework import status',
        ]

    def generate_endpoint_tests(
        self, endpoint_url: str, model_name: str, methods: list[str] | None = None
    ) -> TestSuite:
        """Generate tests for an API endpoint.

        Args:
            endpoint_url: The URL pattern for the endpoint
            model_name: Name of the model the endpoint serves
            methods: HTTP methods to test (default: GET, POST, PUT, DELETE)

        Returns:
            TestSuite: A complete test suite for the endpoint
        """
        if methods is None:
            methods = ['GET', 'POST', 'PUT', 'DELETE']

        suite = TestSuite(
            name=f'{model_name}APITestCase',
            description=f'API integration tests for {model_name} endpoint',
            imports=self.default_imports,
        )

        for method in methods:
            suite.test_cases.append(
                self._generate_method_test(endpoint_url, model_name, method)
            )

        suite.test_cases.append(self._generate_auth_test(endpoint_url, model_name))

        return suite

    def _generate_method_test(
        self, endpoint_url: str, model_name: str, method: str
    ) -> TestCase:
        """Generate a test for a specific HTTP method.

        Args:
            endpoint_url: The URL pattern
            model_name: Name of the model
            method: HTTP method to test

        Returns:
            TestCase: A test case for the method
        """
        method_lower = method.lower()

        return TestCase(
            name=f'test_{model_name.lower()}_{method_lower}',
            description=f'Test {method} request to {model_name} endpoint',
            test_type='integration',
            code=textwrap.dedent(f'''
                def test_{model_name.lower()}_{method_lower}(self):
                    """Test {method} request to {endpoint_url}."""
                    self.client = APIClient()
                    # Authenticate if required
                    user = User.objects.create_user(
                        username='testuser',
                        password='testpass123'
                    )
                    self.client.force_authenticate(user=user)

                    response = self.client.{method_lower}('{endpoint_url}')
                    # Assert expected status code
                    # self.assertEqual(response.status_code, status.HTTP_200_OK)
            ''').strip(),
            tags=['api', method_lower, model_name.lower()],
        )

    def _generate_auth_test(self, endpoint_url: str, model_name: str) -> TestCase:
        """Generate an authentication test for an endpoint.

        Args:
            endpoint_url: The URL pattern
            model_name: Name of the model

        Returns:
            TestCase: A test case for authentication
        """
        return TestCase(
            name=f'test_{model_name.lower()}_unauthorized',
            description=f'Test unauthorized access to {model_name} endpoint',
            test_type='security',
            code=textwrap.dedent(f'''
                def test_{model_name.lower()}_unauthorized(self):
                    """Test that unauthenticated requests are rejected."""
                    self.client = APIClient()
                    response = self.client.get('{endpoint_url}')
                    self.assertIn(
                        response.status_code,
                        [status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN]
                    )
            ''').strip(),
            tags=['api', 'security', 'authentication'],
        )

    def render_test_suite(self, suite: TestSuite) -> str:
        """Render a test suite to Python code.

        Args:
            suite: The TestSuite to render

        Returns:
            str: Python code for the test suite
        """
        lines = ['"""Auto-generated API test suite."""', '']

        for import_line in suite.imports:
            lines.append(import_line)
        lines.append('')
        lines.append('')

        lines.append(f'class {suite.name}(TestCase):')
        lines.append(f'    """{suite.description}."""')
        lines.append('')

        for test_case in suite.test_cases:
            for line in test_case.code.split('\n'):
                lines.append(f'    {line}')
            lines.append('')

        return '\n'.join(lines)


class UATTestCaseGenerator:
    """Generate UAT test cases from business requirements.

    This generator converts business requirements into structured
    test cases suitable for user acceptance testing.
    """

    def __init__(self):
        """Initialize the UAT test case generator."""
        self.test_cases = []

    def generate_from_requirement(
        self, requirement_id: str, requirement_text: str, acceptance_criteria: list[str]
    ) -> list[dict[str, Any]]:
        """Generate UAT test cases from a business requirement.

        Args:
            requirement_id: Unique identifier for the requirement
            requirement_text: Description of the requirement
            acceptance_criteria: List of acceptance criteria

        Returns:
            list: List of UAT test case dictionaries
        """
        test_cases = []

        for i, criterion in enumerate(acceptance_criteria, 1):
            test_case = {
                'test_id': f'{requirement_id}-TC{i:03d}',
                'requirement_id': requirement_id,
                'requirement_text': requirement_text,
                'acceptance_criterion': criterion,
                'preconditions': [],
                'test_steps': self._generate_test_steps(criterion),
                'expected_results': self._generate_expected_results(criterion),
                'actual_results': '',
                'status': 'Not Executed',
                'tester': '',
                'test_date': '',
                'notes': '',
            }
            test_cases.append(test_case)

        return test_cases

    def _generate_test_steps(self, criterion: str) -> list[str]:
        """Generate test steps from an acceptance criterion.

        Args:
            criterion: The acceptance criterion text

        Returns:
            list: List of test step descriptions
        """
        steps = [
            'Navigate to the relevant application area',
            'Ensure all preconditions are met',
            f'Perform action to verify: {criterion}',
            'Observe the system response',
            'Document the actual results',
        ]
        return steps

    def _generate_expected_results(self, criterion: str) -> list[str]:
        """Generate expected results from an acceptance criterion.

        Args:
            criterion: The acceptance criterion text

        Returns:
            list: List of expected result descriptions
        """
        return [
            f'System behavior matches criterion: {criterion}',
            'No errors or unexpected behavior observed',
            'Data integrity is maintained',
        ]

    def export_to_csv(self, test_cases: list[dict], filepath: str) -> None:
        """Export UAT test cases to CSV format.

        Args:
            test_cases: List of test case dictionaries
            filepath: Path to write the CSV file
        """
        import csv

        if not test_cases:
            return

        fieldnames = test_cases[0].keys()

        with open(filepath, 'w', newline='', encoding='utf-8') as csvfile:
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            for test_case in test_cases:
                row = {}
                for key, value in test_case.items():
                    if isinstance(value, list):
                        row[key] = '\n'.join(value)
                    else:
                        row[key] = value
                writer.writerow(row)

    def export_to_markdown(self, test_cases: list[dict]) -> str:
        """Export UAT test cases to Markdown format.

        Args:
            test_cases: List of test case dictionaries

        Returns:
            str: Markdown formatted test cases
        """
        lines = ['# UAT Test Cases', '']

        for tc in test_cases:
            lines.append(f'## {tc["test_id"]}: {tc["acceptance_criterion"][:50]}...')
            lines.append('')
            lines.append(f'**Requirement ID:** {tc["requirement_id"]}')
            lines.append(f'**Requirement:** {tc["requirement_text"]}')
            lines.append(f'**Acceptance Criterion:** {tc["acceptance_criterion"]}')
            lines.append('')
            lines.append('### Test Steps')
            for i, step in enumerate(tc['test_steps'], 1):
                lines.append(f'{i}. {step}')
            lines.append('')
            lines.append('### Expected Results')
            for result in tc['expected_results']:
                lines.append(f'- {result}')
            lines.append('')
            lines.append(f'**Status:** {tc["status"]}')
            lines.append('')
            lines.append('---')
            lines.append('')

        return '\n'.join(lines)
