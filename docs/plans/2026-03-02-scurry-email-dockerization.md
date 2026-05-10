# Scurry Email Service Dockerization Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Dockerize the scurry_web PHP email API, move it to `services/scurry-email/`, migrate from MySQL to PostgreSQL, and integrate it into the docker-compose stack.

**Architecture:** The PHP app runs as an Apache+PHP container (`scurry-email`) in the docker-compose stack. It shares the existing PostgreSQL database (new tables added via Alembic migration). The FastAPI backend proxies to `http://scurry-email:8080` instead of the external `luaakserver.com` URL.

**Tech Stack:** PHP 8.1 + Apache, PostgreSQL 15 (existing), Docker, Alembic

---

### Task 1: Move scurry_web to services/scurry-email/

**Files:**
- Move: `scurry_web/` → `services/scurry-email/`

**Step 1: Create directory and move files**

```bash
mkdir -p services
mv scurry_web services/scurry-email
```

**Step 2: Verify files moved correctly**

```bash
ls services/scurry-email/
# Expected: README.md, config.php, db.php, auth.php, test.php, email/, auth/, outlook/, track/, sql/
```

**Step 3: Commit**

```bash
git add -A
git commit -m "refactor: move scurry_web to services/scurry-email/"
```

---

### Task 2: Create Dockerfile for PHP+Apache

**Files:**
- Create: `services/scurry-email/Dockerfile`
- Create: `services/scurry-email/.dockerignore`
- Create: `services/scurry-email/.htaccess`

**Step 1: Create Dockerfile**

```dockerfile
FROM php:8.1-apache

# Install PostgreSQL PDO driver, curl, and openssl extensions
RUN apt-get update && apt-get install -y \
    libpq-dev \
    libcurl4-openssl-dev \
    && docker-php-ext-install pdo pdo_pgsql curl \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Enable Apache mod_rewrite
RUN a2enmod rewrite

# Configure Apache to allow .htaccess overrides
RUN sed -i 's/AllowOverride None/AllowOverride All/g' /etc/apache2/apache2.conf

# Set working directory
WORKDIR /var/www/html

# Copy PHP source files
COPY . /var/www/html/

# Set correct permissions
RUN chown -R www-data:www-data /var/www/html

# Expose port 80 (Apache default)
EXPOSE 80

# Health check
HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
    CMD curl -f http://localhost/test.php || exit 1
```

**Step 2: Create .dockerignore**

```
README.md
readme.docx
*.postman_collection.json
postman.json
sql/
.git
```

**Step 3: Create .htaccess**

```apache
RewriteEngine On

# Allow direct access to PHP files
RewriteCond %{REQUEST_FILENAME} -f
RewriteRule ^ - [L]

# Allow directory access
RewriteCond %{REQUEST_FILENAME} -d
RewriteRule ^ - [L]
```

**Step 4: Verify Dockerfile builds**

```bash
cd services/scurry-email && docker build -t scurry-email-test . && cd ../..
# Expected: successful build
```

**Step 5: Commit**

```bash
git add services/scurry-email/Dockerfile services/scurry-email/.dockerignore services/scurry-email/.htaccess
git commit -m "feat: add Dockerfile for scurry-email PHP service"
```

---

### Task 3: Convert PHP config to use environment variables

**Files:**
- Modify: `services/scurry-email/config.php`
- Modify: `services/scurry-email/outlook/config.php`

**Step 1: Rewrite `config.php` to read from environment**

Replace all hardcoded values with `getenv()` calls with sensible defaults:

```php
<?php
/**
 * Scurry Email API - Configuration
 */

// GOOGLE OAUTH SETTINGS
define('GOOGLE_CLIENT_ID', getenv('GOOGLE_CLIENT_ID') ?: '');
define('GOOGLE_CLIENT_SECRET', getenv('GOOGLE_CLIENT_SECRET') ?: '');
define('GOOGLE_REDIRECT_URI', getenv('GOOGLE_REDIRECT_URI') ?: '');

// APP SETTINGS
define('APP_URL', getenv('SCURRY_APP_URL') ?: 'http://localhost:8080');

// DATABASE SETTINGS (PostgreSQL)
define('DB_HOST', getenv('DB_HOST') ?: 'postgres');
define('DB_PORT', getenv('DB_PORT') ?: '5432');
define('DB_NAME', getenv('DB_NAME') ?: 'workflow_platform');
define('DB_USER', getenv('DB_USER') ?: 'workflow_user');
define('DB_PASS', getenv('DB_PASS') ?: 'workflow_pass');

// JWT SETTINGS
define('JWT_SECRET', getenv('JWT_SECRET') ?: '');
define('AUTH_API_URL', getenv('AUTH_API_URL') ?: 'http://backend:9000/auth/me');
define('JWT_VERIFY_METHOD', getenv('JWT_VERIFY_METHOD') ?: 'api');

// ENCRYPTION KEY
define('ENCRYPTION_KEY', getenv('SCURRY_ENCRYPTION_KEY') ?: '');

// CORS SETTINGS
define('CORS_ALLOWED_ORIGINS', getenv('CORS_ALLOWED_ORIGINS') ?: '*');
```

**Step 2: Rewrite `outlook/config.php` to read from environment**

```php
<?php
/**
 * Scurry Outlook API - Configuration
 */

// MICROSOFT OAUTH SETTINGS
define('MICROSOFT_CLIENT_ID', getenv('MICROSOFT_CLIENT_ID') ?: '');
define('MICROSOFT_CLIENT_SECRET', getenv('MICROSOFT_CLIENT_SECRET') ?: '');
define('MICROSOFT_REDIRECT_URI', getenv('MICROSOFT_REDIRECT_URI') ?: '');
define('MICROSOFT_TENANT', getenv('MICROSOFT_TENANT') ?: 'common');

// Microsoft API URLs
define('MICROSOFT_AUTHORITY', 'https://login.microsoftonline.com/' . MICROSOFT_TENANT);
define('MICROSOFT_AUTHORIZE_URL', MICROSOFT_AUTHORITY . '/oauth2/v2.0/authorize');
define('MICROSOFT_TOKEN_URL', MICROSOFT_AUTHORITY . '/oauth2/v2.0/token');
define('MICROSOFT_GRAPH_URL', 'https://graph.microsoft.com/v1.0');
define('MICROSOFT_SCOPES', 'openid profile email offline_access Mail.Read Mail.Send User.Read');

// APP SETTINGS
define('APP_URL', getenv('SCURRY_OUTLOOK_APP_URL') ?: 'http://localhost:8080/outlook');

// DATABASE SETTINGS (shared from parent config OR re-read env)
if (!defined('DB_HOST')) {
    define('DB_HOST', getenv('DB_HOST') ?: 'postgres');
    define('DB_PORT', getenv('DB_PORT') ?: '5432');
    define('DB_NAME', getenv('DB_NAME') ?: 'workflow_platform');
    define('DB_USER', getenv('DB_USER') ?: 'workflow_user');
    define('DB_PASS', getenv('DB_PASS') ?: 'workflow_pass');
}

// JWT SETTINGS
if (!defined('AUTH_API_URL')) {
    define('AUTH_API_URL', getenv('AUTH_API_URL') ?: 'http://backend:9000/auth/me');
    define('JWT_VERIFY_METHOD', getenv('JWT_VERIFY_METHOD') ?: 'api');
}

// ENCRYPTION KEY
if (!defined('ENCRYPTION_KEY')) {
    define('ENCRYPTION_KEY', getenv('SCURRY_ENCRYPTION_KEY') ?: '');
}

// TRACKING SETTINGS
define('TRACKING_BASE_URL', APP_URL . '/track');

// CORS SETTINGS
if (!defined('CORS_ALLOWED_ORIGINS')) {
    define('CORS_ALLOWED_ORIGINS', getenv('CORS_ALLOWED_ORIGINS') ?: '*');
}
```

**Step 3: Commit**

```bash
git add services/scurry-email/config.php services/scurry-email/outlook/config.php
git commit -m "feat: convert scurry-email config to environment variables"
```

---

### Task 4: Convert PHP database layer from MySQL to PostgreSQL

**Files:**
- Modify: `services/scurry-email/db.php`
- Modify: `services/scurry-email/outlook/db.php`

**Step 1: Update `db.php` PDO connection to PostgreSQL**

Change the PDO DSN from MySQL to PostgreSQL:

