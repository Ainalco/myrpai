# 🐿️ Scurry Gmail API

Send emails via Gmail with open/click tracking, using your existing JWT authentication.

---

## Quick Start

### 1. Configure

Edit `config.php`:

```php
// Database
define('DB_HOST', 'localhost');
define('DB_NAME', 'your_database');
define('DB_USER', 'your_user');
define('DB_PASS', 'your_password');

// JWT - Use 'api' to verify via your existing auth endpoint
define('JWT_VERIFY_METHOD', 'api');
define('AUTH_API_URL', 'https://luaakserver.com/doccer/aibot/api/auth/me');

// Google OAuth (already configured)
define('GOOGLE_CLIENT_ID', '...');
define('GOOGLE_CLIENT_SECRET', '...');
define('GOOGLE_REDIRECT_URI', 'https://luaakserver.com/scurry_web/auth/gmail/callback.php');

// Generate encryption key: echo base64_encode(random_bytes(32));
define('ENCRYPTION_KEY', 'your_32_byte_key_here');
```

### 2. Create Database Tables

```bash
mysql -u your_user -p your_database < sql/schema.sql
```

### 3. Upload to Server

Upload all files to: `https://luaakserver.com/scurry_web/`

---

## API Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                         YOUR APP                                 │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 1: Login to your existing system                           │
│                                                                  │
│ POST /doccer/aibot/api/auth/login                               │
│ Body: { "username": "navid", "password": "xxx" }                │
│ Response: { "access_token": "eyJ..." }                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 2: Get user info & Gmail status                            │
│                                                                  │
│ GET /scurry_web/auth/user.php                                   │
│ Headers: Authorization: Bearer eyJ...                            │
│ Response: { gmail_connected: false, gmail_accounts: [] }        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 3: Connect Gmail (if not connected)                        │
│                                                                  │
│ GET /scurry_web/auth/gmail/connect.php                          │
│ Headers: Authorization: Bearer eyJ...                            │
│ Response: { auth_url: "https://accounts.google.com/..." }       │
│                                                                  │
│ → Open auth_url in browser                                      │
│ → User authorizes                                                │
│ → Google redirects to callback                                   │
│ → Account connected!                                             │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 4: Send Email                                              │
│                                                                  │
│ POST /scurry_web/email/send.php                                 │
│ Headers: Authorization: Bearer eyJ...                            │
│ Body: {                                                          │
│   "account_id": 1,                                              │
│   "to": "recipient@example.com",                                │
│   "subject": "Hello!",                                          │
│   "body_html": "<p>Test</p>"                                    │
│ }                                                                │
│ Response: { email_id: 1, message_id: "...", sent_at: "..." }    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│ Step 5: Track Opens & Clicks                                    │
│                                                                  │
│ GET /scurry_web/track/stats.php?email_id=1                      │
│ Headers: Authorization: Bearer eyJ...                            │
│ Response: { opens: 3, clicks: 1, open_rate: 100% }              │
└─────────────────────────────────────────────────────────────────┘
```

---

## API Endpoints

### Authentication

All endpoints require JWT token in Authorization header:
```
Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...
```

---

### Get Current User

```http
GET /auth/user.php
```

**Response:**
```json
{
  "success": true,
  "data": {
    "user_id": 1,
    "external_user_id": 123,
    "username": "navid",
    "gmail_connected": true,
    "gmail_accounts": [
      {
        "id": 1,
        "email_address": "navid@gmail.com",
        "display_name": "Navid",
        "is_active": true
      }
    ]
  }
}
```

---

### Connect Gmail

```http
GET /auth/gmail/connect.php
```

**Response:**
```json
{
  "success": true,
  "data": {
    "auth_url": "https://accounts.google.com/o/oauth2/v2/auth?...",
    "instructions": "Open auth_url in browser to connect Gmail account"
  }
}
```

Open `auth_url` in a popup or new tab. After authorization, user is redirected to callback and sees success page.

---

### Disconnect Gmail

```http
POST /auth/gmail/disconnect.php
Content-Type: application/json

