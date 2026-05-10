<?php
/**
 * 🐿️ Scurry Email API - Connect Gmail
 * 
 * GET /auth/gmail/connect.php
 * 
 * Headers:
 *   Authorization: Bearer {jwt_token}
 * 
 * Returns Google OAuth URL
 */

require_once __DIR__ . '/../../auth.php';

// Require authentication
$user = requireAuth();

// Generate state token (includes user_id for callback)
$stateData = [
    'user_id' => $user['gmail_user_id'],
    'csrf' => bin2hex(random_bytes(16)),
    'timestamp' => time()
];
$state = base64_encode(json_encode($stateData));

// Store state in session or database for validation
$db = getDB();
$stmt = $db->prepare("
    INSERT INTO scurry_oauth_states (state_token, user_id, created_at, expires_at)
    VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '10 minutes')
");
$stmt->execute([$stateData['csrf'], $user['gmail_user_id']]);

// Build Google OAuth URL
$scopes = [
    'https://www.googleapis.com/auth/gmail.send',
    'https://www.googleapis.com/auth/gmail.readonly',
    'https://www.googleapis.com/auth/userinfo.email',
    'https://www.googleapis.com/auth/userinfo.profile'
];

$authUrl = 'https://accounts.google.com/o/oauth2/v2/auth?' . http_build_query([
    'client_id' => GOOGLE_CLIENT_ID,
    'redirect_uri' => GOOGLE_REDIRECT_URI,
    'response_type' => 'code',
    'scope' => implode(' ', $scopes),
    'access_type' => 'offline',
    'prompt' => 'consent',
    'state' => $state
]);

jsonResponse([
    'success' => true,
    'data' => [
        'auth_url' => $authUrl,
        'instructions' => 'Open auth_url in browser to connect Gmail account'
    ]
]);
