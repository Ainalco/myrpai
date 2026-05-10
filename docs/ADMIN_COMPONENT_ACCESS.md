# Admin Guide: Managing Component Access

This document explains how to manage user access to advanced components in the workflow platform.

## Overview

The platform uses a feature flag system to control access to advanced/power-user components. Users with `enable_advanced_components = true` can see and use all component types, while regular users only see basic components.

## Component Classification

All current components are marked as **non-advanced** (`is_advanced: False`), meaning they are visible to all users:

- **Input Sources** - External data source
- **Text Generation** - Generate summaries, subject lines, or any text
- **Email** - Generate and send follow-up emails
- **Conditional Logic** - Filter based on conditions
- **AI Filter** - Filter based on AI analysis
- **Action** - Push data to external systems (Pipedrive, etc.)

### Adding Advanced Components

When adding new component types to the system, set `is_advanced: True` in the `COMPONENT_TYPES` dictionary in `backend/components.py` to restrict them to power users:

```python
COMPONENT_TYPES = {
    # ... existing components ...
    "webhook": {
        "name": "Webhook",
        "description": "Trigger external webhooks",
        "icon": "webhook",
        "category": "action",
        "is_advanced": True  # Only visible to power users
    }
}
```

## Managing User Access

### Enable Advanced Components for a User

Connect to the PostgreSQL database and run:

```sql
-- Enable advanced components for a specific user by email
UPDATE users
SET enable_advanced_components = true
WHERE email = 'user@example.com';

-- Enable for a specific user by ID
UPDATE users
SET enable_advanced_components = true
WHERE id = 123;
```

### Disable Advanced Components for a User

```sql
-- Disable advanced components
UPDATE users
SET enable_advanced_components = false
WHERE email = 'user@example.com';
```

### List All Power Users

```sql
-- View all users with advanced component access
SELECT id, email, username, full_name, enable_advanced_components, created_at
FROM users
WHERE enable_advanced_components = true
ORDER BY created_at DESC;
```

### Check a Specific User's Access Level

```sql
-- Check if a user has advanced access
SELECT id, email, username, enable_advanced_components
FROM users
WHERE email = 'user@example.com';
```

## Database Connection

### Using Docker

```bash
# Connect to PostgreSQL via Docker
docker compose exec postgres psql -U workflow_user -d workflow_platform

# Or run SQL directly
docker compose exec postgres psql -U workflow_user -d workflow_platform -c "UPDATE users SET enable_advanced_components = true WHERE email = 'user@example.com';"
```

### Direct Connection

If connecting directly to PostgreSQL:

```bash
# Using psql client
psql -h localhost -U workflow_user -d workflow_platform

# Then run SQL commands
UPDATE users SET enable_advanced_components = true WHERE email = 'user@example.com';
```

Connection details (from `.env`):

- Host: `localhost` (or service name if via Docker network)
- Port: `5432`
- Database: `workflow_platform`
- User: `workflow_user`
- Password: See `POSTGRES_PASSWORD` in `.env` file

## Default Access Level

- **New users**: Default to `enable_advanced_components = false` (restricted)
- **Existing users**: After migration, default to `false` (restricted)

To grant access to existing users, run the SQL update commands above.

## Verification

After updating user permissions:

1. **User logs out and back in** (to refresh JWT token)
2. **Frontend automatically fetches** available components from API
3. **Advanced components appear** (if flag = true) or are hidden (if flag = false)

Test by:

1. Opening the workflow builder
2. Clicking "Add Component" button
3. Checking which component types are shown in the dialog

## Troubleshooting

### User doesn't see advanced components after enabling flag

1. Verify the database change:

   ```sql
   SELECT enable_advanced_components FROM users WHERE email = 'user@example.com';
   ```

2. Ask user to log out and log back in (to refresh JWT token with new permissions)

3. Check browser console for errors

4. Verify backend is using the updated code:
   ```bash
   docker compose logs backend -f | grep "component"
   ```

### Components not filtering correctly

1. Check the `GET /components/types` endpoint in backend logs
2. Verify `is_advanced` metadata is set correctly in `COMPONENT_TYPES`
3. Check frontend is calling the API (not using cached/hardcoded list)

## Security Notes

- The `is_advanced` flag is a soft restriction for UX purposes
- Users can still interact with advanced components via API if they know the component type
- This is NOT a security boundary - it's a UX feature to prevent confusion
- For true access control, implement backend validation in component creation/execution endpoints

## Migration History

- **Migration 009**: Added `enable_advanced_components` column to `users` table
- **Default**: `false` (restricted)
- **Applied**: 2025-11-08

## Future Enhancements

Potential improvements to the access control system:

1. **Admin UI**: Build a user management page in the frontend for easier access control
2. **Role-based System**: Add full RBAC with roles like "basic", "power", "admin"
3. **Component-level Permissions**: Allow granular control per component type
4. **Audit Logging**: Track when access levels are changed and by whom
5. **Self-service Requests**: Let users request power access, admins approve via UI

Grant Advanced Permissions by Email

docker compose exec postgres psql -U workflow_user -d workflow_platform -c "UPDATE
users SET enable_advanced_components = true WHERE email = 'user@example.com';"

Replace user@example.com with the actual user's email.

---

Alternative: Grant by User ID

docker compose exec postgres psql -U workflow_user -d workflow_platform -c "UPDATE
users SET enable_advanced_components = true WHERE id = 1;"

Replace 1 with the actual user ID.

---

Verify the Change

docker compose exec postgres psql -U workflow_user -d workflow_platform -c "SELECT
id, email, username, enable_advanced_components FROM users WHERE email =
'user@example.com';"

Should show t (true) in the enable_advanced_components column.

---

Revoke Advanced Permissions

docker compose exec postgres psql -U workflow_user -d workflow_platform -c "UPDATE
users SET enable_advanced_components = false WHERE email = 'user@example.com';"

---

List All Power Users

docker compose exec postgres psql -U workflow_user -d workflow_platform -c "SELECT
id, email, username, enable_advanced_components FROM users WHERE
enable_advanced_components = true;"
