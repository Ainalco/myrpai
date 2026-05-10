# 🐿️ Scurry Outlook API - Standalone

Complete Outlook/Microsoft 365 email integration - **completely separate from Gmail**.

## 📁 Structure

```
scurry_web/
└── outlook/                    ← Upload this entire folder
    ├── config.php              # Microsoft OAuth settings
    ├── db.php                  # Database helpers
    ├── auth.php                # JWT verification
    ├── auth/
    │   ├── connect.php         # Get OAuth URL
    │   ├── callback.php        # OAuth redirect handler
    │   ├── disconnect.php      # Remove account
    │   └── user.php            # Get current user
    ├── email/
    │   ├── accounts.php        # List accounts
    │   ├── send.php            # Send email
    │   ├── inbox.php           # Read inbox
    │   └── sent.php            # Sent history
    └── track/
        ├── open.php            # Track opens
        ├── click.php           # Track clicks
        ├── stats.php           # Statistics
        └── events.php          # Event list
```

---

## 🔧 Setup

### 1. Run SQL (Create Tables)
```sql
-- Run outlook_tables_v2.sql in phpMyAdmin
```

### 2. Upload `outlook/` Folder
Upload to: `/var/www/html/scurry_web/outlook/`

### 3. Edit `config.php`
```php
define('MICROSOFT_CLIENT_ID', 'your-client-id');
define('MICROSOFT_CLIENT_SECRET', 'your-secret');
```

### 4. Create Azure App
1. Go to [portal.azure.com](https://portal.azure.com)
2. **App registrations** → **New registration**
3. Redirect URI: `https://luaakserver.com/scurry_web/outlook/auth/callback.php`
4. Add permissions: `Mail.Read`, `Mail.Send`, `User.Read`, `offline_access`

---

## 🚀 API Endpoints

### Authentication
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/outlook/auth/user.php` | Get current user |
| GET | `/outlook/auth/connect.php` | Get OAuth URL |
| POST | `/outlook/auth/disconnect.php?account_id=1` | Disconnect |

### Email Accounts
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/outlook/email/accounts.php` | List all |
| GET | `/outlook/email/accounts.php?id=1` | Get by ID |
| GET | `/outlook/email/accounts.php?email=x@outlook.com` | Find by email |

### Send Email
| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/outlook/email/send.php` | Send email |

**Body:**
```json
{
  "account_id": 1,
  "to": "recipient@example.com",
  "to_name": "John Doe",
  "subject": "Hello!",
  "body": "<p>HTML content</p>",
  "cc": ["cc@example.com"],
  "bcc": ["bcc@example.com"],
  "track_opens": true,
  "track_clicks": true
}
```

### Read Inbox
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/outlook/email/inbox.php?account_id=1` | List inbox |
| GET | `/outlook/email/inbox.php?account_id=1&limit=50` | With limit |
| GET | `/outlook/email/inbox.php?account_id=1&folder=sent` | Sent folder |
| GET | `/outlook/email/inbox.php?account_id=1&search=invoice` | Search |
| GET | `/outlook/email/inbox.php?account_id=1&message_id=xxx` | Get full email |

**Folders:** `inbox`, `sent`, `drafts`, `deleted`, `junk`

### Sent History
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/outlook/email/sent.php` | List all |
| GET | `/outlook/email/sent.php?account_id=1` | By account |
| GET | `/outlook/email/sent.php?status=sent` | By status |

### Tracking
| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/outlook/track/stats.php` | Overall stats |
| GET | `/outlook/track/stats.php?email_id=1` | Email stats |
| GET | `/outlook/track/events.php?email_id=1` | Events |

---

## 🔑 Authentication

All endpoints require JWT token:
```
Authorization: Bearer YOUR_JWT_TOKEN
```

Get token from: `POST /doccer/aibot/api/auth/login`

---

## 📊 Database Tables

| Table | Purpose |
|-------|---------|
| `gmail_users` | Users (shared with Gmail) |
| `outlook_accounts` | Connected Outlook accounts |
| `outlook_sent_emails` | Sent email history |
| `outlook_tracking` | Open/click events |

---

*🐿️ Scurry - Faster than a caffeinated squirrel!*
