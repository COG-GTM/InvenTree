"""Cloud migration utilities for on-prem to OCI migration.

This module provides utilities for planning and executing migration
of InvenTree data and workloads from on-premises to OCI cloud.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from django.db import models

import structlog

logger = structlog.get_logger(__name__)


class MigrationPhase(Enum):
    """Migration phase enumeration."""

    ASSESSMENT = 'assessment'
    PLANNING = 'planning'
    PREPARATION = 'preparation'
    MIGRATION = 'migration'
    VALIDATION = 'validation'
    CUTOVER = 'cutover'
    OPTIMIZATION = 'optimization'


class MigrationStatus(Enum):
    """Migration status enumeration."""

    NOT_STARTED = 'not_started'
    IN_PROGRESS = 'in_progress'
    COMPLETED = 'completed'
    FAILED = 'failed'
    PAUSED = 'paused'


@dataclass
class DataInventoryItem:
    """Represents an item in the data inventory for migration.

    Attributes:
        name: Name of the data entity (e.g., table name, model name)
        entity_type: Type of entity ('table', 'file', 'config')
        record_count: Number of records
        size_bytes: Size in bytes
        dependencies: List of dependent entities
        priority: Migration priority (1-5, 1 being highest)
        notes: Additional notes
    """

    name: str
    entity_type: str
    record_count: int = 0
    size_bytes: int = 0
    dependencies: list[str] = field(default_factory=list)
    priority: int = 3
    notes: str = ''

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            'name': self.name,
            'entity_type': self.entity_type,
            'record_count': self.record_count,
            'size_bytes': self.size_bytes,
            'size_mb': round(self.size_bytes / (1024 * 1024), 2),
            'dependencies': self.dependencies,
            'priority': self.priority,
            'notes': self.notes,
        }


@dataclass
class MigrationTask:
    """Represents a migration task.

    Attributes:
        task_id: Unique task identifier
        name: Task name
        description: Task description
        phase: Migration phase
        status: Current status
        data_items: Data items involved in this task
        started_at: When the task started
        completed_at: When the task completed
        error_message: Error message if failed
    """

    task_id: str
    name: str
    description: str
    phase: MigrationPhase
    status: MigrationStatus = MigrationStatus.NOT_STARTED
    data_items: list[str] = field(default_factory=list)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error_message: str = ''

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            'task_id': self.task_id,
            'name': self.name,
            'description': self.description,
            'phase': self.phase.value,
            'status': self.status.value,
            'data_items': self.data_items,
            'started_at': self.started_at.isoformat() if self.started_at else None,
            'completed_at': self.completed_at.isoformat()
            if self.completed_at
            else None,
            'error_message': self.error_message,
        }


@dataclass
class MigrationPlan:
    """Complete migration plan from on-prem to OCI.

    Attributes:
        plan_id: Unique plan identifier
        name: Plan name
        description: Plan description
        created_at: When the plan was created
        target_completion: Target completion date
        current_phase: Current migration phase
        status: Overall migration status
        inventory: Data inventory items
        tasks: Migration tasks
    """

    plan_id: str
    name: str
    description: str
    created_at: datetime = field(default_factory=datetime.now)
    target_completion: datetime | None = None
    current_phase: MigrationPhase = MigrationPhase.ASSESSMENT
    status: MigrationStatus = MigrationStatus.NOT_STARTED
    inventory: list[DataInventoryItem] = field(default_factory=list)
    tasks: list[MigrationTask] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary.

        Returns:
            Dictionary representation
        """
        return {
            'plan_id': self.plan_id,
            'name': self.name,
            'description': self.description,
            'created_at': self.created_at.isoformat(),
            'target_completion': (
                self.target_completion.isoformat() if self.target_completion else None
            ),
            'current_phase': self.current_phase.value,
            'status': self.status.value,
            'inventory': [item.to_dict() for item in self.inventory],
            'tasks': [task.to_dict() for task in self.tasks],
            'progress': self._calculate_progress(),
        }

    def _calculate_progress(self) -> dict[str, Any]:
        """Calculate migration progress.

        Returns:
            Progress statistics
        """
        total_tasks = len(self.tasks)
        completed_tasks = sum(
            1 for t in self.tasks if t.status == MigrationStatus.COMPLETED
        )
        failed_tasks = sum(1 for t in self.tasks if t.status == MigrationStatus.FAILED)
        in_progress_tasks = sum(
            1 for t in self.tasks if t.status == MigrationStatus.IN_PROGRESS
        )

        return {
            'total_tasks': total_tasks,
            'completed_tasks': completed_tasks,
            'failed_tasks': failed_tasks,
            'in_progress_tasks': in_progress_tasks,
            'completion_percent': (
                round(completed_tasks / total_tasks * 100, 2) if total_tasks > 0 else 0
            ),
        }


