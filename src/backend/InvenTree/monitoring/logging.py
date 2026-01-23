"""Log aggregation and analysis utilities.

This module provides utilities for collecting, parsing, and analyzing logs
from multiple system components.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

import structlog

logger = structlog.get_logger(__name__)


class LogLevel(Enum):
    """Log level enumeration."""

    DEBUG = 'DEBUG'
    INFO = 'INFO'
    WARNING = 'WARNING'
    ERROR = 'ERROR'
    CRITICAL = 'CRITICAL'


@dataclass
class LogEntry:
    """Represents a parsed log entry.

    Attributes:
        timestamp: When the log was created
        level: Log level
        message: Log message
        source: Source of the log (e.g., module name)
        extra: Additional structured data
    """

    timestamp: datetime
    level: LogLevel
    message: str
    source: str = ''
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary format.

        Returns:
            Dictionary representation of the log entry
        """
        return {
            'timestamp': self.timestamp.isoformat(),
            'level': self.level.value,
            'message': self.message,
            'source': self.source,
            'extra': self.extra,
        }


@dataclass
class LogFilter:
    """Filter criteria for log queries.

    Attributes:
        start_time: Filter logs after this time
        end_time: Filter logs before this time
        levels: Filter by log levels
        sources: Filter by log sources
        message_pattern: Regex pattern to match messages
        extra_filters: Key-value filters for extra data
    """

    start_time: datetime | None = None
    end_time: datetime | None = None
    levels: list[LogLevel] | None = None
    sources: list[str] | None = None
    message_pattern: str | None = None
    extra_filters: dict[str, Any] | None = None


class LogParser:
    """Parser for various log formats.

    This class provides methods for parsing logs from different formats
    including JSON, common log format, and custom patterns.

    Example:
        parser = LogParser()
        entry = parser.parse_json_log('{"timestamp": "2026-01-23T12:00:00", "level": "INFO", "message": "Test"}')
    """

    COMMON_LOG_PATTERN = re.compile(
        r'(?P<timestamp>\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?)\s+'
        r'(?P<level>DEBUG|INFO|WARNING|ERROR|CRITICAL)\s+'
        r'(?:\[(?P<source>[^\]]+)\]\s+)?'
        r'(?P<message>.*)'
    )

    def __init__(self):
        """Initialize the log parser."""
        self._custom_patterns: dict[str, re.Pattern] = {}

    def register_pattern(self, name: str, pattern: str) -> None:
        """Register a custom log pattern.

        Args:
            name: Name for the pattern
            pattern: Regex pattern with named groups
        """
        self._custom_patterns[name] = re.compile(pattern)

    def parse_json_log(self, line: str) -> LogEntry | None:
        """Parse a JSON-formatted log line.

        Args:
            line: The log line to parse

        Returns:
            LogEntry or None if parsing fails
        """
        try:
            data = json.loads(line)

            timestamp_str = data.get('timestamp', data.get('time', ''))
            if isinstance(timestamp_str, str):
                timestamp = self._parse_timestamp(timestamp_str)
            else:
                timestamp = datetime.now()

            level_str = data.get('level', data.get('severity', 'INFO')).upper()
            level = (
                LogLevel[level_str]
                if level_str in LogLevel.__members__
                else LogLevel.INFO
            )

            message = data.get('message', data.get('msg', ''))
            source = data.get('source', data.get('logger', data.get('name', '')))

            extra = {
                k: v
                for k, v in data.items()
                if k
                not in (
                    'timestamp',
                    'time',
                    'level',
                    'severity',
                    'message',
                    'msg',
                    'source',
                    'logger',
                    'name',
                )
            }

            return LogEntry(
                timestamp=timestamp,
                level=level,
                message=message,
                source=source,
                extra=extra,
            )
        except (json.JSONDecodeError, KeyError, ValueError):
            return None

    def parse_common_log(self, line: str) -> LogEntry | None:
        """Parse a common log format line.

        Args:
            line: The log line to parse

        Returns:
            LogEntry or None if parsing fails
        """
        match = self.COMMON_LOG_PATTERN.match(line)
        if not match:
            return None

        groups = match.groupdict()

        timestamp = self._parse_timestamp(groups['timestamp'])
        level = LogLevel[groups['level']]
        message = groups['message']
        source = groups.get('source', '')

        return LogEntry(
            timestamp=timestamp, level=level, message=message, source=source
        )

    def parse_with_pattern(self, name: str, line: str) -> LogEntry | None:
        """Parse a log line using a registered custom pattern.

        Args:
            name: Name of the registered pattern
            line: The log line to parse

        Returns:
            LogEntry or None if parsing fails
        """
        pattern = self._custom_patterns.get(name)
        if not pattern:
            return None

        match = pattern.match(line)
        if not match:
            return None

        groups = match.groupdict()

        timestamp = self._parse_timestamp(groups.get('timestamp', ''))
        level_str = groups.get('level', 'INFO').upper()
        level = (
            LogLevel[level_str] if level_str in LogLevel.__members__ else LogLevel.INFO
        )
        message = groups.get('message', '')
        source = groups.get('source', '')

        extra = {
            k: v
            for k, v in groups.items()
            if k not in ('timestamp', 'level', 'message', 'source')
        }

        return LogEntry(
            timestamp=timestamp,
            level=level,
            message=message,
            source=source,
            extra=extra,
        )

    def _parse_timestamp(self, timestamp_str: str) -> datetime:
        """Parse a timestamp string.

        Args:
            timestamp_str: The timestamp string

        Returns:
            Parsed datetime
        """
        formats = [
            '%Y-%m-%dT%H:%M:%S.%fZ',
            '%Y-%m-%dT%H:%M:%SZ',
            '%Y-%m-%dT%H:%M:%S.%f',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S.%f',
            '%Y-%m-%d %H:%M:%S',
        ]

        for fmt in formats:
            try:
                return datetime.strptime(
                    timestamp_str.replace('+00:00', 'Z').rstrip('Z') + 'Z',
                    fmt.replace('Z', '') + 'Z' if 'Z' in fmt else fmt,
                )
            except ValueError:
                continue

        for fmt in formats:
            try:
                return datetime.strptime(
                    timestamp_str.split('+')[0].split('-')[0]
                    if '+' in timestamp_str or timestamp_str.count('-') > 2
                    else timestamp_str,
                    fmt.replace('Z', ''),
                )
            except ValueError:
                continue

        return datetime.now()


