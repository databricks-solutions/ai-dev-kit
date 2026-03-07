# Type Conversion

Bidirectional mapping between Spark types and external system types.

## Spark to External System

Convert Spark/Python values to external system types:

```python
def convert_spark_to_external(value, external_type):
    """Convert Spark/Python value to external system type."""
    if value is None:
        return None

    external_type_lower = external_type.lower()

    # UUID conversion
    if "uuid" in external_type_lower:
        import uuid
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))

    # Timestamp conversion
    if "timestamp" in external_type_lower:
        from datetime import datetime
        if isinstance(value, datetime):
            return value
        if isinstance(value, str):
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        if isinstance(value, (int, float)):
            return datetime.fromtimestamp(value)

    # IP address conversion
    if "inet" in external_type_lower:
        import ipaddress
        if isinstance(value, (ipaddress.IPv4Address, ipaddress.IPv6Address)):
            return value
        return ipaddress.ip_address(str(value))

    # Decimal conversion
    if "decimal" in external_type_lower:
        from decimal import Decimal
        if isinstance(value, Decimal):
            return value
        return Decimal(str(value))

    # Collections
    if "list" in external_type_lower or "set" in external_type_lower:
        if not isinstance(value, (list, set)):
            raise ValueError(f"Expected list/set, got {type(value)}")
        return list(value)

    if "map" in external_type_lower:
        if not isinstance(value, dict):
            raise ValueError(f"Expected dict, got {type(value)}")
        return value

    # Numeric types
    if "int" in external_type_lower:
        return int(value)
    if "float" in external_type_lower or "double" in external_type_lower:
        return float(value)

    # Boolean
    if "bool" in external_type_lower:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes")
        return bool(value)

    # Default: return as-is
    return value
```

## External System to Spark

Convert external values to Spark types:

```python
def convert_external_to_spark(value, spark_type):
    """Convert external system value to Spark type."""
    from pyspark.sql.types import (
        StringType, IntegerType, LongType, FloatType, DoubleType,
        BooleanType, TimestampType, DateType
    )
    from datetime import datetime, date

    if value is None:
        return None

    try:
        if isinstance(spark_type, StringType):
            return str(value)

        elif isinstance(spark_type, BooleanType):
            if isinstance(value, bool):
                return value
            if isinstance(value, str):
                return value.lower() in ("true", "1", "yes")
            return bool(value)

        elif isinstance(spark_type, (IntegerType, LongType)):
            if isinstance(value, bool):
                raise ValueError("Cannot convert boolean to integer")
            return int(value)

        elif isinstance(spark_type, (FloatType, DoubleType)):
            if isinstance(value, bool):
                raise ValueError("Cannot convert boolean to float")
            return float(value)

        elif isinstance(spark_type, TimestampType):
            if isinstance(value, datetime):
                return value
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00"))
            raise ValueError(f"Cannot convert {type(value)} to timestamp")

        elif isinstance(spark_type, DateType):
            if isinstance(value, date) and not isinstance(value, datetime):
                return value
            if isinstance(value, datetime):
                return value.date()
            if isinstance(value, str):
                return datetime.fromisoformat(value.replace("Z", "+00:00")).date()
            raise ValueError(f"Cannot convert {type(value)} to date")

        else:
            return value

    except (ValueError, TypeError) as e:
        raise ValueError(
            f"Failed to convert '{value}' (type: {type(value).__name__}) "
            f"to {spark_type}: {e}"
        )
```

## Cassandra-Specific Types

Handle Cassandra complex types:

```python
def convert_cassandra_to_spark(value):
    """Handle Cassandra-specific complex types."""
    if value is None:
        return None

    from cassandra.util import (
        Date, Time, Duration, OrderedMap, SortedSet,
        Point, LineString, Polygon
    )
    import uuid

    # Cassandra Date to Python date
    if isinstance(value, Date):
        return value.date()

    # Cassandra Time to nanoseconds (LongType)
    if isinstance(value, Time):
        return value.nanosecond

    # UUID to string
    if isinstance(value, uuid.UUID):
        return str(value)

    # Duration to structured dict
    if isinstance(value, Duration):
        return {
            "months": value.months,
            "days": value.days,
            "nanoseconds": value.nanoseconds
        }

    # OrderedMap to dict
    if isinstance(value, OrderedMap):
        return dict(value)

    # SortedSet to list
    if isinstance(value, SortedSet):
        return list(value)

    # Geospatial types to WKT string
    if isinstance(value, (Point, LineString, Polygon)):
        return str(value)

    return value
```