```php
function getDbConnection() {
    static $pdo = null;

    if ($pdo === null) {
        try {
            $dsn = "pgsql:host=" . DB_HOST . ";port=" . DB_PORT . ";dbname=" . DB_NAME;
            $pdo = new PDO(
                $dsn,
                DB_USER,
                DB_PASS,
                [
                    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                    PDO::ATTR_EMULATE_PREPARES => false
                ]
            );
        } catch (PDOException $e) {
            errorResponse('DATABASE_ERROR', 'Database connection failed: ' . $e->getMessage(), 500);
        }
    }

    return $pdo;
}
```

**Step 2: Apply same change to `outlook/db.php`**

Same PDO DSN change.

**Step 3: Commit**

```bash
git add services/scurry-email/db.php services/scurry-email/outlook/db.php
git commit -m "feat: convert scurry-email database layer to PostgreSQL"
```

---

### Task 5: Convert all PHP SQL syntax from MySQL to PostgreSQL

**Files:**
- Modify: `services/scurry-email/auth.php` (line 166-173: `NOW()` → `CURRENT_TIMESTAMP`, `lastInsertId()` remains valid for pgsql)
- Modify: `services/scurry-email/auth/gmail/connect.php` (oauth_states INSERT uses `NOW()`)
- Modify: `services/scurry-email/auth/gmail/callback.php` (email_accounts INSERT uses `NOW()`)
- Modify: `services/scurry-email/auth/gmail/disconnect.php`
- Modify: `services/scurry-email/email/send.php` (sent_emails INSERT, tracking updates)
- Modify: `services/scurry-email/email/accounts.php`
- Modify: `services/scurry-email/email/sent.php`
- Modify: `services/scurry-email/email/inbox.php`
- Modify: `services/scurry-email/email/replies.php`
- Modify: `services/scurry-email/track/open.php`
- Modify: `services/scurry-email/track/click.php`
- Modify: `services/scurry-email/track/events.php`
- Modify: `services/scurry-email/track/stats.php`
- Modify: `services/scurry-email/outlook/auth/connect.php`
- Modify: `services/scurry-email/outlook/auth/callback.php`
- Modify: `services/scurry-email/outlook/auth/disconnect.php`
- Modify: `services/scurry-email/outlook/email/send.php`
- Modify: `services/scurry-email/outlook/track/open.php`
- Modify: `services/scurry-email/outlook/track/click.php`

**MySQL → PostgreSQL conversion rules to apply across ALL files:**

