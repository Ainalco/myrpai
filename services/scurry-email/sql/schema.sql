-- ==============================================
-- 🐿️ Scurry Email API - Database Schema
-- ==============================================
-- Run this script to create all required tables
-- ==============================================

-- Gmail Users (mapped from your existing auth system)
CREATE TABLE IF NOT EXISTS gmail_users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    external_user_id INT NOT NULL UNIQUE COMMENT 'User ID from your auth system',
    username VARCHAR(255),
    email VARCHAR(255),
    created_at DATETIME NOT NULL,
    updated_at DATETIME DEFAULT NULL,
    INDEX idx_external_user_id (external_user_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- OAuth State Tokens (for CSRF protection during OAuth flow)
CREATE TABLE IF NOT EXISTS oauth_states (
    id INT AUTO_INCREMENT PRIMARY KEY,
    state_token VARCHAR(64) NOT NULL UNIQUE,
    user_id INT NOT NULL,
    created_at DATETIME NOT NULL,
    expires_at DATETIME NOT NULL,
    INDEX idx_state_token (state_token),
    INDEX idx_expires_at (expires_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Email Accounts (connected Gmail accounts)
CREATE TABLE IF NOT EXISTS email_accounts (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL COMMENT 'References gmail_users.id',
    provider VARCHAR(50) NOT NULL DEFAULT 'gmail',
    email_address VARCHAR(255) NOT NULL,
    display_name VARCHAR(255),
    access_token TEXT NOT NULL COMMENT 'Encrypted',
    refresh_token TEXT COMMENT 'Encrypted',
    token_expires_at DATETIME,
    scopes TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    last_sync_at DATETIME,
    sync_error TEXT,
    created_at DATETIME NOT NULL,
    updated_at DATETIME DEFAULT NULL,
    INDEX idx_user_id (user_id),
    INDEX idx_email_address (email_address),
    INDEX idx_is_active (is_active),
    UNIQUE KEY unique_user_email (user_id, email_address)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Sent Emails
CREATE TABLE IF NOT EXISTS sent_emails (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL COMMENT 'References gmail_users.id',
    account_id INT NOT NULL COMMENT 'References email_accounts.id',
    recipient_email VARCHAR(255) NOT NULL,
    recipient_name VARCHAR(255),
    cc JSON,
    bcc JSON,
    subject VARCHAR(1000) NOT NULL,
    body_html LONGTEXT NOT NULL,
    body_text LONGTEXT,
    gmail_message_id VARCHAR(255),
    gmail_thread_id VARCHAR(255),
    status ENUM('pending', 'sent', 'failed') DEFAULT 'pending',
    error_message TEXT,
    
    -- Tracking counters
    opens INT DEFAULT 0,
    clicks INT DEFAULT 0,
    first_opened_at DATETIME,
    last_opened_at DATETIME,
    first_clicked_at DATETIME,
    last_clicked_at DATETIME,
    
    -- Timestamps
    sent_at DATETIME,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    INDEX idx_user_id (user_id),
    INDEX idx_account_id (account_id),
    INDEX idx_status (status),
    INDEX idx_recipient (recipient_email),
    INDEX idx_sent_at (sent_at),
    INDEX idx_created_at (created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Email Tracking Events
CREATE TABLE IF NOT EXISTS email_tracking (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email_id INT NOT NULL COMMENT 'References sent_emails.id',
    event_type ENUM('open', 'click') NOT NULL,
    url TEXT COMMENT 'For click events',
    ip_address VARCHAR(45),
    user_agent TEXT,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_email_id (email_id),
    INDEX idx_event_type (event_type),
    INDEX idx_created_at (created_at),
    FOREIGN KEY (email_id) REFERENCES sent_emails(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- ==============================================
-- Clean up expired OAuth states (run periodically)
-- ==============================================
-- DELETE FROM oauth_states WHERE expires_at < NOW();

-- ==============================================
-- Sample queries
-- ==============================================

-- Get user's connected accounts:
-- SELECT * FROM email_accounts WHERE user_id = ? AND is_active = TRUE;

-- Get email stats:
-- SELECT 
--     COUNT(*) as total,
--     SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
--     SUM(opens) as total_opens,
--     SUM(clicks) as total_clicks
-- FROM sent_emails WHERE user_id = ?;

-- Get open rate:
-- SELECT 
--     COUNT(*) as total_sent,
--     SUM(CASE WHEN opens > 0 THEN 1 ELSE 0 END) as opened,
--     ROUND(SUM(CASE WHEN opens > 0 THEN 1 ELSE 0 END) / COUNT(*) * 100, 2) as open_rate
-- FROM sent_emails WHERE user_id = ? AND status = 'sent';
