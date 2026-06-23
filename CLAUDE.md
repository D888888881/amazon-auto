# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is an **Amazon ASIN Analysis & Management Platform** — a Django web application that helps sellers analyze product performance, manage Amazon seller credentials, and automate ROI calculations and advertising difficulty assessments for multiple ASINs (Amazon Standard Identification Numbers).

**Key Components:**
- **Django backend** (Python 3.10+): REST APIs, job queuing, credential management, data processing
- **RQ job queue**: Background job execution for async tasks (ROI calculation, advertising difficulty ranking, wizard jobs)
- **MySQL database**: Stores ASIN dashboard data, user profiles, seller credentials, job state
- **Redis cache**: Used by Django RQ for job queue and Django cache
- **Web UI**: HTML/CSS templates for dashboard, Excel import, credential config, job scheduling
- **Async APIs**: Scripts for fetching Amazon data, seller info, ad metrics using Playwright/aiohttp

## Quick Start Commands

### Development Setup
```bash
# Install dependencies in virtual environment
pip install -r requirements.txt

# Run migrations
python manage.py migrate

# Start development server (port 8000)
python manage.py runserver

# In a separate terminal, start RQ job worker
python manage.py rqworker default
```

### Testing & Inspection
```bash
# Run Django shell for debugging models/queries
python manage.py shell

# Check job queue status
python manage.py rq_show_scheduled

# Run a single test module
python manage.py test auto_amazon.tests.MyTestClass
```

### Docker Deployment
```bash
# Build and run with docker-compose (includes MySQL, Redis)
docker-compose up --build

# Or run migrations in isolation before starting
docker-compose up -d db redis
docker-compose run --rm web migrate-only
docker-compose up
```

## Architecture & Design Patterns

### Request Flow
1. **Views** (`auto_amazon/views.py`): Django views handle HTTP requests, validate inputs, manage transactions
2. **Job Enqueueing** (`auto_amazon/rq_enqueue.py`): Long-running tasks (ROI calc, ad difficulty) are enqueued to RQ
3. **RQ Tasks** (`auto_amazon/rq_tasks.py`): Worker processes jobs asynchronously; status is polled from the frontend
4. **Async Scripts** (`scripts/asin_find_project/`): External APIs (Amazon, Taobao, etc.) are called via Playwright or aiohttp

### Key Models
- **UserProfile**: Extends Django User with registration approval status (pending/approved/rejected)
- **AsinDashboardRow**: One row per ASIN per user; stores metrics (profit margin, ad difficulty, ROI, trend data)
- **AsinFolderAssignment**: Maps ASIN folders to user access (many-to-many)

### Database Design
- **MySQL with utf8mb4 charset** for Chinese character support
- **Unique constraint** on (user, asin) in AsinDashboardRow to prevent duplicate entries
- **Foreign key relationships** to User for multi-tenancy and access control
- **Index on ASIN** for fast lookups

### Background Job System
- Uses **RQ (Redis Queue)** for job management
- **rq_enqueue.py**: Queue new jobs, set timeouts, manage retries
- **rq_tasks.py**: Actual job implementations (ROI, ad difficulty calculations)
- **Resilient wrapper** (`resilient_wizard.py`): Batches ASIN processing with failure recovery
- **Job lock** (`asin_job_lock.py`): Prevents concurrent jobs on the same ASIN

### Excel Import/Export
- **openpyxl** for reading/writing Excel files preserving formatting
- **excel_io.py**: Core read/save operations on active sheet
- **excel_import_utils.py**: Parse Excel data, validate schema, bulk insert to database
- **excel_search_restore.py**: Restore original source values from API results

### External API Integration
- **async_seller_wizard_api.py**: Fetch Amazon seller account info (requires auth cookies)
- **async_advertisement_api.py**: Query ad difficulty ranking data
- **Playwright**: Browser automation for cookie/session management and form submission
- **aiohttp**: High-concurrency HTTP requests with rate limiting

### Media/File Handling
- ASIN-specific folders: `media/file/<ASIN>/` for product images and work files
- **media_import_staging.py**: Batch image processing, validation, storage
- **AsinFolderAssignment**: Controls who can access which ASIN's files

## Critical Files & Their Responsibilities

