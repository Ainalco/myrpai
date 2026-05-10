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
