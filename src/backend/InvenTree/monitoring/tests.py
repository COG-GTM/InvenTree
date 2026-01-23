"""Tests for the monitoring module.

This module provides unit tests for metrics, health checks, alerts,
logging, OCI integration, and cloud migration utilities.
"""

from datetime import datetime

from django.test import TestCase

from monitoring.alerts import AlertManager, AlertRule, AlertStatus
from monitoring.cloud_migration import (
    DataInventoryItem,
    MigrationPlanner,
    MigrationStatus,
    create_migration_report,
)
from monitoring.health import (
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    SystemHealth,
)
from monitoring.logging import LogAggregator, LogEntry, LogFilter, LogLevel, LogParser
from monitoring.metrics import MetricDefinition, MetricsRegistry, Timer
from monitoring.oci_integration import (
    HybridCloudManager,
    OCIConfig,
    OCIMonitoringAdapter,
    OCIObjectStorageAdapter,
    OCIRegion,
)


class MetricsRegistryTest(TestCase):
    """Tests for the MetricsRegistry class."""

    def setUp(self):
        """Set up test data."""
        self.registry = MetricsRegistry()

    def test_register_metric(self):
        """Test registering a metric."""
        metric = MetricDefinition(
            name='test_counter',
            description='Test counter metric',
            metric_type='counter',
        )
        self.registry.register_metric(metric)

        registered = self.registry.get_metric('test_counter')
        self.assertIsNotNone(registered)
        self.assertEqual(registered.name, 'test_counter')

    def test_increment_counter(self):
        """Test incrementing a counter."""
        self.registry.increment('requests_total')
        self.registry.increment('requests_total')
        self.registry.increment('requests_total', value=5)

        value = self.registry.get_counter_value('requests_total')
        self.assertEqual(value, 7.0)

    def test_increment_counter_with_labels(self):
        """Test incrementing a counter with labels."""
        self.registry.increment(
            'requests_total', labels={'method': 'GET', 'status': '200'}
        )
        self.registry.increment(
            'requests_total', labels={'method': 'POST', 'status': '201'}
        )

        get_value = self.registry.get_counter_value(
            'requests_total', labels={'method': 'GET', 'status': '200'}
        )
        post_value = self.registry.get_counter_value(
            'requests_total', labels={'method': 'POST', 'status': '201'}
        )

        self.assertEqual(get_value, 1.0)
        self.assertEqual(post_value, 1.0)

    def test_set_gauge(self):
        """Test setting a gauge value."""
        self.registry.set_gauge('active_users', 42)
        value = self.registry.get_gauge_value('active_users')
        self.assertEqual(value, 42)

        self.registry.set_gauge('active_users', 50)
        value = self.registry.get_gauge_value('active_users')
        self.assertEqual(value, 50)

    def test_observe_histogram(self):
        """Test observing histogram values."""
        self.registry.observe_histogram('request_duration', 0.1)
        self.registry.observe_histogram('request_duration', 0.2)
        self.registry.observe_histogram('request_duration', 0.3)

        stats = self.registry.get_histogram_stats('request_duration')

        self.assertEqual(stats['count'], 3)
        self.assertAlmostEqual(stats['sum'], 0.6, places=5)
        self.assertAlmostEqual(stats['min'], 0.1, places=5)
        self.assertAlmostEqual(stats['max'], 0.3, places=5)
        self.assertAlmostEqual(stats['avg'], 0.2, places=5)

    def test_export_metrics(self):
        """Test exporting all metrics."""
        self.registry.increment('counter1')
        self.registry.set_gauge('gauge1', 100)
        self.registry.observe_histogram('histogram1', 1.0)

        exported = self.registry.export_metrics()

        self.assertIn('counters', exported)
        self.assertIn('gauges', exported)
        self.assertIn('histograms', exported)
        self.assertIn('exported_at', exported)

    def test_reset(self):
        """Test resetting all metrics."""
        self.registry.increment('counter1')
        self.registry.set_gauge('gauge1', 100)

        self.registry.reset()

        self.assertEqual(self.registry.get_counter_value('counter1'), 0.0)
        self.assertIsNone(self.registry.get_gauge_value('gauge1'))


class TimerTest(TestCase):
    """Tests for the Timer class."""

    def test_timer_context_manager(self):
        """Test timer as context manager."""
        registry = MetricsRegistry()

        with Timer('test_duration', registry=registry) as timer:
            pass

        self.assertIsNotNone(timer.duration)
        self.assertGreaterEqual(timer.duration, 0)


