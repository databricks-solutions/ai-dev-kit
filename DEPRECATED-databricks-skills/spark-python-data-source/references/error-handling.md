# Error Handling and Resilience

Patterns for retries, circuit breakers, and graceful degradation.

## Exponential Backoff

Retry with exponential backoff for transient failures:

```python
def write_with_retry(self, iterator):
    """Write with exponential backoff."""
    import time

    max_retries = int(self.options.get("max_retries", "5"))
    initial_backoff = float(self.options.get("initial_backoff", "1.0"))
    max_backoff = float(self.options.get("max_backoff", "60.0"))

    for row in iterator:
        retry_count = 0

        while retry_count <= max_retries:
            try:
                self._send_data(row)
                break  # Success

            except Exception as e:
                if not self._is_retryable_error(e):
                    # Non-retryable error - fail immediately
                    raise

                if retry_count >= max_retries:
                    # Max retries exceeded
                    raise Exception(f"Max retries ({max_retries}) exceeded: {e}")

                # Calculate backoff with exponential growth
                backoff = min(initial_backoff * (2 ** retry_count), max_backoff)
                time.sleep(backoff)
                retry_count += 1

def _is_retryable_error(self, error):
    """Determine if error is retryable."""
    from requests.exceptions import RequestException, Timeout, ConnectionError

    # Network errors are retryable
    if isinstance(error, (Timeout, ConnectionError)):
        return True

    # HTTP errors
    if hasattr(error, 'response') and error.response:
        status_code = error.response.status_code
        # Retry on 429 (throttling) and 5xx (server errors)
        if status_code == 429 or 500 <= status_code < 600:
            return True

    return False
```

## Retry with Throttling Respect

Handle API rate limiting with Retry-After header:

```python
def write_with_throttling(self, iterator):
    """Write with respect for rate limits."""
    import time
    from requests.exceptions import HTTPError

    for row in iterator:
        max_attempts = 5
        attempt = 0

        while attempt < max_attempts:
            try:
                self._send_data(row)
                break

            except HTTPError as e:
                if e.response.status_code == 429:
                    # Throttled - respect Retry-After header
                    retry_after = self._get_retry_after(e.response)
                    time.sleep(retry_after)
                    attempt += 1
                else:
                    raise

        if attempt >= max_attempts:
            raise Exception("Max retry attempts for throttling exceeded")

def _get_retry_after(self, response):
    """Extract retry delay from Retry-After header."""
    retry_after = response.headers.get("Retry-After")

    if retry_after:
        try:
            # Try as seconds (int)
            return int(retry_after)
        except ValueError:
            # Try as HTTP date
            from datetime import datetime
            try:
                retry_date = datetime.strptime(retry_after, "%a, %d %b %Y %H:%M:%S GMT")
                delay = (retry_date - datetime.utcnow()).total_seconds()
                return max(0, delay)
            except ValueError:
                pass

    # Default fallback
    return 1.0
```

## Circuit Breaker

Prevent cascading failures with circuit breaker pattern:

```python
class CircuitBreaker:
    """Circuit breaker to prevent cascading failures."""

    def __init__(self, threshold=10, timeout=300):
        self.threshold = threshold  # failures before opening
        self.timeout = timeout  # seconds before trying again
        self.consecutive_failures = 0
        self.circuit_open = False
        self.circuit_open_until = None

    def record_success(self):
        """Record successful operation."""
        self.consecutive_failures = 0

    def record_failure(self):
        """Record failed operation."""
        from datetime import datetime, timedelta

        self.consecutive_failures += 1

        if self.consecutive_failures >= self.threshold:
            self.circuit_open = True
            self.circuit_open_until = datetime.now() + timedelta(seconds=self.timeout)

    def is_open(self):
        """Check if circuit is open."""
        from datetime import datetime

        if self.circuit_open:
            if datetime.now() >= self.circuit_open_until:
                # Timeout expired - try again
                self.circuit_open = False
                self.consecutive_failures = 0
                return False
            return True

        return False

class ResilientWriter:
    def __init__(self, options):
        self.circuit_breaker = CircuitBreaker(
            threshold=int(options.get("circuit_breaker_threshold", "10")),
            timeout=int(options.get("circuit_breaker_timeout", "300"))
        )

    def write(self, iterator):
        """Write with circuit breaker protection."""
        for row in iterator:
            if self.circuit_breaker.is_open():
                raise Exception("Circuit breaker open - too many failures")

            try:
                self._send_data(row)
                self.circuit_breaker.record_success()

            except Exception as e:
                self.circuit_breaker.record_failure()
                raise
```

## Graceful Degradation

Handle partial failures and fallback strategies:

```python
def read_with_fallback(self, partition):
    """Read with fallback to secondary sources."""
    try:
        # Try primary source
        yield from self._read_primary(partition)

    except ConnectionError as e:
        # Primary failed - try secondary
        if self.secondary_endpoint:
            print(f"Primary failed, using secondary: {e}")
            yield from self._read_secondary(partition)
        else:
            raise

    except TimeoutError as e:
        # Timeout - try with smaller partitions
        if partition.can_subdivide():
            print(f"Timeout, subdividing: {e}")
            for sub_partition in partition.subdivide():
                yield from self.read(sub_partition)
        else:
            raise

    except PartialResultError as e:
        # Partial results - log warning and continue
        print(f"Warning: Partial results for partition {partition.id}: {e}")
        yield from e.partial_results
```

