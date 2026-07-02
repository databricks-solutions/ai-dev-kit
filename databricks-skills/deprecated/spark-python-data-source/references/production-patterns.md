# Production Patterns

Observability, security, validation, and operational best practices.

## Observability and Metrics

Track operation metrics for monitoring:

```python
class ObservableWriter:
    """Writer with comprehensive metrics tracking."""

    def write(self, iterator):
        """Write with metrics collection."""
        from pyspark import TaskContext
        from datetime import datetime
        import time

        context = TaskContext.get()
        partition_id = context.partitionId()

        metrics = {
            "partition_id": partition_id,
            "rows_processed": 0,
            "rows_failed": 0,
            "bytes_sent": 0,
            "batches_sent": 0,
            "retry_count": 0,
            "start_time": time.time(),
            "errors": []
        }

        try:
            for row in iterator:
                try:
                    size = self._send_row(row)
                    metrics["rows_processed"] += 1
                    metrics["bytes_sent"] += size

                except Exception as e:
                    metrics["rows_failed"] += 1
                    metrics["errors"].append({
                        "type": type(e).__name__,
                        "message": str(e)
                    })

                    if not self.continue_on_error:
                        raise

            metrics["duration_seconds"] = time.time() - metrics["start_time"]
            self._report_metrics(metrics)

            return SimpleCommitMessage(
                partition_id=partition_id,
                count=metrics["rows_processed"]
            )

        except Exception as e:
            metrics["fatal_error"] = str(e)
            self._report_failure(partition_id, metrics)
            raise

    def _report_metrics(self, metrics):
        """Report metrics to monitoring system."""
        # Example: CloudWatch, Prometheus, Databricks metrics
        print(f"METRICS: {json.dumps(metrics)}")

        # Calculate derived metrics
        if metrics["duration_seconds"] > 0:
            throughput = metrics["rows_processed"] / metrics["duration_seconds"]
            print(f"Throughput: {throughput:.2f} rows/second")
```

## Logging Best Practices

Structured logging for production debugging:

```python
import logging
import json

# Configure structured logging
logging.basicConfig(
    format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class StructuredLogger:
    """Logger with structured output."""

    @staticmethod
    def log_operation(operation, context, **kwargs):
        """Log operation with structured context."""
        log_entry = {
            "operation": operation,
            "context": context,
            **kwargs
        }
        logger.info(json.dumps(log_entry))

    @staticmethod
    def log_error(operation, error, context):
        """Log error with context."""
        log_entry = {
            "operation": operation,
            "error_type": type(error).__name__,
            "error_message": str(error),
            "context": context
        }
        logger.error(json.dumps(log_entry))

class LoggingWriter:
    def write(self, iterator):
        """Write with structured logging."""
        from pyspark import TaskContext

        context = TaskContext.get()
        partition_id = context.partitionId()

        StructuredLogger.log_operation(
            "write_start",
            {"partition_id": partition_id}
        )

        try:
            count = 0
            for row in iterator:
                self._send_data(row)
                count += 1

            StructuredLogger.log_operation(
                "write_complete",
                {"partition_id": partition_id},
                rows_written=count
            )

        except Exception as e:
            StructuredLogger.log_error(
                "write_failed",
                e,
                {"partition_id": partition_id}
            )
            raise
```

## Security Validation

Input validation and sanitization for production data sources:

```python
import re
import ipaddress

class SecureDataSource:
    """Data source with input validation."""

    def __init__(self, options):
        self._validate_options(options)
        self.options = options

    def _validate_options(self, options):
        """Validate options at system boundary."""
        required = ["host", "database", "table"]
        missing = [opt for opt in required if opt not in options]
        if missing:
            raise ValueError(f"Missing required options: {', '.join(missing)}")

        self._validate_host(options["host"])

        if "port" in options:
            port = int(options["port"])
            if port < 1 or port > 65535:
                raise ValueError(f"Port must be 1-65535, got {port}")

        self._validate_identifier(options["table"], "table")

    def _validate_host(self, host):
        """Validate host is valid IP or hostname."""
        try:
            ipaddress.ip_address(host)
            return
        except ValueError:
            pass
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-\.]*[a-zA-Z0-9]$', host):
            raise ValueError(f"Invalid host format: {host}")

    def _validate_identifier(self, identifier, name):
        """Validate SQL identifier to prevent injection."""
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
            raise ValueError(
                f"Invalid {name} identifier: {identifier}. "
                f"Must contain only letters, numbers, and underscores."
            )
```

For credential sanitization in logs and secrets management, see [authentication-patterns.md](authentication-patterns.md) — the "Security Best Practices" and "Use Secrets Management" sections.

## Configuration Validation

Validate configuration before execution:

