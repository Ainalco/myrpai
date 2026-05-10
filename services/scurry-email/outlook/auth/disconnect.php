<?php
/**
 * 🐿️ Scurry Outlook API - Disconnect Account
 * 
 * POST /outlook/auth/disconnect.php?account_id=1
 */

require_once __DIR__ . '/../auth.php';

setCorsHeaders();

$user = verifyAuth();

$accountId = $_GET['account_id'] ?? $_POST['account_id'] ?? null;

if (!$accountId) {
    errorResponse('MISSING_PARAM', 'account_id is required', 400);
}

$pdo = getDbConnection();

// Verify account belongs to user
$stmt = $pdo->prepare("SELECT * FROM scurry_outlook_accounts WHERE id = ? AND user_id = ?");
$stmt->execute([$accountId, $user['id']]);
$account = $stmt->fetch();

if (!$account) {
    errorResponse('NOT_FOUND', 'Account not found', 404);
}

// Deactivate (soft delete)
$stmt = $pdo->prepare("UPDATE scurry_outlook_accounts SET is_active = 0, access_token = NULL, refresh_token = NULL, updated_at = CURRENT_TIMESTAMP WHERE id = ?");
$stmt->execute([$accountId]);

jsonResponse([
    'success' => true,
    'message' => 'Outlook account disconnected',
    'data' => [
        'account_id' => (int)$accountId,
        'email' => $account['email_address']
    ]
]);