class HealthCheckerTest(TestCase):
    """Tests for the HealthChecker class."""

    def setUp(self):
        """Set up test data."""
        self.checker = HealthChecker()

    def test_register_check(self):
        """Test registering a health check."""

        def custom_check():
            return HealthCheckResult(
                name='custom', status=HealthStatus.HEALTHY, message='OK'
            )

        self.checker.register_check('custom', custom_check)
        result = self.checker.run_check('custom')

        self.assertIsNotNone(result)
        self.assertEqual(result.name, 'custom')
        self.assertEqual(result.status, HealthStatus.HEALTHY)

    def test_run_all_checks(self):
        """Test running all health checks."""
        health = self.checker.run_all_checks()

        self.assertIsInstance(health, SystemHealth)
        self.assertIsInstance(health.status, HealthStatus)
        self.assertGreater(len(health.checks), 0)

    def test_health_to_dict(self):
        """Test converting health to dictionary."""
        health = self.checker.run_all_checks()
        health_dict = health.to_dict()

        self.assertIn('status', health_dict)
        self.assertIn('timestamp', health_dict)
        self.assertIn('checks', health_dict)

    def test_unregister_check(self):
        """Test unregistering a health check."""

        def custom_check():
            return HealthCheckResult(
                name='custom', status=HealthStatus.HEALTHY, message='OK'
            )

        self.checker.register_check('custom', custom_check)
        result = self.checker.unregister_check('custom')
        self.assertTrue(result)

        check_result = self.checker.run_check('custom')
        self.assertIsNone(check_result)


class AlertManagerTest(TestCase):
    """Tests for the AlertManager class."""

    def setUp(self):
        """Set up test data."""
        self.manager = AlertManager()

    def test_add_rule(self):
        """Test adding an alert rule."""
        rule = AlertRule(
            rule_id='test_rule',
            name='Test Rule',
            description='Test alert rule',
            metric_name='test_metric',
            condition='gt',
            threshold=100,
        )

        self.manager.add_rule(rule)
        retrieved = self.manager.get_rule('test_rule')

        self.assertIsNotNone(retrieved)
        self.assertEqual(retrieved.name, 'Test Rule')

    def test_evaluate_metric_triggers_alert(self):
        """Test that metric evaluation triggers alerts."""
        rule = AlertRule(
            rule_id='high_value',
            name='High Value Alert',
            description='Value exceeds threshold',
            metric_name='value',
            condition='gt',
            threshold=100,
            cooldown_seconds=0,
        )

        self.manager.add_rule(rule)
        alerts = self.manager.evaluate_metric('value', 150)

        self.assertEqual(len(alerts), 1)
        self.assertEqual(alerts[0].name, 'High Value Alert')
        self.assertEqual(alerts[0].metric_value, 150)

    def test_evaluate_metric_no_alert(self):
        """Test that metric evaluation doesn't trigger when below threshold."""
        rule = AlertRule(
            rule_id='high_value',
            name='High Value Alert',
            description='Value exceeds threshold',
            metric_name='value',
            condition='gt',
            threshold=100,
        )

        self.manager.add_rule(rule)
        alerts = self.manager.evaluate_metric('value', 50)

        self.assertEqual(len(alerts), 0)

    def test_acknowledge_alert(self):
        """Test acknowledging an alert."""
        rule = AlertRule(
            rule_id='test_rule',
            name='Test Rule',
            description='Test',
            metric_name='metric',
            condition='gt',
            threshold=0,
            cooldown_seconds=0,
        )

        self.manager.add_rule(rule)
        alerts = self.manager.evaluate_metric('metric', 100)

        result = self.manager.acknowledge_alert(alerts[0].alert_id, user='admin')
        self.assertTrue(result)

        active = self.manager.get_active_alerts()
        self.assertEqual(active[0].status, AlertStatus.ACKNOWLEDGED)

    def test_resolve_alert(self):
        """Test resolving an alert."""
        rule = AlertRule(
            rule_id='test_rule',
            name='Test Rule',
            description='Test',
            metric_name='metric',
            condition='gt',
            threshold=0,
            cooldown_seconds=0,
        )

        self.manager.add_rule(rule)
        alerts = self.manager.evaluate_metric('metric', 100)

        result = self.manager.resolve_alert(alerts[0].alert_id, user='admin')
        self.assertTrue(result)

        active = self.manager.get_active_alerts()
        self.assertEqual(len(active), 0)