## Bulk Operation Error Handling

Handle errors in bulk operations:

```python
def write_batch_with_error_handling(self, iterator):
    """Write in batches with individual error tracking."""
    from cassandra.concurrent import execute_concurrent_with_args

    batch_size = int(self.options.get("batch_size", "1000"))
    fail_on_first_error = self.options.get("fail_on_first_error", "true").lower() == "true"

    batch_params = []
    failed_rows = []

    for row in iterator:
        batch_params.append(self._row_to_params(row))

        if len(batch_params) >= batch_size:
            # Execute batch
            results = execute_concurrent_with_args(
                self.session,
                self.prepared_statement,
                batch_params,
                concurrency=100,
                raise_on_first_error=fail_on_first_error
            )

            # Check for failures
            for success, result_or_error in results:
                if not success:
                    failed_rows.append((batch_params[i], result_or_error))

            batch_params = []

    # Final batch
    if batch_params:
        results = execute_concurrent_with_args(
            self.session,
            self.prepared_statement,
            batch_params,
            concurrency=100,
            raise_on_first_error=fail_on_first_error
        )

        for i, (success, result_or_error) in enumerate(results):
            if not success:
                failed_rows.append((batch_params[i], result_or_error))

    # Handle failed rows
    if failed_rows:
        if fail_on_first_error:
            raise Exception(f"{len(failed_rows)} rows failed to write")
        else:
            # Log failures but continue
            print(f"Warning: {len(failed_rows)} rows failed to write")
```

## Dead Letter Queue

Store failed records for later processing:

```python
class DeadLetterQueueWriter:
    """Writer with dead letter queue for failed records."""

    def __init__(self, options):
        self.dlq_path = options.get("dlq_path")
        self.dlq_enabled = bool(self.dlq_path)

    def write(self, iterator):
        """Write with DLQ support."""
        from datetime import datetime
        import json

        successful = 0
        failed = 0

        for row in iterator:
            try:
                self._send_data(row)
                successful += 1

            except Exception as e:
                failed += 1

                if self.dlq_enabled:
                    self._write_to_dlq(row, e)
                else:
                    raise

        return {
            "successful": successful,
            "failed": failed
        }

    def _write_to_dlq(self, row, error):
        """Write failed record to dead letter queue."""
        from datetime import datetime
        import json
        import os

        dlq_record = {
            "timestamp": datetime.now().isoformat(),
            "error": str(error),
            "error_type": type(error).__name__,
            "row": row.asDict()
        }

        # Append to DLQ file
        os.makedirs(os.path.dirname(self.dlq_path), exist_ok=True)

        with open(self.dlq_path, 'a') as f:
            f.write(json.dumps(dlq_record) + '\n')
```

## Timeout Handling

Enforce operation timeouts:

```python
import signal
from contextlib import contextmanager

class TimeoutError(Exception):
    pass

def timeout_handler(signum, frame):
    raise TimeoutError("Operation timed out")

@contextmanager
def timeout(seconds):
    """Context manager for operation timeout."""
    signal.signal(signal.SIGALRM, timeout_handler)
    signal.alarm(seconds)
    try:
        yield
    finally:
        signal.alarm(0)

class TimeoutWriter:
    def write(self, iterator):
        """Write with per-row timeout."""
        timeout_seconds = int(self.options.get("write_timeout", "30"))

        for row in iterator:
            try:
                with timeout(timeout_seconds):
                    self._send_data(row)

            except TimeoutError:
                print(f"Write timeout after {timeout_seconds}s")
                raise
```

## Error Aggregation

Collect and report errors systematically:

```python
class ErrorAggregator:
    """Aggregate errors for batch reporting."""

    def __init__(self):
        self.errors = []
        self.error_counts = {}

    def record_error(self, error, context=None):
        """Record an error with context."""
        error_type = type(error).__name__
        error_msg = str(error)

        self.errors.append({
            "type": error_type,
            "message": error_msg,
            "context": context
        })

        # Count by type
        self.error_counts[error_type] = self.error_counts.get(error_type, 0) + 1

    def get_summary(self):
        """Get error summary."""
        return {
            "total_errors": len(self.errors),
            "by_type": self.error_counts,
            "sample_errors": self.errors[:10]  # First 10
        }

class ErrorAwareWriter:
    def write(self, iterator):
        """Write with error aggregation."""
        aggregator = ErrorAggregator()
        successful = 0

        for i, row in enumerate(iterator):
            try:
                self._send_data(row)
                successful += 1

            except Exception as e:
                aggregator.record_error(e, context={"row_index": i})

        # Report summary
        if aggregator.errors:
            summary = aggregator.get_summary()
            print(f"Completed with {successful} success, {summary['total_errors']} errors")
            print(f"Error breakdown: {summary['by_type']}")

            if summary['total_errors'] > successful:
                raise Exception(f"Too many errors: {summary}")
```

## Best Practices

1. **Retry Only Transient Errors**: Don't retry client errors (4xx)
2. **Respect Rate Limits**: Use Retry-After headers and backoff
3. **Circuit Breakers**: Prevent cascading failures in distributed systems
4. **Timeout Operations**: Set reasonable timeouts to prevent hangs
5. **Log Errors**: Capture error context for debugging
6. **Dead Letter Queues**: Store failed records for later analysis
7. **Monitor Failure Rates**: Alert on anomalous error rates
8. **Graceful Degradation**: Continue with partial results when appropriate