1. `NOW()` → `CURRENT_TIMESTAMP` (PostgreSQL standard)
2. Remove backtick quoting around table/column names (PostgreSQL uses double quotes if needed, but standard names don't need quoting)
3. `ENUM('open', 'click')` columns → use VARCHAR with CHECK constraint (handled in migration, PHP code just passes string values - no PHP changes needed)
4. `LONGTEXT` → `TEXT` (PostgreSQL `TEXT` is unlimited)
5. `JSON` columns → `JSONB` (handled in migration, PHP passes JSON strings - PDO handles this)
6. `BOOLEAN DEFAULT TRUE` → same (PostgreSQL supports this natively)
7. `lastInsertId()` → works with pgsql PDO driver (returns sequence value)
8. `DATE_SUB(NOW(), INTERVAL 30 DAY)` → `CURRENT_TIMESTAMP - INTERVAL '30 days'`
9. `DATE(created_at)` → `created_at::date` or `DATE(created_at)` (both work in PostgreSQL)

**Step 1: Search and replace `NOW()` with `CURRENT_TIMESTAMP` in all PHP files**

Apply across all files listed above. The key files are:
- `auth.php` line 168: `VALUES (?, ?, ?, NOW())`
- `auth/gmail/connect.php`: `NOW()` in INSERT for oauth_states
- `auth/gmail/callback.php`: `NOW()` in INSERT/UPDATE for email_accounts
- `email/send.php`: `NOW()` in INSERT for sent_emails
- `track/open.php`: `NOW()` in INSERT for email_tracking and UPDATE for sent_emails
- `track/click.php`: same pattern
- All corresponding `outlook/` files

**Step 2: Fix MySQL-specific date functions**

In `track/stats.php` and similar files, change:
- `DATE_SUB(NOW(), INTERVAL 30 DAY)` → `CURRENT_TIMESTAMP - INTERVAL '30 days'`
- `DATE(created_at)` → `created_at::date`

**Step 3: Remove backtick quoting if present in any queries**

Search for backtick characters in SQL queries and remove them.

**Step 4: Verify no MySQL-specific syntax remains**

```bash
grep -rn "NOW()" services/scurry-email/ --include="*.php"
grep -rn "AUTO_INCREMENT" services/scurry-email/ --include="*.php"
grep -rn "DATE_SUB" services/scurry-email/ --include="*.php"
# Expected: no matches (only schema.sql should have MySQL syntax, which we don't execute)
```

**Step 5: Commit**

```bash
git add services/scurry-email/
git commit -m "feat: convert all scurry-email SQL from MySQL to PostgreSQL syntax"
```

---

### Task 6: Create Alembic migration for scurry email tables

**Files:**
- Create: `backend/alembic/versions/015_add_scurry_email_tables.py`

**Step 1: Create the migration file**

This migration creates 8 tables in PostgreSQL that mirror the MySQL schema. Key conversions:
- `AUTO_INCREMENT` → `SERIAL` (via `sa.Column(sa.Integer, primary_key=True, autoincrement=True)`)
- `ENUM` → `VARCHAR` with CHECK constraint
- `LONGTEXT` → `TEXT`
- `JSON` → `JSONB`
- `DATETIME` → `TIMESTAMP`
- MySQL indexes → PostgreSQL indexes

Tables to create:
1. `scurry_users` (renamed from `gmail_users` to avoid confusion with Gmail-specific naming)
2. `scurry_oauth_states`
3. `scurry_email_accounts` (Gmail accounts)
4. `scurry_sent_emails` (Gmail sent)
5. `scurry_email_tracking` (Gmail tracking)
6. `scurry_outlook_accounts`
7. `scurry_outlook_sent_emails`
8. `scurry_outlook_tracking`

**IMPORTANT:** All tables are prefixed with `scurry_` to avoid conflicts with existing aibot2 tables.

```python
"""Add scurry email tables

Revision ID: 015
Revises: 014
Create Date: 2026-03-02
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers
revision = '015_add_scurry_email_tables'
down_revision = '014_add_reason_and_token_tracking'
branch_labels = None
depends_on = None

def upgrade():
    # Scurry Users (mapped from auth system)
    op.create_table('scurry_users',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('external_user_id', sa.Integer(), nullable=False, unique=True),
        sa.Column('username', sa.String(255), nullable=True),
        sa.Column('email', sa.String(255), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True),
    )
    op.create_index('ix_scurry_users_external_user_id', 'scurry_users', ['external_user_id'])

    # OAuth State Tokens
    op.create_table('scurry_oauth_states',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('state_token', sa.String(64), nullable=False, unique=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('expires_at', sa.TIMESTAMP(), nullable=False),
    )
    op.create_index('ix_scurry_oauth_states_state_token', 'scurry_oauth_states', ['state_token'])
    op.create_index('ix_scurry_oauth_states_expires_at', 'scurry_oauth_states', ['expires_at'])

    # Gmail Email Accounts
    op.create_table('scurry_email_accounts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('provider', sa.String(50), nullable=False, server_default='gmail'),
        sa.Column('email_address', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('scopes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('last_sync_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('sync_error', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True),
        sa.UniqueConstraint('user_id', 'email_address', name='uq_scurry_email_accounts_user_email'),
    )
    op.create_index('ix_scurry_email_accounts_user_id', 'scurry_email_accounts', ['user_id'])
    op.create_index('ix_scurry_email_accounts_email', 'scurry_email_accounts', ['email_address'])
    op.create_index('ix_scurry_email_accounts_active', 'scurry_email_accounts', ['is_active'])

    # Gmail Sent Emails
    op.create_table('scurry_sent_emails',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('recipient_email', sa.String(255), nullable=False),
        sa.Column('recipient_name', sa.String(255), nullable=True),
        sa.Column('cc', sa.JSON(), nullable=True),
        sa.Column('bcc', sa.JSON(), nullable=True),
        sa.Column('subject', sa.String(1000), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('gmail_message_id', sa.String(255), nullable=True),
        sa.Column('gmail_thread_id', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('opens', sa.Integer(), server_default='0'),
        sa.Column('clicks', sa.Integer(), server_default='0'),
        sa.Column('first_opened_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_opened_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('first_clicked_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_clicked_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('sent_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed')", name='ck_scurry_sent_emails_status'),
    )
    op.create_index('ix_scurry_sent_emails_user_id', 'scurry_sent_emails', ['user_id'])
    op.create_index('ix_scurry_sent_emails_account_id', 'scurry_sent_emails', ['account_id'])
    op.create_index('ix_scurry_sent_emails_status', 'scurry_sent_emails', ['status'])
    op.create_index('ix_scurry_sent_emails_recipient', 'scurry_sent_emails', ['recipient_email'])
    op.create_index('ix_scurry_sent_emails_sent_at', 'scurry_sent_emails', ['sent_at'])

    # Gmail Email Tracking Events
    op.create_table('scurry_email_tracking',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email_id', sa.Integer(), sa.ForeignKey('scurry_sent_emails.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(20), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("event_type IN ('open', 'click')", name='ck_scurry_email_tracking_type'),
    )
    op.create_index('ix_scurry_email_tracking_email_id', 'scurry_email_tracking', ['email_id'])
    op.create_index('ix_scurry_email_tracking_type', 'scurry_email_tracking', ['event_type'])

    # Outlook Accounts
    op.create_table('scurry_outlook_accounts',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('email_address', sa.String(255), nullable=False),
        sa.Column('display_name', sa.String(255), nullable=True),
        sa.Column('microsoft_user_id', sa.String(255), nullable=True),
        sa.Column('access_token', sa.Text(), nullable=False),
        sa.Column('refresh_token', sa.Text(), nullable=True),
        sa.Column('token_expires_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('is_active', sa.Boolean(), server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.TIMESTAMP(), nullable=True),
        sa.UniqueConstraint('user_id', 'email_address', name='uq_scurry_outlook_accounts_user_email'),
    )
    op.create_index('ix_scurry_outlook_accounts_user_id', 'scurry_outlook_accounts', ['user_id'])
    op.create_index('ix_scurry_outlook_accounts_email', 'scurry_outlook_accounts', ['email_address'])

    # Outlook Sent Emails
    op.create_table('scurry_outlook_sent_emails',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('account_id', sa.Integer(), nullable=False),
        sa.Column('recipient_email', sa.String(255), nullable=False),
        sa.Column('recipient_name', sa.String(255), nullable=True),
        sa.Column('cc', sa.JSON(), nullable=True),
        sa.Column('bcc', sa.JSON(), nullable=True),
        sa.Column('subject', sa.String(1000), nullable=False),
        sa.Column('body_html', sa.Text(), nullable=False),
        sa.Column('body_text', sa.Text(), nullable=True),
        sa.Column('outlook_message_id', sa.String(255), nullable=True),
        sa.Column('status', sa.String(20), nullable=False, server_default='pending'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('opens', sa.Integer(), server_default='0'),
        sa.Column('clicks', sa.Integer(), server_default='0'),
        sa.Column('first_opened_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_opened_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('first_clicked_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('last_clicked_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('sent_at', sa.TIMESTAMP(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("status IN ('pending', 'sent', 'failed')", name='ck_scurry_outlook_sent_status'),
    )
    op.create_index('ix_scurry_outlook_sent_user_id', 'scurry_outlook_sent_emails', ['user_id'])
    op.create_index('ix_scurry_outlook_sent_account_id', 'scurry_outlook_sent_emails', ['account_id'])
    op.create_index('ix_scurry_outlook_sent_status', 'scurry_outlook_sent_emails', ['status'])

    # Outlook Tracking Events
    op.create_table('scurry_outlook_tracking',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('email_id', sa.Integer(), sa.ForeignKey('scurry_outlook_sent_emails.id', ondelete='CASCADE'), nullable=False),
        sa.Column('event_type', sa.String(20), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('ip_address', sa.String(45), nullable=True),
        sa.Column('user_agent', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(), nullable=False, server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.CheckConstraint("event_type IN ('open', 'click')", name='ck_scurry_outlook_tracking_type'),
    )
    op.create_index('ix_scurry_outlook_tracking_email_id', 'scurry_outlook_tracking', ['email_id'])
    op.create_index('ix_scurry_outlook_tracking_type', 'scurry_outlook_tracking', ['event_type'])

def downgrade():
    op.drop_table('scurry_outlook_tracking')
    op.drop_table('scurry_outlook_sent_emails')
    op.drop_table('scurry_outlook_accounts')
    op.drop_table('scurry_email_tracking')
    op.drop_table('scurry_sent_emails')
    op.drop_table('scurry_email_accounts')
    op.drop_table('scurry_oauth_states')
    op.drop_table('scurry_users')
```

**IMPORTANT:** Since we're prefixing tables with `scurry_`, we need to update all PHP files to reference the new table names. The mapping is:
- `gmail_users` → `scurry_users`
- `oauth_states` → `scurry_oauth_states`
- `email_accounts` → `scurry_email_accounts`
- `sent_emails` → `scurry_sent_emails`
- `email_tracking` → `scurry_email_tracking`
- `outlook_accounts` → `scurry_outlook_accounts`
- `outlook_sent_emails` → `scurry_outlook_sent_emails`
- `outlook_tracking` → `scurry_outlook_tracking`

**Step 2: Update ALL PHP files to use new table names**

Do a search-and-replace across all `.php` files in `services/scurry-email/`:

| Old Table Name | New Table Name |
|---|---|
| `gmail_users` | `scurry_users` |
| `oauth_states` | `scurry_oauth_states` |
| `email_accounts` | `scurry_email_accounts` |
| `sent_emails` | `scurry_sent_emails` |
| `email_tracking` | `scurry_email_tracking` |
| `outlook_accounts` | `scurry_outlook_accounts` |
| `outlook_sent_emails` | `scurry_outlook_sent_emails` |
| `outlook_tracking` | `scurry_outlook_tracking` |

**Step 3: Run migration**

```bash
cd backend && python migrate.py
```

**Step 4: Verify tables exist**

```bash
docker compose exec postgres psql -U workflow_user -d workflow_platform -c "\dt scurry_*"
# Expected: 8 scurry_ tables listed
```

**Step 5: Commit**

```bash
git add backend/alembic/versions/015_add_scurry_email_tables.py services/scurry-email/
git commit -m "feat: add Alembic migration for scurry email tables and update PHP table references"
```

---

### Task 7: Add scurry-email service to docker-compose

**Files:**
- Modify: `docker-compose.yml`
- Modify: `docker-compose.prod.yml` (if exists)

**Step 1: Add scurry-email service to docker-compose.yml**

Add after the `frontend` service:

```yaml
  scurry-email:
    build: ./services/scurry-email
    environment:
      # Database (shared PostgreSQL)
      - DB_HOST=postgres
      - DB_PORT=5432
      - DB_NAME=workflow_platform
      - DB_USER=workflow_user
      - DB_PASS=workflow_pass
      # JWT Auth (validates against backend)
      - AUTH_API_URL=http://backend:9000/auth/me
      - JWT_VERIFY_METHOD=api
      # Google OAuth
      - GOOGLE_CLIENT_ID=${GOOGLE_CLIENT_ID:-}
      - GOOGLE_CLIENT_SECRET=${GOOGLE_CLIENT_SECRET:-}
      - GOOGLE_REDIRECT_URI=${GOOGLE_REDIRECT_URI:-}
      # Microsoft OAuth
      - MICROSOFT_CLIENT_ID=${MICROSOFT_CLIENT_ID:-}
      - MICROSOFT_CLIENT_SECRET=${MICROSOFT_CLIENT_SECRET:-}
      - MICROSOFT_REDIRECT_URI=${MICROSOFT_REDIRECT_URI:-}
      - MICROSOFT_TENANT=${MICROSOFT_TENANT:-common}
      # App URLs
      - SCURRY_APP_URL=${SCURRY_APP_URL:-http://localhost:8080}
      - SCURRY_OUTLOOK_APP_URL=${SCURRY_OUTLOOK_APP_URL:-http://localhost:8080/outlook}
      # Encryption
      - SCURRY_ENCRYPTION_KEY=${SCURRY_ENCRYPTION_KEY:-}
      - CORS_ALLOWED_ORIGINS=*
    depends_on:
      postgres:
        condition: service_healthy
    ports:
      - "8080:80"
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost/test.php"]
      interval: 30s
      timeout: 5s
      retries: 3
```

**Step 2: Commit**

```bash
git add docker-compose.yml
git commit -m "feat: add scurry-email service to docker-compose"
```

---

### Task 8: Update backend proxy URLs to point to local service

**Files:**
- Modify: `backend/gmail_proxy.py` (lines 31, 33)
- Modify: `backend/outlook_proxy.py` (lines 31, 33)
- Modify: `docker-compose.yml` (backend environment)

**Step 1: Update default URLs in gmail_proxy.py**

Change lines 31, 33:
```python
GMAIL_AUTH_URL = os.getenv("GMAIL_AUTH_URL", "http://backend:9000/api")
GMAIL_API_BASE_URL = os.getenv("GMAIL_API_BASE_URL", "http://scurry-email")
```

**Step 2: Update default URLs in outlook_proxy.py**

Change lines 31, 33:
```python
OUTLOOK_AUTH_URL = os.getenv("OUTLOOK_AUTH_URL", "http://backend:9000/api")
OUTLOOK_API_BASE_URL = os.getenv("OUTLOOK_API_BASE_URL", "http://scurry-email/outlook")
```

**Step 3: Fix Outlook proxy path inconsistencies**

The Outlook proxy currently calls:
- `f"{OUTLOOK_API_BASE_URL}/auth/outlook/connect.php"` — but with new base URL this becomes `/outlook/auth/outlook/connect.php` (wrong!)

Fix the paths in outlook_proxy.py to match actual file structure:
- `{OUTLOOK_API_BASE_URL}/auth/outlook/connect.php` → `{OUTLOOK_API_BASE_URL}/auth/connect.php`
- `{OUTLOOK_API_BASE_URL}/auth/outlook/disconnect.php` → `{OUTLOOK_API_BASE_URL}/auth/disconnect.php`
- `{OUTLOOK_API_BASE_URL}/email/send.php` stays the same (correct)
- `{OUTLOOK_API_BASE_URL}/email/accounts.php` stays the same (correct)

**Step 4: Add scurry-email dependency to backend in docker-compose.yml**

Add to backend's `depends_on`:
```yaml
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
      scurry-email:
        condition: service_healthy
```

**Step 5: Commit**

```bash
git add backend/gmail_proxy.py backend/outlook_proxy.py docker-compose.yml
git commit -m "feat: update backend proxy URLs to use local scurry-email service"
```

---

### Task 9: Update test.php health check and cleanup

**Files:**
- Modify: `services/scurry-email/test.php`

**Step 1: Simplify test.php as a health check endpoint**

The existing test.php is an HTML testing form. Add a simple JSON health check response when called with no browser:

Add at the top of test.php, before the HTML:
```php
<?php
// Health check for Docker
if (php_sapi_name() !== 'cli' && !isset($_GET['ui'])) {
    require_once __DIR__ . '/config.php';
    header('Content-Type: application/json');

    // Try DB connection
    try {
        require_once __DIR__ . '/db.php';
        $db = getDB();
        $db->query('SELECT 1');
        echo json_encode(['status' => 'healthy', 'service' => 'scurry-email', 'database' => 'connected']);
    } catch (Exception $e) {
        http_response_code(503);
        echo json_encode(['status' => 'unhealthy', 'service' => 'scurry-email', 'error' => $e->getMessage()]);
    }
    exit;
}
// ... existing HTML form below for ?ui mode
```

**Step 2: Commit**

```bash
git add services/scurry-email/test.php
git commit -m "feat: add health check endpoint to scurry-email test.php"
```

---

### Task 10: Build, run, and verify integration

**Step 1: Build all services**

```bash
docker compose build
# Expected: all services build successfully (timeout: 10 minutes)
```

**Step 2: Start services**

```bash
docker compose up -d
# Wait for all services to be healthy
docker compose ps
```

**Step 3: Run database migration**

```bash
docker compose exec backend python migrate.py
# Expected: migration 015 applied successfully
```

**Step 4: Verify scurry-email health**

```bash
curl http://localhost:8080/test.php
# Expected: {"status":"healthy","service":"scurry-email","database":"connected"}
```

**Step 5: Verify proxy integration**

```bash
# Test that backend can reach scurry-email (should get 401 without token, which proves connectivity)
docker compose exec backend curl -s http://scurry-email/email/accounts.php
# Expected: JSON response with "UNAUTHORIZED" error (proves the service is reachable and PHP is executing)
```

**Step 6: Verify tables**

```bash
docker compose exec postgres psql -U workflow_user -d workflow_platform -c "\dt scurry_*"
# Expected: 8 scurry_ tables
```

**Step 7: Final commit**

```bash
git add -A
git commit -m "feat: complete scurry-email dockerization and integration"
```