| File | Purpose |
|------|---------|
| `auto_amazon/models.py` | All database model definitions (UserProfile, AsinDashboardRow, etc.) |
| `auto_amazon/views.py` | Main HTTP request handlers (dashboard, Excel upload, job status, API endpoints) |
| `auto_amazon/rq_enqueue.py` | Job enqueueing logic, timeout settings, retry configuration |
| `auto_amazon/rq_tasks.py` | RQ job task implementations (ROI calc, ad difficulty ranking) |
| `auto_amazon/resilient_wizard.py` | Batch processing orchestration with failure handling |
| `auto_amazon/asin_wizard.py` | Core ASIN data analysis and wizard runtime |
| `auto_amazon/excel_io.py` | openpyxl wrapper for Excel read/write with formatting preservation |
| `auto_amazon/excel_import_utils.py` | Validation and bulk data import from Excel |
| `auto_amazon/credentials_config.py` | Encrypted credential storage and rotation |
| `auto_amazon/scheduled_jobs.py` | Periodic task scheduling (e.g., daily ROI recalc) |
| `scripts/asin_find_project/` | External API clients (seller wizard, ad difficulty, image search, etc.) |
| `auto_amazon_project/settings.py` | Django settings (DB, cache, installed apps, RQ config) |
| `auto_amazon_project/urls.py` | URL routing |

## Development Notes

### Multi-Tenancy
- All dashboard and credential data is **user-scoped**
- **UserProfile approval system**: New registrations require admin review before login
- **ASIN folder assignment**: Admin controls which users can access which ASIN folders

### ROI Calculation
- Triggered on-demand or via scheduled jobs
- Calls **resilient_wizard.py** for batch ASIN processing
- Updates `AsinDashboardRow.ad_removed_roi` and related fields
- Exchange rate is fetched and stored for each row

### Ad Difficulty Ranking
- Uses Amazon seller account API (via Playwright) + ranking metrics
- Returns percentile/ranking scores
- Failures are caught and logged; job continues on remaining ASINs

### Transaction Safety
- Critical sections use Django `@transaction.atomic()` to prevent partial updates
- Database connection pooling: `django.db.close_old_connections()` after long async work

### Credential Management
- Seller accounts stored encrypted in database (`credentials_config.py`)
- Cookie sessions managed via file storage or in-process
- Supports bulk account configuration from JSON config files

### Excel Processing
- Preserves cell formatting (colors, font, borders) during read/write
- Handles merged cells and complex sheets
- Validates required columns before import

## Testing

Run the full test suite:
```bash
python manage.py test
```

Run specific test:
```bash
python manage.py test auto_amazon.tests.TestAsinDashboard
```

Tests use Django's test database (SQLite by default in test settings).

## Environment Variables

**Database Configuration:**
- `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` (preferred)
- Falls back to `MYSQL_*` env vars for Docker compose compatibility

**Django Settings:**
- `DEBUG`: Set to False in production
- `CSRF_TRUSTED_ORIGINS`: Comma-separated list of allowed origins

**Redis/RQ:**
- Configured in `settings.py` via `RQ_QUEUES` dict
- Default: `redis://127.0.0.1:6379/0`

## Common Workflows

### Add a New ASIN Field to Dashboard
1. Add field to `AsinDashboardRow` model in `models.py`
2. Create migration: `python manage.py makemigrations`
3. Apply migration: `python manage.py migrate`
4. Update Excel import schema in `excel_import_utils.py` if needed
5. Update templates (`templates/auto_amazon/asin_dashboard.html`) to display the field

### Enqueue a Background Job
```python
from auto_amazon.rq_enqueue import enqueue_roi_calc

enqueue_roi_calc(asin=row.asin, user_id=user.id, timeout=600)
```

### Add an External API Call
1. Create async function in `scripts/asin_find_project/` (use aiohttp or Playwright)
2. Handle rate limiting via `shared_rate_limit.py`
3. Call from job task or view with proper exception handling
4. Log failures to allow job continuation on other items

### Deploy with Docker
```bash
docker-compose down
docker-compose up -d --build
# Migrations run automatically via entrypoint.sh
```

## Known Constraints

- **PyMySQL charset limitation**: DB password must be ASCII-encodable (latin-1); no Unicode special chars
- **Playwright overhead**: Browser automation via Playwright is slower than native API calls; batch requests when possible
- **RQ job timeouts**: Long-running jobs (600s default) may need adjustment for large ASIN batches
- **SQLite in tests**: Development tests run faster but use SQLite; mirror DB-specific behavior with explicit test settings if needed
- **Media folder cleanup**: Orphaned ASIN folders are not auto-deleted; manual cleanup via admin panel needed

## Debugging Tips

- **RQ job stuck?** Check Redis: `redis-cli`, then `LRANGE rq:jobs:default 0 -1`
- **Import failures?** Enable debug logging in Excel import utils; check error_rows column
- **Slow queries?** Use Django debug toolbar or raw `EXPLAIN` queries
- **Credential errors?** Verify encrypted key in `settings.py`, check credential entry in database
- **Async API timeout?** Increase `aiohttp.ClientSession` timeout or reduce batch size
