"""FastAPI app for the Claude Code MCP application."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

# Configure logging BEFORE importing other modules
logging.basicConfig(
  level=logging.INFO,
  format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
  handlers=[
    logging.StreamHandler(),
  ],
)

from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware

from .db import is_postgres_configured, is_dynamic_token_mode, run_migrations, init_database, start_token_refresh, stop_token_refresh
from .routers import agent_router, clusters_router, config_router, conversations_router, projects_router, skills_router, warehouses_router
from .services.backup_manager import start_backup_worker, stop_backup_worker
from .services.skills_manager import copy_skills_to_app

logger = logging.getLogger(__name__)

# Load environment variables
env_local_loaded = load_dotenv(dotenv_path='.env.local')
env = os.getenv('ENV', 'development' if env_local_loaded else 'production')

if env_local_loaded:
  logger.info(f'Loaded .env.local (ENV={env})')
else:
  logger.info(f'Using system environment variables (ENV={env})')


@asynccontextmanager
async def lifespan(app: FastAPI):
  """Async lifespan context manager for startup/shutdown events."""
  logger.info('Starting application...')

  # Copy skills from databricks-skills to local cache
  copy_skills_to_app()

  # Initialize database if configured
  db_initialized = False
  if is_postgres_configured():
    logger.info('Initializing database...')
    try:
      init_database()
      db_initialized = True

      # Start token refresh for dynamic OAuth mode (Databricks Apps)
      if is_dynamic_token_mode():
        await start_token_refresh()

      # Run migrations in background thread (non-blocking)
      asyncio.create_task(asyncio.to_thread(run_migrations))

      # Start backup worker
      start_backup_worker()
    except Exception as e:
      logger.warning(
        f'Database initialization failed: {e}\n'
        'App will continue without database features (conversations won\'t be persisted).'
      )
  else:
    logger.warning(
      'Database not configured. Set either:\n'
      '  - LAKEBASE_PG_URL (static URL with password), or\n'
      '  - LAKEBASE_INSTANCE_NAME and LAKEBASE_DATABASE_NAME (dynamic OAuth)'
    )

  yield

  logger.info('Shutting down application...')

  # Stop token refresh if running
  await stop_token_refresh()

  stop_backup_worker()


app = FastAPI(
  title='Claude Code MCP App',
  description='Project-based Claude Code agent application',
  lifespan=lifespan,
)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
  """Log all unhandled exceptions."""
  logger.exception(f'Unhandled exception for {request.method} {request.url}: {exc}')
  return JSONResponse(
    status_code=500,
    content={'detail': 'Internal Server Error', 'error': str(exc)},
  )


# Configure CORS
allowed_origins = ['http://localhost:3000', 'http://localhost:3001', 'http://localhost:5173'] if env == 'development' else []
logger.info(f'CORS allowed origins: {allowed_origins}')

app.add_middleware(
  CORSMiddleware,
  allow_origins=allowed_origins,
  allow_credentials=True,
  allow_methods=['*'],
  allow_headers=['*'],
)

API_PREFIX = '/api'

# Include routers
app.include_router(config_router, prefix=f'{API_PREFIX}/config', tags=['configuration'])
app.include_router(clusters_router, prefix=API_PREFIX, tags=['clusters'])
app.include_router(warehouses_router, prefix=API_PREFIX, tags=['warehouses'])
app.include_router(projects_router, prefix=API_PREFIX, tags=['projects'])
app.include_router(conversations_router, prefix=API_PREFIX, tags=['conversations'])
app.include_router(agent_router, prefix=API_PREFIX, tags=['agent'])
app.include_router(skills_router, prefix=API_PREFIX, tags=['skills'])

# Production: Serve Vite static build
# Check multiple possible locations for the frontend build
_app_root = Path(__file__).parent.parent  # server/app.py -> app root
_possible_build_paths = [
  _app_root / 'client/out',  # Standard location relative to app root
  Path('.') / 'client/out',  # Relative to working directory
  Path('/app/python/source_code') / 'client/out',  # Databricks Apps location
]

build_path = None
for path in _possible_build_paths:
  if path.exists():
    build_path = path
    break

if build_path:
  logger.info(f'Serving static files from {build_path}')
  index_html = build_path / 'index.html'

  # SPA fallback: catch 404s from static files and serve index.html for client-side routing
  # This must be defined BEFORE mounting static files
  @app.exception_handler(StarletteHTTPException)
  async def spa_fallback(request: Request, exc: StarletteHTTPException):
    # Only handle 404s for non-API routes
    if exc.status_code == 404 and not request.url.path.startswith('/api'):
      return FileResponse(index_html)
    # For API 404s or other errors, return JSON
    return JSONResponse(
      status_code=exc.status_code,
      content={'detail': exc.detail},
    )

  app.mount('/', StaticFiles(directory=str(build_path), html=True), name='static')
else:
  logger.warning(
    f'Build directory not found in any of: {[str(p) for p in _possible_build_paths]}. '
    'In development, run Vite separately: cd client && npm run dev'
  )
