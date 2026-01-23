"""ETL (Extract, Transform, Load) utilities for BEP MES requirements.

This module provides data transformation and integration capabilities
for synchronizing data between InvenTree and external systems.

Features:
- Data extraction from InvenTree models
- Data transformation pipelines
- Data loading to external systems
- Data validation and quality checks
"""

import csv
import io
import json
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from django.db.models import QuerySet

import structlog

logger = structlog.get_logger('inventree')


@dataclass
class TransformationStep:
    """Definition of a data transformation step."""

    name: str
    description: str
    transform_func: Callable[[dict], dict]
    enabled: bool = True


@dataclass
class ValidationRule:
    """Definition of a data validation rule."""

    name: str
    description: str
    validate_func: Callable[[dict], tuple[bool, str]]
    severity: str = 'error'


@dataclass
class ETLPipeline:
    """Definition of an ETL pipeline."""

    pipeline_id: str
    name: str
    description: str
    source_model: str
    transformations: list[TransformationStep] = field(default_factory=list)
    validations: list[ValidationRule] = field(default_factory=list)
    target_format: str = 'json'


class DataExtractor:
    """Extract data from InvenTree models.

    This class provides methods for extracting data from Django models
    with support for filtering, field selection, and related data.
    """

    def __init__(self):
        """Initialize the data extractor."""
        self.extraction_stats = {
            'total_records': 0,
            'extracted_records': 0,
            'errors': 0,
        }

    def extract_queryset(
        self,
        queryset: QuerySet,
        fields: list[str] | None = None,
        include_related: bool = False,
    ) -> list[dict]:
        """Extract data from a QuerySet.

        Args:
            queryset: Django QuerySet to extract from
            fields: Optional list of fields to include
            include_related: Whether to include related object data

        Returns:
            list: List of dictionaries with extracted data
        """
        self.extraction_stats['total_records'] = queryset.count()

        data = list(queryset.values(*fields)) if fields else list(queryset.values())

        self.extraction_stats['extracted_records'] = len(data)

        if include_related:
            data = self._include_related_data(queryset, data)

        logger.info(
            'data_extracted',
            total=self.extraction_stats['total_records'],
            extracted=self.extraction_stats['extracted_records'],
        )

        return data

    def _include_related_data(self, queryset: QuerySet, data: list[dict]) -> list[dict]:
        """Include related object data in extraction.

        Args:
            queryset: Original QuerySet
            data: Extracted data list

        Returns:
            list: Data with related objects included
        """
        model = queryset.model

        for field_obj in model._meta.fields:
            if field_obj.is_relation:
                related_name = field_obj.name
                for record in data:
                    if record.get(related_name):
                        record[f'{related_name}_display'] = str(
                            record.get(related_name, '')
                        )

        return data

    def extract_to_csv(
        self, queryset: QuerySet, fields: list[str] | None = None
    ) -> str:
        """Extract data to CSV format.

        Args:
            queryset: Django QuerySet to extract from
            fields: Optional list of fields to include

        Returns:
            str: CSV formatted string
        """
        data = self.extract_queryset(queryset, fields)

        if not data:
            return ''

        output = io.StringIO()
        fieldnames = list(data[0].keys())

        writer = csv.DictWriter(output, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(data)

        return output.getvalue()

    def extract_to_json(
        self, queryset: QuerySet, fields: list[str] | None = None
    ) -> str:
        """Extract data to JSON format.

        Args:
            queryset: Django QuerySet to extract from
            fields: Optional list of fields to include

        Returns:
            str: JSON formatted string
        """
        data = self.extract_queryset(queryset, fields)

        return json.dumps(
            {
                'extracted_at': datetime.now().isoformat(),
                'record_count': len(data),
                'data': data,
            },
            indent=2,
            default=str,
        )


class DataTransformer:
    """Transform data through configurable pipelines.

    This class provides methods for applying transformations
    to data records, including field mapping, value conversion,
    and data enrichment.
    """

    def __init__(self):
        """Initialize the data transformer."""
        self.transformation_stats = {
            'total_records': 0,
            'transformed_records': 0,
            'errors': 0,
        }

    def transform(
        self, data: list[dict], transformations: list[TransformationStep]
    ) -> list[dict]:
        """Apply transformations to data.

        Args:
            data: List of data dictionaries
            transformations: List of transformation steps to apply

        Returns:
            list: Transformed data
        """
        self.transformation_stats['total_records'] = len(data)
        transformed_data = []

        for record in data:
            try:
                transformed_record = record.copy()

                for step in transformations:
                    if step.enabled:
                        transformed_record = step.transform_func(transformed_record)

                transformed_data.append(transformed_record)
                self.transformation_stats['transformed_records'] += 1

            except Exception as e:
                self.transformation_stats['errors'] += 1
                logger.error('transformation_error', record=record, error=str(e))

        logger.info(
            'data_transformed',
            total=self.transformation_stats['total_records'],
            transformed=self.transformation_stats['transformed_records'],
            errors=self.transformation_stats['errors'],
        )

        return transformed_data

    @staticmethod
    def create_field_mapping_transform(field_map: dict[str, str]) -> TransformationStep:
        """Create a field mapping transformation.

        Args:
            field_map: Dictionary mapping old field names to new names

        Returns:
            TransformationStep: The transformation step
        """

        def transform_func(record: dict) -> dict:
            new_record = {}
            for old_name, new_name in field_map.items():
                if old_name in record:
                    new_record[new_name] = record[old_name]
            for key, value in record.items():
                if key not in field_map:
                    new_record[key] = value
            return new_record

        return TransformationStep(
            name='field_mapping',
            description=f'Map fields: {field_map}',
            transform_func=transform_func,
        )

    @staticmethod
    def create_value_conversion_transform(
        field: str, conversion_func: Callable[[Any], Any]
    ) -> TransformationStep:
        """Create a value conversion transformation.

        Args:
            field: Field name to convert
            conversion_func: Function to convert the value

        Returns:
            TransformationStep: The transformation step
        """

        def transform_func(record: dict) -> dict:
            if field in record:
                record[field] = conversion_func(record[field])
            return record

        return TransformationStep(
            name=f'convert_{field}',
            description=f'Convert values in {field}',
            transform_func=transform_func,
        )

    @staticmethod
    def create_computed_field_transform(
        field_name: str, compute_func: Callable[[dict], Any]
    ) -> TransformationStep:
        """Create a computed field transformation.

        Args:
            field_name: Name of the new computed field
            compute_func: Function to compute the field value

        Returns:
            TransformationStep: The transformation step
        """

        def transform_func(record: dict) -> dict:
            record[field_name] = compute_func(record)
            return record

        return TransformationStep(
            name=f'compute_{field_name}',
            description=f'Compute field {field_name}',
            transform_func=transform_func,
        )


class DataValidator:
    """Validate data against defined rules.

    This class provides methods for validating data records
    against configurable validation rules.
    """

    def __init__(self):
        """Initialize the data validator."""
        self.validation_stats = {
            'total_records': 0,
            'valid_records': 0,
            'invalid_records': 0,
            'errors': [],
        }

    def validate(
        self, data: list[dict], rules: list[ValidationRule]
    ) -> tuple[list[dict], list[dict]]:
        """Validate data against rules.

        Args:
            data: List of data dictionaries
            rules: List of validation rules to apply

        Returns:
            tuple: (valid_records, invalid_records)
        """
        self.validation_stats = {
            'total_records': len(data),
            'valid_records': 0,
            'invalid_records': 0,
            'errors': [],
        }

        valid_records = []
        invalid_records = []

        for record in data:
            is_valid = True
            record_errors = []

            for rule in rules:
                try:
                    rule_valid, message = rule.validate_func(record)
                    if not rule_valid:
                        is_valid = False
                        record_errors.append({
                            'rule': rule.name,
                            'severity': rule.severity,
                            'message': message,
                        })
                except Exception as e:
                    is_valid = False
                    record_errors.append({
                        'rule': rule.name,
                        'severity': 'error',
                        'message': f'Validation error: {e!s}',
                    })

            if is_valid:
                valid_records.append(record)
                self.validation_stats['valid_records'] += 1
            else:
                invalid_record = record.copy()
                invalid_record['_validation_errors'] = record_errors
                invalid_records.append(invalid_record)
                self.validation_stats['invalid_records'] += 1
                self.validation_stats['errors'].extend(record_errors)

        logger.info(
            'data_validated',
            total=self.validation_stats['total_records'],
            valid=self.validation_stats['valid_records'],
            invalid=self.validation_stats['invalid_records'],
        )

        return valid_records, invalid_records

    @staticmethod
    def create_required_field_rule(field: str) -> ValidationRule:
        """Create a required field validation rule.

        Args:
            field: Field name that is required

        Returns:
            ValidationRule: The validation rule
        """

        def validate_func(record: dict) -> tuple[bool, str]:
            if field not in record or record[field] is None:
                return False, f'Required field {field} is missing'
            if isinstance(record[field], str) and not record[field].strip():
                return False, f'Required field {field} is empty'
            return True, ''

        return ValidationRule(
            name=f'required_{field}',
            description=f'Field {field} is required',
            validate_func=validate_func,
        )

    @staticmethod
    def create_type_check_rule(field: str, expected_type: type) -> ValidationRule:
        """Create a type check validation rule.

        Args:
            field: Field name to check
            expected_type: Expected Python type

        Returns:
            ValidationRule: The validation rule
        """

        def validate_func(record: dict) -> tuple[bool, str]:
            if field not in record:
                return True, ''
            if not isinstance(record[field], expected_type):
                return (
                    False,
                    f'Field {field} should be {expected_type.__name__}, '
                    f'got {type(record[field]).__name__}',
                )
            return True, ''

        return ValidationRule(
            name=f'type_check_{field}',
            description=f'Field {field} must be {expected_type.__name__}',
            validate_func=validate_func,
        )

    @staticmethod
    def create_range_check_rule(
        field: str, min_value: float | None = None, max_value: float | None = None
    ) -> ValidationRule:
        """Create a range check validation rule.

        Args:
            field: Field name to check
            min_value: Minimum allowed value
            max_value: Maximum allowed value

        Returns:
            ValidationRule: The validation rule
        """

        def validate_func(record: dict) -> tuple[bool, str]:
            if field not in record or record[field] is None:
                return True, ''

            value = record[field]

            if min_value is not None and value < min_value:
                return (
                    False,
                    f'Field {field} value {value} is below minimum {min_value}',
                )

            if max_value is not None and value > max_value:
                return False, f'Field {field} value {value} exceeds maximum {max_value}'

            return True, ''

        return ValidationRule(
            name=f'range_check_{field}',
            description=f'Field {field} must be between {min_value} and {max_value}',
            validate_func=validate_func,
        )


class DataLoader:
    """Load transformed data to target systems.

    This class provides methods for loading data to various
    target formats and systems.
    """

    def __init__(self):
        """Initialize the data loader."""
        self.load_stats = {'total_records': 0, 'loaded_records': 0, 'errors': 0}

    def load_to_json_file(
        self, data: list[dict], filepath: str, metadata: dict | None = None
    ) -> bool:
        """Load data to a JSON file.

        Args:
            data: List of data dictionaries
            filepath: Path to output file
            metadata: Optional metadata to include

        Returns:
            bool: True if successful
        """
        self.load_stats['total_records'] = len(data)

        try:
            output = {
                'loaded_at': datetime.now().isoformat(),
                'record_count': len(data),
                'metadata': metadata or {},
                'data': data,
            }

            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(output, f, indent=2, default=str)

            self.load_stats['loaded_records'] = len(data)
            logger.info('data_loaded_to_json', filepath=filepath, records=len(data))
            return True

        except Exception as e:
            self.load_stats['errors'] += 1
            logger.error('load_error', filepath=filepath, error=str(e))
            return False

    def load_to_csv_file(self, data: list[dict], filepath: str) -> bool:
        """Load data to a CSV file.

        Args:
            data: List of data dictionaries
            filepath: Path to output file

        Returns:
            bool: True if successful
        """
        self.load_stats['total_records'] = len(data)

        if not data:
            return True

        try:
            fieldnames = list(data[0].keys())

            with open(filepath, 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(data)

            self.load_stats['loaded_records'] = len(data)
            logger.info('data_loaded_to_csv', filepath=filepath, records=len(data))
            return True

        except Exception as e:
            self.load_stats['errors'] += 1
            logger.error('load_error', filepath=filepath, error=str(e))
            return False


class ETLPipelineRunner:
    """Run complete ETL pipelines.

    This class orchestrates the execution of complete ETL pipelines,
    coordinating extraction, transformation, validation, and loading.
    """

    def __init__(self):
        """Initialize the pipeline runner."""
        self.extractor = DataExtractor()
        self.transformer = DataTransformer()
        self.validator = DataValidator()
        self.loader = DataLoader()

    def run_pipeline(
        self, pipeline: ETLPipeline, queryset: QuerySet, output_path: str | None = None
    ) -> dict:
        """Run a complete ETL pipeline.

        Args:
            pipeline: The ETL pipeline definition
            queryset: Source data QuerySet
            output_path: Optional path for output file

        Returns:
            dict: Pipeline execution results
        """
        results = {
            'pipeline_id': pipeline.pipeline_id,
            'started_at': datetime.now().isoformat(),
            'extraction': {},
            'transformation': {},
            'validation': {},
            'loading': {},
            'success': False,
        }

        try:
            data = self.extractor.extract_queryset(queryset)
            results['extraction'] = self.extractor.extraction_stats.copy()

            if pipeline.transformations:
                data = self.transformer.transform(data, pipeline.transformations)
                results['transformation'] = self.transformer.transformation_stats.copy()

            if pipeline.validations:
                valid_data, _invalid_data = self.validator.validate(
                    data, pipeline.validations
                )
                results['validation'] = self.validator.validation_stats.copy()
                data = valid_data

            if output_path:
                if pipeline.target_format == 'json':
                    success = self.loader.load_to_json_file(data, output_path)
                elif pipeline.target_format == 'csv':
                    success = self.loader.load_to_csv_file(data, output_path)
                else:
                    success = False

                results['loading'] = self.loader.load_stats.copy()
                results['loading']['success'] = success

            results['success'] = True
            results['completed_at'] = datetime.now().isoformat()

            logger.info(
                'pipeline_completed', pipeline_id=pipeline.pipeline_id, success=True
            )

        except Exception as e:
            results['error'] = str(e)
            results['completed_at'] = datetime.now().isoformat()

            logger.error(
                'pipeline_failed', pipeline_id=pipeline.pipeline_id, error=str(e)
            )

        return results