class DataInventoryScanner:
    """Scanner for creating data inventory from InvenTree models.

    This class scans the InvenTree database to create an inventory
    of all data that needs to be migrated to OCI.

    Example:
        scanner = DataInventoryScanner()
        inventory = scanner.scan_all_models()
    """

    CORE_MODELS = [
        ('part', 'Part'),
        ('part', 'PartCategory'),
        ('part', 'BomItem'),
        ('part', 'PartParameter'),
        ('stock', 'StockItem'),
        ('stock', 'StockLocation'),
        ('build', 'Build'),
        ('build', 'BuildItem'),
        ('order', 'PurchaseOrder'),
        ('order', 'SalesOrder'),
        ('company', 'Company'),
        ('company', 'SupplierPart'),
        ('users', 'User'),
    ]

    def __init__(self):
        """Initialize the scanner."""
        self._inventory: list[DataInventoryItem] = []

    def scan_all_models(self) -> list[DataInventoryItem]:
        """Scan all InvenTree models and create inventory.

        Returns:
            List of DataInventoryItem objects
        """
        self._inventory = []

        for app_label, model_name in self.CORE_MODELS:
            try:
                item = self._scan_model(app_label, model_name)
                if item:
                    self._inventory.append(item)
            except Exception as e:
                logger.error(
                    'model_scan_failed',
                    app_label=app_label,
                    model_name=model_name,
                    error=str(e),
                )

        logger.info('inventory_scan_completed', item_count=len(self._inventory))
        return self._inventory

    def _scan_model(self, app_label: str, model_name: str) -> DataInventoryItem | None:
        """Scan a single model.

        Args:
            app_label: Django app label
            model_name: Model class name

        Returns:
            DataInventoryItem or None if model not found
        """
        try:
            from django.apps import apps

            model = apps.get_model(app_label, model_name)
            record_count = model.objects.count()

            dependencies = self._get_model_dependencies(model)

            priority = self._determine_priority(app_label, model_name)

            return DataInventoryItem(
                name=f'{app_label}.{model_name}',
                entity_type='table',
                record_count=record_count,
                size_bytes=0,
                dependencies=dependencies,
                priority=priority,
            )
        except LookupError:
            logger.warning(
                'model_not_found', app_label=app_label, model_name=model_name
            )
            return None

    def _get_model_dependencies(self, model: type[models.Model]) -> list[str]:
        """Get foreign key dependencies for a model.

        Args:
            model: Django model class

        Returns:
            List of dependent model names
        """
        dependencies = []

        for field_obj in model._meta.fields:
            if field_obj.is_relation and hasattr(field_obj, 'related_model'):
                related = field_obj.related_model
                if related:
                    dep_name = f'{related._meta.app_label}.{related.__name__}'
                    if dep_name not in dependencies:
                        dependencies.append(dep_name)

        return dependencies

    def _determine_priority(self, app_label: str, model_name: str) -> int:
        """Determine migration priority for a model.

        Args:
            app_label: Django app label
            model_name: Model class name

        Returns:
            Priority level (1-5)
        """
        high_priority = ['Part', 'PartCategory', 'StockLocation', 'Company', 'User']
        medium_priority = ['StockItem', 'Build', 'BomItem']

        if model_name in high_priority:
            return 1
        elif model_name in medium_priority:
            return 2
        else:
            return 3

    def get_inventory(self) -> list[DataInventoryItem]:
        """Get the current inventory.

        Returns:
            List of inventory items
        """
        return self._inventory

    def export_inventory(self) -> dict[str, Any]:
        """Export inventory as a dictionary.

        Returns:
            Dictionary with inventory data
        """
        return {
            'scanned_at': datetime.now().isoformat(),
            'total_items': len(self._inventory),
            'total_records': sum(item.record_count for item in self._inventory),
            'items': [item.to_dict() for item in self._inventory],
        }