class LogAggregator:
    """Aggregator for collecting and querying logs.

    This class provides methods for collecting logs from multiple sources
    and querying them with filters.

    Example:
        aggregator = LogAggregator()
        aggregator.add_entry(LogEntry(...))
        results = aggregator.query(LogFilter(levels=[LogLevel.ERROR]))
    """

    def __init__(self, max_entries: int = 10000):
        """Initialize the log aggregator.

        Args:
            max_entries: Maximum number of entries to keep in memory
        """
        self._entries: list[LogEntry] = []
        self._max_entries = max_entries
        self._parser = LogParser()

    def add_entry(self, entry: LogEntry) -> None:
        """Add a log entry.

        Args:
            entry: The log entry to add
        """
        self._entries.append(entry)

        if len(self._entries) > self._max_entries:
            self._entries = self._entries[-self._max_entries :]

    def add_raw_log(self, line: str, format_type: str = 'auto') -> bool:
        """Add a raw log line, parsing it automatically.

        Args:
            line: The raw log line
            format_type: Format type ('json', 'common', 'auto')

        Returns:
            True if the log was parsed and added successfully
        """
        entry = None

        if format_type == 'json' or (
            format_type == 'auto' and line.strip().startswith('{')
        ):
            entry = self._parser.parse_json_log(line)
        elif format_type == 'common' or format_type == 'auto':
            entry = self._parser.parse_common_log(line)

        if entry:
            self.add_entry(entry)
            return True
        return False

    def query(self, filter_criteria: LogFilter | None = None) -> list[LogEntry]:
        """Query logs with optional filters.

        Args:
            filter_criteria: Optional filter criteria

        Returns:
            List of matching log entries
        """
        if not filter_criteria:
            return list(self._entries)

        results = []
        for entry in self._entries:
            if self._matches_filter(entry, filter_criteria):
                results.append(entry)

        return results

    def count_by_level(
        self, filter_criteria: LogFilter | None = None
    ) -> dict[str, int]:
        """Count logs by level.

        Args:
            filter_criteria: Optional filter criteria

        Returns:
            Dictionary mapping level names to counts
        """
        entries = self.query(filter_criteria)
        counts: dict[str, int] = {}

        for entry in entries:
            level_name = entry.level.value
            counts[level_name] = counts.get(level_name, 0) + 1

        return counts

    def count_by_source(
        self, filter_criteria: LogFilter | None = None
    ) -> dict[str, int]:
        """Count logs by source.

        Args:
            filter_criteria: Optional filter criteria

        Returns:
            Dictionary mapping source names to counts
        """
        entries = self.query(filter_criteria)
        counts: dict[str, int] = {}

        for entry in entries:
            source = entry.source or 'unknown'
            counts[source] = counts.get(source, 0) + 1

        return counts

    def get_error_summary(
        self, filter_criteria: LogFilter | None = None
    ) -> list[dict[str, Any]]:
        """Get a summary of error logs.

        Args:
            filter_criteria: Optional filter criteria

        Returns:
            List of error summaries with counts
        """
        if filter_criteria:
            filter_criteria.levels = [LogLevel.ERROR, LogLevel.CRITICAL]
        else:
            filter_criteria = LogFilter(levels=[LogLevel.ERROR, LogLevel.CRITICAL])

        entries = self.query(filter_criteria)

        error_counts: dict[str, dict[str, Any]] = {}
        for entry in entries:
            key = f'{entry.source}:{entry.message[:100]}'
            if key not in error_counts:
                error_counts[key] = {
                    'source': entry.source,
                    'message': entry.message[:200],
                    'level': entry.level.value,
                    'count': 0,
                    'first_seen': entry.timestamp,
                    'last_seen': entry.timestamp,
                }
            error_counts[key]['count'] += 1
            if entry.timestamp < error_counts[key]['first_seen']:
                error_counts[key]['first_seen'] = entry.timestamp
            if entry.timestamp > error_counts[key]['last_seen']:
                error_counts[key]['last_seen'] = entry.timestamp

        summaries = list(error_counts.values())
        summaries.sort(key=lambda x: x['count'], reverse=True)

        for summary in summaries:
            summary['first_seen'] = summary['first_seen'].isoformat()
            summary['last_seen'] = summary['last_seen'].isoformat()

        return summaries

    def clear(self) -> None:
        """Clear all log entries."""
        self._entries.clear()

    def _matches_filter(self, entry: LogEntry, filter_criteria: LogFilter) -> bool:
        """Check if an entry matches filter criteria.

        Args:
            entry: The log entry
            filter_criteria: The filter criteria

        Returns:
            True if the entry matches
        """
        if filter_criteria.start_time and entry.timestamp < filter_criteria.start_time:
            return False

        if filter_criteria.end_time and entry.timestamp > filter_criteria.end_time:
            return False

        if filter_criteria.levels and entry.level not in filter_criteria.levels:
            return False

        if filter_criteria.sources and entry.source not in filter_criteria.sources:
            return False

        if filter_criteria.message_pattern:
            if not re.search(filter_criteria.message_pattern, entry.message):
                return False

        if filter_criteria.extra_filters:
            for key, value in filter_criteria.extra_filters.items():
                if entry.extra.get(key) != value:
                    return False

        return True