class LogParserTest(TestCase):
    """Tests for the LogParser class."""

    def setUp(self):
        """Set up test data."""
        self.parser = LogParser()

    def test_parse_json_log(self):
        """Test parsing JSON log."""
        log_line = '{"timestamp": "2026-01-23T12:00:00", "level": "INFO", "message": "Test message"}'
        entry = self.parser.parse_json_log(log_line)

        self.assertIsNotNone(entry)
        self.assertEqual(entry.level, LogLevel.INFO)
        self.assertEqual(entry.message, 'Test message')

    def test_parse_common_log(self):
        """Test parsing common log format."""
        log_line = '2026-01-23T12:00:00 INFO [app] Test message'
        entry = self.parser.parse_common_log(log_line)

        self.assertIsNotNone(entry)
        self.assertEqual(entry.level, LogLevel.INFO)
        self.assertEqual(entry.source, 'app')
        self.assertEqual(entry.message, 'Test message')

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns None."""
        entry = self.parser.parse_json_log('not valid json')
        self.assertIsNone(entry)


class LogAggregatorTest(TestCase):
    """Tests for the LogAggregator class."""

    def setUp(self):
        """Set up test data."""
        self.aggregator = LogAggregator()

    def test_add_entry(self):
        """Test adding a log entry."""
        entry = LogEntry(
            timestamp=datetime.now(),
            level=LogLevel.INFO,
            message='Test message',
            source='test',
        )

        self.aggregator.add_entry(entry)
        results = self.aggregator.query()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].message, 'Test message')

    def test_query_with_filter(self):
        """Test querying with filters."""
        self.aggregator.add_entry(
            LogEntry(
                timestamp=datetime.now(),
                level=LogLevel.INFO,
                message='Info message',
                source='app',
            )
        )
        self.aggregator.add_entry(
            LogEntry(
                timestamp=datetime.now(),
                level=LogLevel.ERROR,
                message='Error message',
                source='app',
            )
        )

        filter_criteria = LogFilter(levels=[LogLevel.ERROR])
        results = self.aggregator.query(filter_criteria)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].level, LogLevel.ERROR)

    def test_count_by_level(self):
        """Test counting logs by level."""
        self.aggregator.add_entry(
            LogEntry(
                timestamp=datetime.now(),
                level=LogLevel.INFO,
                message='Info 1',
                source='app',
            )
        )
        self.aggregator.add_entry(
            LogEntry(
                timestamp=datetime.now(),
                level=LogLevel.INFO,
                message='Info 2',
                source='app',
            )
        )
        self.aggregator.add_entry(
            LogEntry(
                timestamp=datetime.now(),
                level=LogLevel.ERROR,
                message='Error 1',
                source='app',
            )
        )

        counts = self.aggregator.count_by_level()

        self.assertEqual(counts.get('INFO'), 2)
        self.assertEqual(counts.get('ERROR'), 1)


class OCIConfigTest(TestCase):
    """Tests for OCI configuration."""

    def test_config_to_dict(self):
        """Test converting config to dictionary."""
        config = OCIConfig(
            tenancy_ocid='ocid1.tenancy.oc1..test',
            user_ocid='ocid1.user.oc1..test',
            region=OCIRegion.US_ASHBURN,
            compartment_ocid='ocid1.compartment.oc1..test',
        )

        config_dict = config.to_dict()

        self.assertEqual(config_dict['tenancy_ocid'], 'ocid1.tenancy.oc1..test')
        self.assertEqual(config_dict['region'], 'us-ashburn-1')
        self.assertNotIn('fingerprint', config_dict)


class OCIObjectStorageAdapterTest(TestCase):
    """Tests for the OCI Object Storage adapter."""

    def setUp(self):
        """Set up test data."""
        self.config = OCIConfig(
            tenancy_ocid='ocid1.tenancy.oc1..test',
            user_ocid='ocid1.user.oc1..test',
            region=OCIRegion.US_ASHBURN,
            compartment_ocid='ocid1.compartment.oc1..test',
        )
        self.adapter = OCIObjectStorageAdapter(self.config, namespace='test-namespace')

    def test_connect(self):
        """Test connecting to Object Storage."""
        result = self.adapter.connect()
        self.assertTrue(result)
        self.assertTrue(self.adapter.is_connected)

    def test_health_check(self):
        """Test health check."""
        self.adapter.connect()
        health = self.adapter.health_check()

        self.assertEqual(health['service'], 'object_storage')
        self.assertTrue(health['connected'])

    def test_upload_file(self):
        """Test uploading a file."""
        self.adapter.connect()
        result = self.adapter.upload_file('bucket', 'test.txt', b'content')

        self.assertEqual(result['bucket'], 'bucket')
        self.assertEqual(result['object'], 'test.txt')
        self.assertEqual(result['size'], 7)


class HybridCloudManagerTest(TestCase):
    """Tests for the HybridCloudManager class."""

    def setUp(self):
        """Set up test data."""
        self.config = OCIConfig(
            tenancy_ocid='ocid1.tenancy.oc1..test',
            user_ocid='ocid1.user.oc1..test',
            region=OCIRegion.US_ASHBURN,
            compartment_ocid='ocid1.compartment.oc1..test',
        )
        self.manager = HybridCloudManager(self.config)

    def test_register_adapter(self):
        """Test registering an adapter."""
        adapter = OCIObjectStorageAdapter(self.config)
        self.manager.register_adapter('storage', adapter)

        retrieved = self.manager.get_adapter('storage')
        self.assertIsNotNone(retrieved)

    def test_connect_all_services(self):
        """Test connecting all services."""
        self.manager.register_adapter('storage', OCIObjectStorageAdapter(self.config))
        self.manager.register_adapter('monitoring', OCIMonitoringAdapter(self.config))

        results = self.manager.connect_all_services()

        self.assertTrue(results['storage'])
        self.assertTrue(results['monitoring'])

    def test_health_check_all(self):
        """Test health checking all services."""
        self.manager.register_adapter('storage', OCIObjectStorageAdapter(self.config))
        self.manager.connect_all_services()

        health = self.manager.health_check_all()

        self.assertIn('storage', health)
        self.assertTrue(health['storage']['connected'])


class DataInventoryItemTest(TestCase):
    """Tests for DataInventoryItem."""

    def test_to_dict(self):
        """Test converting to dictionary."""
        item = DataInventoryItem(
            name='part.Part',
            entity_type='table',
            record_count=1000,
            size_bytes=1024 * 1024,
            dependencies=['part.PartCategory'],
            priority=1,
        )

        item_dict = item.to_dict()

        self.assertEqual(item_dict['name'], 'part.Part')
        self.assertEqual(item_dict['record_count'], 1000)
        self.assertEqual(item_dict['size_mb'], 1.0)
        self.assertEqual(item_dict['priority'], 1)


class MigrationPlannerTest(TestCase):
    """Tests for the MigrationPlanner class."""

    def setUp(self):
        """Set up test data."""
        self.planner = MigrationPlanner()
        self.inventory = [
            DataInventoryItem(
                name='part.Part', entity_type='table', record_count=1000, priority=1
            ),
            DataInventoryItem(
                name='stock.StockItem',
                entity_type='table',
                record_count=5000,
                priority=2,
            ),
        ]

    def test_create_plan(self):
        """Test creating a migration plan."""
        plan = self.planner.create_plan(name='Test Migration', inventory=self.inventory)

        self.assertIsNotNone(plan.plan_id)
        self.assertEqual(plan.name, 'Test Migration')
        self.assertEqual(len(plan.inventory), 2)
        self.assertGreater(len(plan.tasks), 0)

    def test_plan_to_dict(self):
        """Test converting plan to dictionary."""
        plan = self.planner.create_plan(name='Test Migration', inventory=self.inventory)

        plan_dict = plan.to_dict()

        self.assertIn('plan_id', plan_dict)
        self.assertIn('progress', plan_dict)
        self.assertIn('inventory', plan_dict)
        self.assertIn('tasks', plan_dict)

    def test_update_task_status(self):
        """Test updating task status."""
        plan = self.planner.create_plan(name='Test Migration', inventory=self.inventory)

        task_id = plan.tasks[0].task_id
        result = self.planner.update_task_status(
            plan.plan_id, task_id, MigrationStatus.COMPLETED
        )

        self.assertTrue(result)
        self.assertEqual(plan.tasks[0].status, MigrationStatus.COMPLETED)


class MigrationReportTest(TestCase):
    """Tests for migration report generation."""

    def test_create_migration_report(self):
        """Test creating a migration report."""
        inventory = [
            DataInventoryItem(
                name='part.Part', entity_type='table', record_count=1000, priority=1
            )
        ]

        planner = MigrationPlanner()
        plan = planner.create_plan(name='Test Migration', inventory=inventory)

        report = create_migration_report(plan)

        self.assertIn('plan_id', report)
        self.assertIn('overall_progress', report)
        self.assertIn('phase_progress', report)
        self.assertIn('inventory_summary', report)
        self.assertIn('task_summary', report)