{
  "account_id": 1
}
```

**Response:**
```json
{
  "success": true,
  "message": "Gmail account disconnected successfully",
  "data": {
    "account_id": 1,
    "email_address": "navid@gmail.com"
  }
}
```

---

### List Email Accounts

```http
GET /email/accounts.php
```

**Response:**
```json
{
  "success": true,
  "data": {
    "accounts": [
      {
        "id": 1,
        "provider": "gmail",
        "email_address": "navid@gmail.com",
        "display_name": "Navid",
        "is_active": true,
        "token_status": "valid",
        "token_expires_in": 3200
      }
    ],
    "total": 1
  }
}
```

---

### Send Email

```http
POST /email/send.php
Content-Type: application/json

{
  "account_id": 1,
  "to": "recipient@example.com",
  "to_name": "John Doe",
  "subject": "Meeting Follow-up",
  "body_html": "<h1>Hello!</h1><p>Thanks for the meeting.</p>",
  "body_text": "Hello! Thanks for the meeting.",
  "cc": ["cc@example.com"],
  "bcc": ["bcc@example.com"],
  "track_opens": true,
  "track_clicks": true
}
```

**Response:**
```json
{
  "success": true,
  "data": {
    "email_id": 42,
    "message_id": "18d5a1234567890",
    "thread_id": "18d5a1234567890",
    "from": "navid@gmail.com",
    "to": "recipient@example.com",
    "subject": "Meeting Follow-up",
    "tracking": {
      "opens": true,
      "clicks": true
    },
    "sent_at": "2025-01-05T10:30:00+00:00"
  }
}
```

---

### List Sent Emails

```http
GET /email/sent.php?account_id=1&status=sent&limit=50&offset=0
```

**Query Parameters:**
| Parameter | Type | Description |
|-----------|------|-------------|
| account_id | int | Filter by account (optional) |
| status | string | Filter: sent, failed, pending (optional) |
| limit | int | Results per page (default: 50, max: 100) |
| offset | int | Pagination offset (default: 0) |

**Response:**
```json
{
  "success": true,
  "data": {
    "emails": [
      {
        "id": 42,
        "account_id": 1,
        "from_email": "navid@gmail.com",
        "recipient_email": "john@example.com",
        "subject": "Meeting Follow-up",
        "status": "sent",
        "opens": 3,
        "clicks": 1,
        "first_opened_at": "2025-01-05T11:00:00",
        "sent_at": "2025-01-05T10:30:00"
      }
    ],
    "pagination": {
      "total": 150,
      "limit": 50,
      "offset": 0,
      "has_more": true
    }
  }
}
```

---

### Get Tracking Stats

```http
GET /track/stats.php?email_id=42
```

**For specific email:**
```json
{
  "success": true,
  "data": {
    "email_id": 42,
    "subject": "Meeting Follow-up",
    "recipient": "john@example.com",
    "sent_at": "2025-01-05T10:30:00",
    "stats": {
      "opens": 3,
      "clicks": 1,
      "first_opened_at": "2025-01-05T11:00:00",
      "last_opened_at": "2025-01-05T14:30:00",
      "unique_clicks": [
        { "url": "https://example.com/link", "clicks": 1 }
      ]
    }
  }
}
```

**Overall stats (no email_id):**
```http
GET /track/stats.php?days=30&account_id=1
```

```json
{
  "success": true,
  "data": {
    "period_days": 30,
    "summary": {
      "total_emails": 150,
      "sent": 145,
      "failed": 5,
      "total_opens": 234,
      "total_clicks": 89,
      "emails_opened": 98,
      "emails_clicked": 45,
      "open_rate": 67.59,
      "click_rate": 31.03
    },
    "daily": [
      { "date": "2025-01-05", "sent": 12, "opens": 8, "clicks": 3 }
    ]
  }
}
```

---

### Get Tracking Events

```http
GET /track/events.php?email_id=42&event_type=click&limit=100
```

**Response:**
```json
{
  "success": true,
  "data": {
    "email": {
      "id": 42,
      "subject": "Meeting Follow-up",
      "recipient": "john@example.com"
    },
    "events": [
      {
        "id": 1,
        "event_type": "open",
        "url": null,
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0...",
        "created_at": "2025-01-05T11:00:00"
      },
      {
        "id": 2,
        "event_type": "click",
        "url": "https://example.com/link",
        "ip_address": "192.168.1.1",
        "user_agent": "Mozilla/5.0...",
        "created_at": "2025-01-05T11:01:00"
      }
    ],
    "pagination": {
      "total": 4,
      "limit": 100,
      "offset": 0,
      "has_more": false
    }
  }
}
```

---

## Error Responses

All errors follow this format:

```json
{
  "success": false,
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message"
  }
}
```

**Common Error Codes:**

| Code | HTTP | Description |
|------|------|-------------|
| UNAUTHORIZED | 401 | Missing or invalid JWT token |
| VALIDATION_ERROR | 400 | Missing required field |
| ACCOUNT_NOT_FOUND | 404 | Email account not found |
| EMAIL_NOT_FOUND | 404 | Email not found |
| SEND_FAILED | 500 | Gmail API error |
| TOKEN_REFRESH_FAILED | 500 | Need to reconnect Gmail |

---

## Tracking Implementation

### How Open Tracking Works

When `track_opens: true`, we inject a 1x1 transparent pixel:
```html
<img src="https://luaakserver.com/scurry_web/track/open.php?id=42" width="1" height="1" />
```

When email is opened and images load, the pixel is requested and we log the event.

**Accuracy:** ~60-70% (many email clients block images by default)

### How Click Tracking Works

When `track_clicks: true`, we replace links:
```html
<!-- Original -->
<a href="https://example.com">Click here</a>