# Global log aggregator instance
_log_aggregator = LogAggregator()


def get_log_aggregator() -> LogAggregator:
    """Get the global log aggregator instance.

    Returns:
        The global LogAggregator instance
    """
    return _log_aggregator


class StructuredLogHandler(logging.Handler):
    """Logging handler that sends logs to the aggregator.

    This handler can be added to Python's logging system to automatically
    capture logs into the aggregator.

    Example:
        handler = StructuredLogHandler()
        logging.getLogger().addHandler(handler)
    """

    def __init__(self, aggregator: LogAggregator | None = None):
        """Initialize the handler.

        Args:
            aggregator: Optional aggregator (uses global if not provided)
        """
        super().__init__()
        self.aggregator = aggregator or get_log_aggregator()

    def emit(self, record: logging.LogRecord) -> None:
        """Emit a log record to the aggregator.

        Args:
            record: The log record
        """
        try:
            level_map = {
                logging.DEBUG: LogLevel.DEBUG,
                logging.INFO: LogLevel.INFO,
                logging.WARNING: LogLevel.WARNING,
                logging.ERROR: LogLevel.ERROR,
                logging.CRITICAL: LogLevel.CRITICAL,
            }

            entry = LogEntry(
                timestamp=datetime.fromtimestamp(record.created),
                level=level_map.get(record.levelno, LogLevel.INFO),
                message=self.format(record),
                source=record.name,
                extra={
                    'pathname': record.pathname,
                    'lineno': record.lineno,
                    'funcName': record.funcName,
                },
            )

            self.aggregator.add_entry(entry)
        except Exception:
            self.handleError(record)
