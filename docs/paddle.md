# Scurry - Paddle Billing API

A PHP backend that integrates with Paddle for subscription billing and credit-based usage (acorns).

**Base URL:** `https://luaakserver.com/CRM_Squirrel/paddle`

---

## API Endpoints

| Method | Endpoint            | Auth             | Description                        |
| ------ | ------------------- | ---------------- | ---------------------------------- |
| GET    | `/api/auth`         | Bearer Token     | Get/create user from FastAPI token |
| GET    | `/api/balance`      | Bearer Token     | Check acorn balance                |
| POST   | `/api/spend`        | Bearer Token     | Deduct acorns                      |
| GET    | `/api/transactions` | Bearer Token     | View transaction history           |
| GET    | `/api/prices`       | None             | Get Paddle price IDs               |
| GET    | `/api/users`        | Bearer Token     | Get full user profile              |
| POST   | `/api/webhook`      | Paddle Signature | Paddle webhook endpoint            |

---

## Full URLs

```
https://luaakserver.com/CRM_Squirrel/paddle/api/auth
https://luaakserver.com/CRM_Squirrel/paddle/api/balance
https://luaakserver.com/CRM_Squirrel/paddle/api/spend
https://luaakserver.com/CRM_Squirrel/paddle/api/transactions
https://luaakserver.com/CRM_Squirrel/paddle/api/prices
https://luaakserver.com/CRM_Squirrel/paddle/api/users
https://luaakserver.com/CRM_Squirrel/paddle/api/webhook
https://luaakserver.com/CRM_Squirrel/paddle/checkout.php
```

---

## Step-by-Step: Postman Testing

### Step 1: Login to FastAPI (Get Bearer Token)

```
POST https://luaakserver.com/doccer/aibot/api/auth/login
```

**Headers:**
| Key | Value |
|-----|-------|
| Content-Type | application/json |

**Body (raw JSON):**

```json
{
  "username": "navid",
  "password": "your_password"
}
```

**Response:**

```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer"
}
```

**Save the `access_token` for next steps.**

---

### Step 2: Get/Create Paddle User

```
GET https://luaakserver.com/CRM_Squirrel/paddle/api/auth
```

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... |

**Response:**

```json
{
  "ok": true,
  "data": {
    "paddle_user_id": 1,
    "email": "navid@navid.com",
    "acorn_balance": 750,
    "plan_type": "sapling",
    "subscription_status": "trialing"
  }
}
```

**Save the `paddle_user_id` for checkout.**

---

### Step 3: Check Balance

```
GET https://luaakserver.com/CRM_Squirrel/paddle/api/balance
```

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... |

**Response:**

```json
{
  "ok": true,
  "data": {
    "user_id": 1,
    "email": "navid@navid.com",
    "acorn_balance": 750,
    "plan_type": "sapling",
    "billing_cycle": "monthly",
    "subscription_status": "trialing",
    "trial_started_at": "2025-12-28 06:08:58",
    "current_period_ends_at": null
  }
}
```

---

### Step 4: Spend Acorns

```
POST https://luaakserver.com/CRM_Squirrel/paddle/api/spend
```

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... |
| Content-Type | application/json |

**Body (raw JSON):**

```json
{
  "cost": 10,
  "description": "AI image generation"
}
```

**Response (Success):**

```json
{
  "ok": true,
  "spent": 10,
  "new_balance": 740,
  "description": "AI image generation"
}
```

**Response (Insufficient Balance):**

```json
{
  "error": "Insufficient acorns",
  "required": 10,
  "available": 5
}
```

---

### Step 5: View Transaction History

```
GET https://luaakserver.com/CRM_Squirrel/paddle/api/transactions?limit=20&offset=0
```

**Headers:**
| Key | Value |
|-----|-------|
| Authorization | Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9... |

**Response:**

```json
{
  "ok": true,
  "data": {
    "transactions": [
      {
        "id": 1,
        "user_id": 1,
        "amount": 250,
        "type": "trial_credit",
        "description": "Trial started",
        "paddle_transaction_id": null,
        "created_at": "2025-12-28 06:08:58"
      },
      {
        "id": 2,
        "user_id": 1,
        "amount": 500,
        "type": "subscription_payment",
        "description": "Subscription: sapling plan",
        "paddle_transaction_id": "txn_01kdhs529n28eh3bxyf0pezyw3",
        "created_at": "2025-12-28 06:08:59"
      }
    ],
    "pagination": {
      "total": 2,
      "limit": 20,
      "offset": 0,
      "has_more": false
    }
  }
}
```

---

### Step 6: Get Price IDs (Public - No Auth)

```
GET https://luaakserver.com/CRM_Squirrel/paddle/api/prices
```

**Response:**

```json
{
  "ok": true,
  "environment": "sandbox",
  "plans": {
    "sapling_monthly": "pri_01kdeyd4a823hp4qv791vfnyfy",
    "sapling_annual": "pri_01kdeyzxdyk67cftesxq61fg33",
    "oak_monthly": "pri_01kdeycc38vntkcwe5sym9wdtw",
    "oak_annual": "pri_01kdez3pay1y4ry41v09q939gc",
    "redwood_monthly": "pri_01kdez6v8sagwket6b29e3hvv6",
    "redwood_annual": "pri_01kdez6v8sagwket6b29e3hvv6"
  },
  "topups": {
    "acorns_500": "pri_01kdez9z3vd36cttj572d74gae",
    "acorns_1750": "pri_01kdezavv140gmtysfk1dtwem1",
    "acorns_4000": "pri_01kdezbgqavm1770k63mtw1b4v"
  }
}
```

---

## Step-by-Step: Website Purchase

### Step 1: Open Checkout Page

```
https://luaakserver.com/CRM_Squirrel/paddle/checkout.php
```

