"""Alembic environment configuration for database migrations.

Uses sync psycopg2 driver for migrations (simpler and avoids async event loop issues).
Runtime database access uses async psycopg3 driver.
"""

import os
from logging.config import fileConfig

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

# Load environment variables from .env.local
load_dotenv('.env.local')

# Import models for autogenerate support
from server.db.models import Base
from server.db.database import _resolve_hostname

# this is the Alembic Config object
config = context.config

# Setup logging from alembic.ini
if config.config_file_name is not None:
  fileConfig(config.config_file_name)

# Target metadata for autogenerate
target_metadata = Base.metadata

# Store resolved hostaddr for connect_args
_resolved_hostaddr = None


def get_url_and_connect_args():
  """Get database URL and connect_args from environment.

  Supports three modes:
  1. Static URL: Uses LAKEBASE_PG_URL directly
  2. Autoscale OAuth: Builds URL from LAKEBASE_ENDPOINT + generates token via client.postgres
  3. Provisioned OAuth: Builds URL from LAKEBASE_INSTANCE_NAME + generates token via client.database

  Returns tuple of (url, connect_args) for psycopg2 driver.
  """
  global _resolved_hostaddr
  connect_args = {}

  url = os.environ.get('LAKEBASE_PG_URL')

  if not url:
    # Try dynamic OAuth mode
    endpoint_name = os.environ.get('LAKEBASE_ENDPOINT')
    instance_name = os.environ.get('LAKEBASE_INSTANCE_NAME')
    database_name = os.environ.get('LAKEBASE_DATABASE_NAME', 'databricks_postgres')

    if not endpoint_name and not instance_name:
      raise ValueError(
        'Database not configured. Set either:\n'
        '  - LAKEBASE_PG_URL (static URL with password), or\n'
        '  - LAKEBASE_ENDPOINT and LAKEBASE_DATABASE_NAME (autoscale, dynamic OAuth), or\n'
        '  - LAKEBASE_INSTANCE_NAME and LAKEBASE_DATABASE_NAME (provisioned, dynamic OAuth)'
      )

    # Generate token using Databricks SDK
    import uuid
    from databricks.sdk import WorkspaceClient
    from databricks_tools_core.identity import PRODUCT_NAME, PRODUCT_VERSION

    w = WorkspaceClient(product=PRODUCT_NAME, product_version=PRODUCT_VERSION)

    if endpoint_name:
      # Autoscale mode: look up host from endpoint, token via client.postgres
      endpoint = w.postgres.get_endpoint(name=endpoint_name)
      host = endpoint.status.hosts.host
      cred = w.postgres.generate_database_credential(endpoint=endpoint_name)
    else:
      # Provisioned mode: look up host from instance, token via client.database
      instance = w.database.get_database_instance(name=instance_name)
      host = instance.read_write_dns
      cred = w.database.generate_database_credential(
        request_id=str(uuid.uuid4()),
        instance_names=[instance_name],
      )

    # Get current user email for username
    me = w.current_user.me()
    username = me.user_name

    # URL-encode username (emails contain @)
    from urllib.parse import quote
    encoded_username = quote(username, safe='')

    # Build URL with token as password
    url = f'postgresql://{encoded_username}:{cred.token}@{host}:5432/{database_name}?sslmode=require'

    # Resolve hostname for DNS workaround (macOS issue)
    _resolved_hostaddr = _resolve_hostname(host)
    if _resolved_hostaddr:
      connect_args['hostaddr'] = _resolved_hostaddr

  # Ensure URL uses sync driver (psycopg2) for migrations
  if url.startswith('postgresql+asyncpg://'):
    url = url.replace('postgresql+asyncpg://', 'postgresql://', 1)
  if url.startswith('postgresql+psycopg://'):
    url = url.replace('postgresql+psycopg://', 'postgresql://', 1)

  return url, connect_args


def run_migrations_offline():
  """Run migrations in 'offline' mode.

  This configures the context with just a URL
  and not an Engine, though an Engine is acceptable
  here as well. By skipping the Engine creation
  we don't even need a DBAPI to be available.

  Calls to context.execute() here emit the given string to the
  script output.
  """
  url, _ = get_url_and_connect_args()
  context.configure(
    url=url,
    target_metadata=target_metadata,
    literal_binds=True,
    dialect_opts={'paramstyle': 'named'},
  )

  with context.begin_transaction():
    context.run_migrations()


def run_migrations_online():
  """Run migrations in 'online' mode using sync engine."""
  url, connect_args = get_url_and_connect_args()

  # Get schema name from Alembic config or environment
  schema_name = config.get_main_option('lakebase_schema_name') or os.environ.get('LAKEBASE_SCHEMA_NAME', 'builder_app')

  # Validate schema name to prevent SQL injection (only allow alphanumeric + underscores)
  import re
  if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', schema_name):
    raise ValueError(f'Invalid schema name: {schema_name!r} — must be alphanumeric/underscores only')

  # Add search_path to connect_args so tables are created in the custom schema
  connect_args.setdefault('options', f'-c search_path={schema_name},public')

  connectable = create_engine(
    url,
    poolclass=pool.NullPool,
    connect_args=connect_args,
  )

  with connectable.connect() as connection:
    # Create the schema if it doesn't exist (SP has CREATE on the database)
    from sqlalchemy import text
    connection.execute(text(f'CREATE SCHEMA IF NOT EXISTS {schema_name}'))
    connection.commit()

    context.configure(
      connection=connection,
      target_metadata=target_metadata,
    )

    with context.begin_transaction():
      context.run_migrations()

  connectable.dispose()


if context.is_offline_mode():
  run_migrations_offline()
else:
  run_migrations_online()