```python
class ConfigValidator:
    """Validate data source configuration."""

    VALID_CONSISTENCY_LEVELS = {
        "ONE", "TWO", "THREE", "QUORUM", "ALL",
        "LOCAL_QUORUM", "EACH_QUORUM", "LOCAL_ONE"
    }

    VALID_COMPRESSION = {
        "none", "gzip", "snappy", "lz4", "zstd"
    }

    @classmethod
    def validate(cls, options):
        """Validate all configuration options."""
        errors = []

        # Validate consistency level
        if "consistency" in options:
            consistency = options["consistency"].upper()
            if consistency not in cls.VALID_CONSISTENCY_LEVELS:
                errors.append(
                    f"Invalid consistency level '{consistency}'. "
                    f"Valid: {', '.join(cls.VALID_CONSISTENCY_LEVELS)}"
                )

        # Validate compression
        if "compression" in options:
            compression = options["compression"].lower()
            if compression not in cls.VALID_COMPRESSION:
                errors.append(
                    f"Invalid compression '{compression}'. "
                    f"Valid: {', '.join(cls.VALID_COMPRESSION)}"
                )

        # Validate numeric ranges
        if "timeout" in options:
            timeout = int(options["timeout"])
            if timeout < 0 or timeout > 300:
                errors.append(f"timeout must be 0-300 seconds, got {timeout}")

        if "batch_size" in options:
            batch_size = int(options["batch_size"])
            if batch_size < 1 or batch_size > 10000:
                errors.append(f"batch_size must be 1-10000, got {batch_size}")

        # Validate dependent options
        if options.get("ssl_enabled", "false").lower() == "true":
            if "ssl_ca_cert" not in options:
                errors.append("ssl_ca_cert required when ssl_enabled=true")

        if errors:
            raise ValueError("Configuration errors:\n" + "\n".join(f"- {e}" for e in errors))
```

## Resource Cleanup

Ensure proper resource cleanup:

```python
class ManagedResourceWriter:
    """Writer with guaranteed resource cleanup."""

    def __init__(self, options):
        self.options = options
        self._connection = None
        self._session = None

    def _get_connection(self):
        """Lazy connection initialization."""
        if self._connection is None:
            self._connection = self._create_connection()
        return self._connection

    def write(self, iterator):
        """Write with guaranteed cleanup."""
        try:
            connection = self._get_connection()

            for row in iterator:
                self._send_data(connection, row)

        finally:
            # Always cleanup resources
            self._cleanup()

    def _cleanup(self):
        """Clean up resources."""
        if self._session:
            try:
                self._session.close()
            except Exception as e:
                logger.warning(f"Error closing session: {e}")
            finally:
                self._session = None

        if self._connection:
            try:
                self._connection.close()
            except Exception as e:
                logger.warning(f"Error closing connection: {e}")
            finally:
                self._connection = None

    def __del__(self):
        """Cleanup on garbage collection."""
        self._cleanup()
```

## Health Checks

Monitor system health:

```python
class HealthCheckMixin:
    """Mixin for health check functionality."""

    def check_health(self):
        """Perform health check before operations."""
        checks = {
            "connection": self._check_connection(),
            "authentication": self._check_authentication(),
            "rate_limit": self._check_rate_limit(),
            "disk_space": self._check_disk_space()
        }

        failed = [name for name, passed in checks.items() if not passed]

        if failed:
            raise Exception(f"Health check failed: {', '.join(failed)}")

        return checks

    def _check_connection(self):
        """Check connection to external system."""
        try:
            self._test_connection()
            return True
        except Exception as e:
            logger.error(f"Connection check failed: {e}")
            return False

    def _check_authentication(self):
        """Check authentication is valid."""
        try:
            self._verify_credentials()
            return True
        except Exception as e:
            logger.error(f"Authentication check failed: {e}")
            return False

    def _check_rate_limit(self):
        """Check if under rate limits."""
        # Check current rate usage
        current_rate = self._get_current_rate()
        limit = self._get_rate_limit()

        return current_rate < limit * 0.8  # 80% threshold

    def _check_disk_space(self):
        """Check available disk space."""
        import shutil

        usage = shutil.disk_usage("/")
        free_percent = (usage.free / usage.total) * 100

        return free_percent > 10  # 10% minimum
```

## Operational Best Practices

1. **Monitoring**: Track throughput, latency, error rates
2. **Logging**: Use structured logging with correlation IDs
3. **Secrets**: Never log sensitive values, use secrets management
4. **Validation**: Validate all inputs to prevent injection attacks
5. **Resource Cleanup**: Always close connections and clean up resources
6. **Health Checks**: Verify system health before operations
7. **Rate Limiting**: Respect API rate limits with backoff
8. **Alerting**: Set up alerts for error rates and latency
9. **Documentation**: Document all configuration options
10. **Version Control**: Tag releases and maintain changelog