### Step 2: Enter User ID

- Enter the `paddle_user_id` from `/api/auth` response
- Example: `1`

### Step 3: Select Plan or Top-up

Click any button:

- **Sapling Monthly/Annual** - 500 acorns/month
- **Oak Monthly/Annual** - 1,750 acorns/month
- **Redwood Monthly/Annual** - 4,000 acorns/month
- **Top-ups** - One-time purchase (500, 1750, 4000 acorns)

### Step 4: Complete Payment

**Test Card:**

```
Card Number: 4242 4242 4242 4242
Expiry: Any future date (e.g., 12/27)
CVV: Any 3 digits (e.g., 123)
Name: Anything
```

### Step 5: Verify Acorns Added

After payment, check balance:

```
GET https://luaakserver.com/CRM_Squirrel/paddle/api/balance
```

---

## Credit System

### Subscription Plans

| Plan    | Monthly Acorns | Trial Credit |
| ------- | -------------- | ------------ |
| Sapling | 500            | +250         |
| Oak     | 1,750          | +250         |
| Redwood | 4,000          | +250         |

### One-Time Top-ups

| Package | Acorns |
| ------- | ------ |
| Small   | 500    |
| Medium  | 1,750  |
| Large   | 4,000  |

---

## Webhook Events

| Event                    | Action                                                  |
| ------------------------ | ------------------------------------------------------- |
| `subscription.created`   | Sets plan, status; gives +250 trial credits if trialing |
| `subscription.activated` | Updates status to active                                |
| `subscription.canceled`  | Updates status, sets end date                           |
| `subscription.past_due`  | Updates status to past_due                              |
| `subscription.updated`   | Updates plan/cycle on changes                           |
| `transaction.completed`  | Credits acorns (subscription or top-up)                 |
| `adjustment.created`     | Handles refunds - deducts credited acorns               |

---

## Integration Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                        YOUR APPLICATION                          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  1. User Login                                                   │
│     POST /doccer/aibot/api/auth/login                           │
│     → Returns: access_token                                      │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. Get Paddle User                                              │
│     GET /CRM_Squirrel/paddle/api/auth                           │
│     Header: Authorization: Bearer {access_token}                 │
│     → Returns: paddle_user_id, acorn_balance                     │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. Open Paddle Checkout (if user wants to buy)                  │
│     Paddle.Checkout.open({                                       │
│       items: [{ priceId: 'pri_xxx', quantity: 1 }],              │
│       customData: { user_id: paddle_user_id }                    │
│     });                                                          │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. Paddle Webhook (automatic)                                   │
│     POST /CRM_Squirrel/paddle/api/webhook                       │
│     → Adds acorns to user account                                │
└─────────────────────────────────────────────────────────────────┘
                                │
                                ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. Use Features (deduct acorns)                                 │
│     POST /CRM_Squirrel/paddle/api/spend                         │
│     Header: Authorization: Bearer {access_token}                 │
│     Body: { "cost": 10, "description": "Feature used" }          │
│     → Returns: new_balance                                       │
└─────────────────────────────────────────────────────────────────┘
```

---

## File Structure

```
/CRM_Squirrel/paddle/
├── .env                    # Environment config
├── .htaccess               # Apache routing & security
├── checkout.php            # Test checkout page
├── schema.sql              # Database schema
├── README.md               # This file
└── api/
    ├── index.php           # Router
    ├── bootstrap.php       # Init & CORS
    ├── helpers.php         # Utility functions
    ├── db.php              # Database connection
    ├── auth.php            # GET /api/auth
    ├── balance.php         # GET /api/balance
    ├── spend.php           # POST /api/spend
    ├── transactions.php    # GET /api/transactions
    ├── prices.php          # GET /api/prices
    ├── users.php           # GET /api/users
    └── webhook.php         # POST /api/webhook
```

---

## Environment Variables (.env)

```env
DB_HOST=127.0.0.1
DB_NAME=Paddle
DB_USER=your_db_user
DB_PASS=your_db_password
ADMIN_SECRET_KEY=your_admin_key
FASTAPI_ME_URL=https://luaakserver.com/doccer/aibot/api/auth/me

PADDLE_ENVIRONMENT=sandbox
PADDLE_CLIENT_TOKEN=test_xxx
PADDLE_WEBHOOK_SECRET=pdl_ntfset_xxx

PADDLE_PRICE_SAPLING_MONTHLY=pri_xxx
PADDLE_PRICE_SAPLING_ANNUAL=pri_xxx
PADDLE_PRICE_OAK_MONTHLY=pri_xxx
PADDLE_PRICE_OAK_ANNUAL=pri_xxx
PADDLE_PRICE_REDWOOD_MONTHLY=pri_xxx
PADDLE_PRICE_REDWOOD_ANNUAL=pri_xxx

PADDLE_PRICE_ACORNS_500=pri_xxx
PADDLE_PRICE_ACORNS_1750=pri_xxx
PADDLE_PRICE_ACORNS_4000=pri_xxx
```

---

## Security Notes

- `.env` is blocked from web access via `.htaccess`
- All authenticated endpoints require valid Bearer token
- Webhook signature is verified before processing
- Database uses prepared statements (no SQL injection)
- Idempotency check prevents duplicate webhook processing

---

## Paddle Dashboard Setup

1. **Products & Prices:** Catalog → Products → Create subscription and one-time products
2. **Webhook:** Developer Tools → Notifications → Add webhook URL
3. **Events:** Select subscription.created, subscription.activated, subscription.canceled, subscription.past_due, subscription.updated, transaction.completed, adjustment.created
4. **Usage Type:** Set to "Platform and simulation"
5. **Client Token:** Developer Tools → Authentication → Copy client-side token
