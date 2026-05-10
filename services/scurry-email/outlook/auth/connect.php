<?php
/**
 * 🐿️ Scurry Outlook API - Connect Account
 * 
 * GET /outlook/auth/connect.php
 * Returns Microsoft OAuth URL
 */

require_once __DIR__ . '/../auth.php';

setCorsHeaders();

$user = verifyAuth();

// Generate state token
$state = base64UrlEncode(json_encode([
    'user_id' => $user['id'],
    'timestamp' => time()
]));

// Store state in session
session_start();
$_SESSION['outlook_oauth_state'] = $state;

// Build Microsoft OAuth URL
$params = [
    'client_id' => MICROSOFT_CLIENT_ID,
    'response_type' => 'code',
    'redirect_uri' => MICROSOFT_REDIRECT_URI,
    'response_mode' => 'query',
    'scope' => MICROSOFT_SCOPES,
    'state' => $state,
    'prompt' => 'consent'
];

$authUrl = MICROSOFT_AUTHORIZE_URL . '?' . http_build_query($params);

jsonResponse([
    'success' => true,
    'auth_url' => $authUrl,
    'message' => 'Open this URL in browser to connect your Outlook account'
]);