## Schema Inference

Infer Spark types from Python values:

```python
def infer_spark_type(value):
    """Infer Spark type from Python value."""
    from pyspark.sql.types import (
        StringType, IntegerType, LongType, FloatType, DoubleType,
        BooleanType, TimestampType, DateType
    )
    from datetime import datetime, date

    if value is None:
        return StringType()

    # Check bool before int (bool is subclass of int)
    if isinstance(value, bool):
        return BooleanType()

    if isinstance(value, int):
        return LongType()

    if isinstance(value, float):
        return DoubleType()

    if isinstance(value, datetime):
        return TimestampType()

    if isinstance(value, date):
        return DateType()

    # Default to string
    return StringType()
```

## External Type to Spark Type Mapping

Map external system types to Spark types:

```python
def map_external_type_to_spark(external_type):
    """Map external system types to Spark types."""
    from pyspark.sql.types import (
        StringType, IntegerType, LongType, FloatType, DoubleType,
        BooleanType, TimestampType, DateType, BinaryType
    )

    type_str = str(external_type).lower()

    # String types
    if any(t in type_str for t in ["varchar", "text", "char", "string", "uuid"]):
        return StringType()

    # Integer types
    if "int" in type_str and "big" not in type_str:
        return IntegerType()
    if "bigint" in type_str or "long" in type_str:
        return LongType()

    # Floating point
    if "float" in type_str:
        return FloatType()
    if "double" in type_str or "decimal" in type_str:
        return DoubleType()

    # Boolean
    if "bool" in type_str:
        return BooleanType()

    # Temporal types
    if "timestamp" in type_str:
        return TimestampType()
    if "date" in type_str:
        return DateType()

    # Binary
    if "blob" in type_str or "binary" in type_str:
        return BinaryType()

    # Default fallback
    return StringType()
```

## JSON Encoding

Handle datetime serialization for JSON APIs:

```python
import json
from datetime import date, datetime
from decimal import Decimal

class ExtendedJsonEncoder(json.JSONEncoder):
    """JSON encoder that handles datetime, date, and Decimal."""

    def default(self, o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()

        if isinstance(o, Decimal):
            return float(o)

        return super().default(o)

# Usage
def send_as_json(data):
    import requests

    payload = json.dumps(data, cls=ExtendedJsonEncoder)
    requests.post(url, data=payload, headers={"Content-Type": "application/json"})
```

## Complete Row Conversion

Convert entire rows with schema:

```python
def convert_row_to_external(row, column_types):
    """Convert entire Spark row to external system format."""
    row_dict = row.asDict() if hasattr(row, "asDict") else dict(row)

    converted = {}
    for col, value in row_dict.items():
        external_type = column_types.get(col, "text")
        converted[col] = convert_spark_to_external(value, external_type)

    return converted

def convert_external_to_row(data, schema):
    """Convert external data to Spark Row."""
    from pyspark.sql import Row

    # Create mapping of column names to types
    schema_map = {field.name: field.dataType for field in schema.fields}

    row_dict = {}
    for col, value in data.items():
        if col in schema_map:
            spark_type = schema_map[col]
            row_dict[col] = convert_external_to_spark(value, spark_type)

    # Add None for missing columns
    for field in schema.fields:
        if field.name not in row_dict:
            row_dict[field.name] = None

    return Row(**row_dict)
```

## Validation

Validate type conversions:

```python
def validate_conversion(value, expected_type):
    """Validate that value matches expected type after conversion."""
    type_checks = {
        "int": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "long": lambda v: isinstance(v, int) and not isinstance(v, bool),
        "float": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "double": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
        "string": lambda v: isinstance(v, str),
        "boolean": lambda v: isinstance(v, bool),
        "timestamp": lambda v: isinstance(v, datetime),
        "date": lambda v: isinstance(v, date) and not isinstance(v, datetime),
    }

    expected_type_lower = expected_type.lower()
    for type_name, check in type_checks.items():
        if type_name in expected_type_lower:
            if not check(value):
                raise ValueError(
                    f"Value {value} (type: {type(value)}) does not match "
                    f"expected type {expected_type}"
                )
            return

    # No specific check - accept any value
```