class MigrationPlanner:
    """Planner for creating migration plans.

    This class creates comprehensive migration plans based on
    data inventory and migration requirements.

    Example:
        planner = MigrationPlanner()
        plan = planner.create_plan('BEP MES Migration', inventory)
    """

    def __init__(self):
        """Initialize the planner."""
        self._plans: dict[str, MigrationPlan] = {}

    def create_plan(
        self,
        name: str,
        inventory: list[DataInventoryItem],
        description: str = '',
        target_completion: datetime | None = None,
    ) -> MigrationPlan:
        """Create a new migration plan.

        Args:
            name: Plan name
            inventory: Data inventory items
            description: Plan description
            target_completion: Target completion date

        Returns:
            Created MigrationPlan
        """
        import uuid

        plan_id = str(uuid.uuid4())

        plan = MigrationPlan(
            plan_id=plan_id,
            name=name,
            description=description or f'Migration plan for {name}',
            target_completion=target_completion,
            inventory=inventory,
        )

        plan.tasks = self._generate_tasks(inventory)

        self._plans[plan_id] = plan

        logger.info(
            'migration_plan_created',
            plan_id=plan_id,
            name=name,
            task_count=len(plan.tasks),
        )

        return plan

    def _generate_tasks(
        self, inventory: list[DataInventoryItem]
    ) -> list[MigrationTask]:
        """Generate migration tasks from inventory.

        Args:
            inventory: Data inventory items

        Returns:
            List of MigrationTask objects
        """
        import uuid

        tasks = []

        tasks.append(
            MigrationTask(
                task_id=str(uuid.uuid4()),
                name='Assessment - Analyze Current State',
                description='Analyze current on-premises MES data and infrastructure',
                phase=MigrationPhase.ASSESSMENT,
            )
        )

        tasks.append(
            MigrationTask(
                task_id=str(uuid.uuid4()),
                name='Assessment - Identify Dependencies',
                description='Map all data dependencies and integration points',
                phase=MigrationPhase.ASSESSMENT,
            )
        )

        tasks.append(
            MigrationTask(
                task_id=str(uuid.uuid4()),
                name='Planning - Design OCI Architecture',
                description='Design target OCI architecture and services',
                phase=MigrationPhase.PLANNING,
            )
        )

        tasks.append(
            MigrationTask(
                task_id=str(uuid.uuid4()),
                name='Planning - Create Migration Schedule',
                description='Create detailed migration schedule with milestones',
                phase=MigrationPhase.PLANNING,
            )
        )

        tasks.append(
            MigrationTask(
                task_id=str(uuid.uuid4()),
                name='Preparation - Provision OCI Resources',
                description='Provision required OCI resources (ADB, Object Storage, etc.)',
                phase=MigrationPhase.PREPARATION,
            )
        )

        tasks.append(
            MigrationTask(
                task_id=str(uuid.uuid4()),
                name='Preparation - Configure Network Connectivity',
                description='Set up VPN/FastConnect between on-prem and OCI',
                phase=MigrationPhase.PREPARATION,
            )
        )

        sorted_inventory = sorted(inventory, key=lambda x: x.priority)

        for item in sorted_inventory:
            tasks.append(
                MigrationTask(
                    task_id=str(uuid.uuid4()),
                    name=f'Migration - Migrate {item.name}',
                    description=f'Migrate {item.record_count} records from {item.name}',
                    phase=MigrationPhase.MIGRATION,
                    data_items=[item.name],
                )
            )

        tasks.append(
            MigrationTask(
                task_id=str(uuid.uuid4()),
                name='Validation - Data Integrity Check',
                description='Verify data integrity after migration',
                phase=MigrationPhase.VALIDATION,
            )
        )

        tasks.append(
            MigrationTask(
                task_id=str(uuid.uuid4()),
                name='Validation - Application Testing',
                description='Test application functionality with migrated data',
                phase=MigrationPhase.VALIDATION,
            )
        )

        tasks.append(
            MigrationTask(
                task_id=str(uuid.uuid4()),
                name='Cutover - Switch to OCI',
                description='Perform final cutover to OCI environment',
                phase=MigrationPhase.CUTOVER,
            )
        )

        tasks.append(
            MigrationTask(
                task_id=str(uuid.uuid4()),
                name='Optimization - Performance Tuning',
                description='Optimize OCI resources for performance',
                phase=MigrationPhase.OPTIMIZATION,
            )
        )

        return tasks

    def get_plan(self, plan_id: str) -> MigrationPlan | None:
        """Get a migration plan by ID.

        Args:
            plan_id: Plan ID

        Returns:
            MigrationPlan or None if not found
        """
        return self._plans.get(plan_id)

    def list_plans(self) -> list[MigrationPlan]:
        """List all migration plans.

        Returns:
            List of MigrationPlan objects
        """
        return list(self._plans.values())

    def update_task_status(
        self,
        plan_id: str,
        task_id: str,
        status: MigrationStatus,
        error_message: str = '',
    ) -> bool:
        """Update the status of a migration task.

        Args:
            plan_id: Plan ID
            task_id: Task ID
            status: New status
            error_message: Error message if failed

        Returns:
            True if task was updated
        """
        plan = self._plans.get(plan_id)
        if not plan:
            return False

        for task in plan.tasks:
            if task.task_id == task_id:
                task.status = status
                if status == MigrationStatus.IN_PROGRESS:
                    task.started_at = datetime.now()
                elif status in (MigrationStatus.COMPLETED, MigrationStatus.FAILED):
                    task.completed_at = datetime.now()
                    if error_message:
                        task.error_message = error_message

                logger.info(
                    'migration_task_updated',
                    plan_id=plan_id,
                    task_id=task_id,
                    status=status.value,
                )
                return True

        return False


