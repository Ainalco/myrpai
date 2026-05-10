# Scurry Email Service Dockerization Design

**Date**: 2026-03-02
**Status**: Approved

## Goal

Dockerize the scurry_web PHP email API, move it to `services/scurry-email/`, migrate from MySQL to the existing PostgreSQL database, and integrate it into the docker-compose stack.

## Current State

- `scurry_web/` is a standalone PHP app providing Gmail + Outlook OAuth email integration with open/click tracking
- Currently deployed externally at `luaakserver.com`
- Backend proxies to it via `gmail_proxy.py` and `outlook_proxy.py`
- Uses MySQL with its own database (`scurry_email`)

## Target State

- `services/scurry-email/` with Dockerfile (PHP 8.1 + Apache)
- Runs as `scurry-email` service in docker-compose
- Uses existing PostgreSQL database (new tables via Alembic migration)
- Backend proxies to `http://scurry-email:8080/` instead of external URL
- Environment-variable-driven configuration

## Changes

### 1. File Relocation
- `scurry_web/` → `services/scurry-email/`
- Add `Dockerfile`, `.htaccess`, `.dockerignore`

### 2. PHP Code Changes (MySQL → PostgreSQL)
- `db.php`: PDO driver `mysql` → `pgsql`, connection string format
- All SQL files: `AUTO_INCREMENT` → `SERIAL`, backtick quoting → standard SQL, `NOW()` → `CURRENT_TIMESTAMP`
- `config.php`: Read from environment variables
- `outlook/config.php`: Same environment variable approach

### 3. Database Migration
- Alembic migration adding 8 tables: `gmail_users`, `email_accounts`, `sent_emails`, `email_tracking`, `oauth_states`, `outlook_accounts`, `outlook_sent_emails`, `outlook_tracking`

### 4. Docker Integration
- New `scurry-email` service in `docker-compose.yml` and `docker-compose.prod.yml`
- PHP 8.1-Apache image with pdo_pgsql, curl, openssl extensions
- Depends on postgres service
- Environment variables for DB, OAuth, JWT, encryption

### 5. Backend Proxy Update
- `gmail_proxy.py`: `GMAIL_API_BASE_URL` → `http://scurry-email:8080`
- `outlook_proxy.py`: `OUTLOOK_API_BASE_URL` → `http://scurry-email:8080/outlook`

### 6. Frontend/Nginx (Production)
- Add `/scurry/` proxy route for OAuth callbacks and tracking pixels
