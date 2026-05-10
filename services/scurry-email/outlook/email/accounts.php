<?php
/**
 * 🐿️ Scurry Outlook API - Email Accounts
 * 
 * GET /outlook/email/accounts.php - List all
 * GET /outlook/email/accounts.php?id=1 - Get by ID
 * GET /outlook/email/accounts.php?email=user@outlook.com - Find by email
 */

require_once __DIR__ . '/../auth.php';

setCorsHeaders();

$user = verifyAuth();
$pdo = getDbConnection();

$id = $_GET['id'] ?? null;
$email = $_GET['email'] ?? null;

if ($id) {
    // Get by ID
    $stmt = $pdo->prepare("SELECT id, email_address, display_name, is_active, token_expires_at, created_at 
                           FROM scurry_outlook_accounts 
                           WHERE id = ? AND user_id = ? AND is_active = 1");
    $stmt->execute([$id, $user['id']]);
    $account = $stmt->fetch();
    
    if (!$account) {
        errorResponse('NOT_FOUND', 'Account not found', 404);
    }
    
    jsonResponse([
        'success' => true,
        'data' => [
            'account_id' => (int)$account['id'],
            'email' => $account['email_address'],
            'display_name' => $account['display_name'],
            'is_active' => (bool)$account['is_active'],
            'token_expires_at' => $account['token_expires_at'],
            'created_at' => $account['created_at']
        ]
    ]);
    
} elseif ($email) {
    // Find by email
    $stmt = $pdo->prepare("SELECT id, email_address, display_name, is_active, created_at 
                           FROM scurry_outlook_accounts 
                           WHERE email_address = ? AND user_id = ? AND is_active = 1");
    $stmt->execute([$email, $user['id']]);
    $account = $stmt->fetch();
    
    if (!$account) {
        errorResponse('NOT_FOUND', 'Account not found for this email', 404);
    }
    
    jsonResponse([
        'success' => true,
        'data' => [
            'account_id' => (int)$account['id'],
            'email' => $account['email_address'],
            'display_name' => $account['display_name'],
            'is_active' => (bool)$account['is_active'],
            'created_at' => $account['created_at']
        ]
    ]);
    
} else {
    // List all
    $stmt = $pdo->prepare("SELECT id, email_address, display_name, is_active, token_expires_at, created_at 
                           FROM scurry_outlook_accounts 
                           WHERE user_id = ? AND is_active = 1
                           ORDER BY created_at DESC");
    $stmt->execute([$user['id']]);
    $accounts = $stmt->fetchAll();
    
    jsonResponse([
        'success' => true,
        'data' => [
            'accounts' => array_map(function($acc) {
                return [
                    'id' => (int)$acc['id'],
                    'email' => $acc['email_address'],
                    'display_name' => $acc['display_name'],
                    'is_active' => (bool)$acc['is_active'],
                    'created_at' => $acc['created_at']
                ];
            }, $accounts),
            'total' => count($accounts)
        ]
    ]);
}