<!-- Tracked -->
<a href="https://luaakserver.com/scurry_web/track/click.php?id=42&url=https%3A%2F%2Fexample.com">Click here</a>
```

When clicked, we log the event and redirect to the original URL.

**Accuracy:** ~95%+ (very reliable)

---

## Gmail Limits

| Account Type | Daily Limit |
|--------------|-------------|
| Free Gmail | 500 emails/day |
| Google Workspace | 2,000 emails/day |

---

## File Structure

```
scurry_gmail_api/
├── config.php              # Configuration
├── db.php                  # Database helpers
├── auth.php                # JWT middleware
├── auth/
│   ├── user.php           # Get current user
│   └── gmail/
│       ├── connect.php    # Start OAuth flow
│       ├── callback.php   # OAuth callback
│       └── disconnect.php # Disconnect account
├── email/
│   ├── accounts.php       # List accounts
│   ├── send.php           # Send email
│   └── sent.php           # List sent emails
├── track/
│   ├── open.php           # Open pixel
│   ├── click.php          # Click redirect
│   ├── stats.php          # Statistics
│   └── events.php         # Individual events
├── sql/
│   └── schema.sql         # Database schema
└── README.md              # This file
```

---

## Frontend Integration Example

```javascript
// 1. Login to get JWT token
const loginResponse = await fetch('https://luaakserver.com/doccer/aibot/api/auth/login', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({ username: 'navid', password: 'xxx' })
});
const { access_token } = await loginResponse.json();

// 2. Check Gmail status
const userResponse = await fetch('https://luaakserver.com/scurry_web/auth/user.php', {
  headers: { 'Authorization': `Bearer ${access_token}` }
});
const userData = await userResponse.json();

// 3. Connect Gmail if needed
if (!userData.data.gmail_connected) {
  const connectResponse = await fetch('https://luaakserver.com/scurry_web/auth/gmail/connect.php', {
    headers: { 'Authorization': `Bearer ${access_token}` }
  });
  const { data } = await connectResponse.json();
  
  // Open in popup
  window.open(data.auth_url, 'gmail_connect', 'width=600,height=700');
}

// 4. Send email
const sendResponse = await fetch('https://luaakserver.com/scurry_web/email/send.php', {
  method: 'POST',
  headers: {
    'Authorization': `Bearer ${access_token}`,
    'Content-Type': 'application/json'
  },
  body: JSON.stringify({
    account_id: 1,
    to: 'recipient@example.com',
    subject: 'Hello!',
    body_html: '<p>Test email</p>'
  })
});
const result = await sendResponse.json();
console.log('Email sent:', result.data.email_id);
```

---

## Support

Questions? Contact the Scurry team! 🐿️
