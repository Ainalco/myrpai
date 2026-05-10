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

// DATABASE SETTINGS (shared with parent - guard against redefinition)
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
