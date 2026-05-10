<?php
/**
 * 🐿️ Scurry Outlook API - Get Current User
 * 
 * GET /outlook/auth/user.php
 */

require_once __DIR__ . '/../auth.php';

setCorsHeaders();

$user = verifyAuth();

$pdo = getDbConnection();

// Get connected Outlook accounts
$stmt = $pdo->prepare("SELECT id, email_address, display_name, is_active, created_at 
                       FROM scurry_outlook_accounts 
                       WHERE user_id = ? AND is_active = 1");
$stmt->execute([$user['id']]);
$accounts = $stmt->fetchAll();

jsonResponse([
    'success' => true,
    'data' => [
        'user_id' => (int)$user['id'],
        'username' => $user['username'],
        'email' => $user['email'],
        'outlook_connected' => count($accounts) > 0,
        'scurry_outlook_accounts' => array_map(function($acc) {
            return [
                'id' => (int)$acc['id'],
                'email' => $acc['email_address'],
                'display_name' => $acc['display_name'],
                'connected_at' => $acc['created_at']
            ];
        }, $accounts)
    ]
]);
