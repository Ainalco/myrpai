<?php
/**
 * 🐿️ Scurry Email API - Get Current User
 * 
 * GET /auth/user.php
 * 
 * Headers:
 *   Authorization: Bearer {jwt_token}
 * 
 * Returns user info and Gmail connection status
 */

require_once __DIR__ . '/../auth.php';

// Require authentication
$user = requireAuth();

$db = getDB();

// Check if user has connected Gmail accounts
$stmt = $db->prepare("
    SELECT id, email_address, display_name, is_active, created_at
    FROM scurry_email_accounts 
    WHERE user_id = ? AND is_active = TRUE
");
$stmt->execute([$user['gmail_user_id']]);
$accounts = $stmt->fetchAll();

jsonResponse([
    'success' => true,
    'data' => [
        'user_id' => $user['gmail_user_id'],
        'external_user_id' => $user['user_id'],
        'username' => $user['username'],
        'email' => $user['email'],
        'gmail_connected' => count($accounts) > 0,
        'gmail_accounts' => $accounts
    ]
]);
