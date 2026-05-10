<?php
/**
 * 🐿️ Scurry Email API - Disconnect Gmail
 * 
 * POST /auth/gmail/disconnect.php
 * 
 * Headers:
 *   Authorization: Bearer {jwt_token}
 *   Content-Type: application/json
 * 
 * Body:
 *   { "account_id": 1 }
 */

require_once __DIR__ . '/../../auth.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    errorResponse('METHOD_NOT_ALLOWED', 'Only POST method allowed', 405);
}

// Require authentication
$user = requireAuth();

$input = json_decode(file_get_contents('php://input'), true);

if (!$input || empty($input['account_id'])) {
    errorResponse('VALIDATION_ERROR', 'account_id is required', 400);
}

$account_id = intval($input['account_id']);

$db = getDB();

// Check account exists and belongs to this user
$stmt = $db->prepare("
    SELECT id, email_address 
    FROM scurry_email_accounts 
    WHERE id = ? AND user_id = ?
");
$stmt->execute([$account_id, $user['gmail_user_id']]);
$account = $stmt->fetch();

if (!$account) {
    errorResponse('ACCOUNT_NOT_FOUND', 'Email account not found or access denied', 404);
}

// Deactivate account (soft delete)
$stmt = $db->prepare("
    UPDATE scurry_email_accounts 
    SET is_active = FALSE, updated_at = CURRENT_TIMESTAMP 
    WHERE id = ?
");
$stmt->execute([$account_id]);

jsonResponse([
    'success' => true,
    'message' => 'Gmail account disconnected successfully',
    'data' => [
        'account_id' => $account_id,
        'email_address' => $account['email_address']
    ]
]);
