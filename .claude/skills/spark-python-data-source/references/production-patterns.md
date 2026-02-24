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

Input validation and sanitization:

```python
import re
import ipaddress

class SecureDataSource:
    """Data source with security validation."""

    # Sensitive keys that should never be logged
    SENSITIVE_KEYS = {
        "password", "api_key", "client_secret", "token",
        "access_token", "refresh_token", "bearer_token"
    }

    def __init__(self, options):
        # Validate and sanitize options
        self._validate_options(options)
        self.options = options

        # Create sanitized version for logging
        self._safe_options = self._sanitize_for_logging(options)

    def _validate_options(self, options):
        """Comprehensive option validation."""
        # Validate required options
        required = ["host", "database", "table"]
        missing = [opt for opt in required if opt not in options]
        if missing:
            raise ValueError(f"Missing required options: {', '.join(missing)}")

        # Validate host (IP or hostname)
        self._validate_host(options["host"])

        # Validate port range
        if "port" in options:
            port = int(options["port"])
            if port < 1 or port > 65535:
                raise ValueError(f"Port must be 1-65535, got {port}")

        # Validate table name (prevent SQL injection)
        self._validate_identifier(options["table"], "table")

        # Validate numeric options
        if "batch_size" in options:
            batch_size = int(options["batch_size"])
            if batch_size < 1 or batch_size > 10000:
                raise ValueError(f"batch_size must be 1-10000, got {batch_size}")

    def _validate_host(self, host):
        """Validate host is valid IP or hostname."""
        try:
            # Try as IP address
            ipaddress.ip_address(host)
            return
        except ValueError:
            pass

        # Validate as hostname
        if not re.match(r'^[a-zA-Z0-9][a-zA-Z0-9-\.]*[a-zA-Z0-9]$', host):
            raise ValueError(f"Invalid host format: {host}")

    def _validate_identifier(self, identifier, name):
        """Validate SQL identifier (table, column name)."""
        # Prevent SQL injection
        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', identifier):
            raise ValueError(
                f"Invalid {name} identifier: {identifier}. "
                f"Must contain only letters, numbers, and underscores, "
                f"and start with a letter or underscore."
            )

    def _sanitize_for_logging(self, options):
        """Mask sensitive values for logging."""
        safe = {}
        for key, value in options.items():
            if key.lower() in self.SENSITIVE_KEYS:
                safe[key] = "***REDACTED***"
            else:
                safe[key] = value
        return safe

    def __repr__(self):
        return f"SecureDataSource({self._safe_options})"
```

## Secrets Management

Load credentials from secure storage:

```python
def load_secrets_from_databricks(scope, keys):
    """Load secrets from Databricks secrets."""
    try:
        from pyspark.dbutils import DBUtils
        from pyspark.sql import SparkSession

        spark = SparkSession.getActiveSession()
        if not spark:
            raise ValueError("No active Spark session")

        dbutils = DBUtils(spark)
        secrets = {}

        for key in keys:
            try:
                secrets[key] = dbutils.secrets.get(scope=scope, key=key)
            except Exception as e:
                raise ValueError(f"Failed to load secret '{key}' from scope '{scope}': {e}")

        return secrets

    except Exception as e:
        raise ValueError(f"Failed to access Databricks secrets: {e}")

class SecureCredentialLoader:
    """Load credentials securely."""

    @staticmethod
    def load_credentials(options):
        """Load credentials from secure storage."""
        # Priority 1: Databricks secrets
        if "secret_scope" in options:
            secret_keys = [
                "username", "password", "api_key", "client_secret"
            ]
            secrets = load_secrets_from_databricks(
                options["secret_scope"],
                secret_keys
            )
            options.update(secrets)

        # Priority 2: Environment variables
        elif options.get("use_env_vars", "false").lower() == "true":
            import os
            options["username"] = os.environ.get("DB_USERNAME")
            options["password"] = os.environ.get("DB_PASSWORD")

        return options
```

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