class MigrationExecutor:
    """Executor for running migration tasks.

    This class executes migration tasks and coordinates data transfer
    between on-premises and OCI.

    Example:
        executor = MigrationExecutor(hybrid_manager)
        result = executor.execute_task(plan, task)
    """

    def __init__(self, hybrid_manager: Any = None):
        """Initialize the executor.

        Args:
            hybrid_manager: HybridCloudManager instance for OCI operations
        """
        self.hybrid_manager = hybrid_manager
        self._execution_log: list[dict[str, Any]] = []

    def execute_task(self, plan: MigrationPlan, task: MigrationTask) -> dict[str, Any]:
        """Execute a migration task.

        Args:
            plan: The migration plan
            task: The task to execute

        Returns:
            Execution result dictionary
        """
        result = {
            'task_id': task.task_id,
            'task_name': task.name,
            'started_at': datetime.now().isoformat(),
            'status': 'running',
        }

        task.status = MigrationStatus.IN_PROGRESS
        task.started_at = datetime.now()

        logger.info(
            'migration_task_started',
            plan_id=plan.plan_id,
            task_id=task.task_id,
            task_name=task.name,
        )

        try:
            if task.phase == MigrationPhase.MIGRATION and task.data_items:
                for data_item in task.data_items:
                    self._migrate_data_item(data_item)

            task.status = MigrationStatus.COMPLETED
            task.completed_at = datetime.now()
            result['status'] = 'completed'
            result['completed_at'] = datetime.now().isoformat()

        except Exception as e:
            task.status = MigrationStatus.FAILED
            task.completed_at = datetime.now()
            task.error_message = str(e)
            result['status'] = 'failed'
            result['error'] = str(e)
            result['completed_at'] = datetime.now().isoformat()

            logger.error(
                'migration_task_failed',
                plan_id=plan.plan_id,
                task_id=task.task_id,
                error=str(e),
            )

        self._execution_log.append(result)
        return result

    def _migrate_data_item(self, data_item: str) -> None:
        """Migrate a single data item.

        Args:
            data_item: Name of the data item to migrate
        """
        logger.info('migrating_data_item', data_item=data_item)

    def get_execution_log(self) -> list[dict[str, Any]]:
        """Get the execution log.

        Returns:
            List of execution results
        """
        return self._execution_log


def create_migration_report(plan: MigrationPlan) -> dict[str, Any]:
    """Create a comprehensive migration report.

    Args:
        plan: The migration plan

    Returns:
        Report dictionary
    """
    progress = plan._calculate_progress()

    phase_progress = {}
    for phase in MigrationPhase:
        phase_tasks = [t for t in plan.tasks if t.phase == phase]
        completed = sum(1 for t in phase_tasks if t.status == MigrationStatus.COMPLETED)
        phase_progress[phase.value] = {
            'total': len(phase_tasks),
            'completed': completed,
            'percent': round(completed / len(phase_tasks) * 100, 2)
            if phase_tasks
            else 0,
        }

    return {
        'plan_id': plan.plan_id,
        'plan_name': plan.name,
        'generated_at': datetime.now().isoformat(),
        'current_phase': plan.current_phase.value,
        'overall_status': plan.status.value,
        'overall_progress': progress,
        'phase_progress': phase_progress,
        'inventory_summary': {
            'total_items': len(plan.inventory),
            'total_records': sum(item.record_count for item in plan.inventory),
            'by_priority': {
                i: sum(1 for item in plan.inventory if item.priority == i)
                for i in range(1, 6)
            },
        },
        'task_summary': {
            'total': len(plan.tasks),
            'by_status': {
                status.value: sum(1 for t in plan.tasks if t.status == status)
                for status in MigrationStatus
            },
        },
    }
