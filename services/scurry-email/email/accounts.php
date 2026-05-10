<?php
/**
 * 🐿️ Scurry Email API - List Email Accounts
 * 
 * GET /email/accounts.php
 * GET /email/accounts.php?email=navids92@gmail.com  (filter by email)
 * GET /email/accounts.php?id=1                       (get specific account)
 * 
 * Returns connected email accounts for the authenticated user
 */

require_once __DIR__ . '/../config.php';
require_once __DIR__ . '/../db.php';
require_once __DIR__ . '/../auth.php';

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    jsonResponse(['success' => false, 'error' => 'Method not allowed'], 405);
}

// Authenticate
$user = requireAuth();

try {
    $pdo = getDbConnection();
    
    // Get gmail user
    $stmt = $pdo->prepare("SELECT id FROM scurry_users WHERE external_user_id = ?");
    $stmt->execute([$user['user_id']]);
    $gmailUser = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if (!$gmailUser) {
        jsonResponse([
            'success' => true,
            'data' => ['accounts' => []],
            'message' => 'No accounts found'
        ]);
    }
    
    // Build query based on filters
    $sql = "
        SELECT 
            id,
            'gmail' as provider,
            email_address,
            display_name,
            is_active,
            token_expires_at,
            last_sync_at,
            sync_error,
            created_at,
            updated_at
        FROM scurry_email_accounts 
        WHERE user_id = ? AND is_active = TRUE
    ";
    $params = [$gmailUser['id']];
    
    // Filter by email
    if (!empty($_GET['email'])) {
        $sql .= " AND email_address = ?";
        $params[] = strtolower(trim($_GET['email']));
    }
    
    // Filter by ID
    if (!empty($_GET['id'])) {
        $sql .= " AND id = ?";
        $params[] = (int)$_GET['id'];
    }
    
    $sql .= " ORDER BY created_at DESC";
    
    $stmt = $pdo->prepare($sql);
    $stmt->execute($params);
    $accounts = $stmt->fetchAll(PDO::FETCH_ASSOC);
    
    // Add token status to each account
    foreach ($accounts as &$account) {
        $expiresAt = strtotime($account['token_expires_at']);
        $now = time();
        
        if ($expiresAt > $now) {
            $account['token_status'] = 'valid';
            $account['token_expires_in'] = $expiresAt - $now;
        } else {
            $account['token_status'] = 'expired';
            $account['token_expires_in'] = 0;
        }
    }
    
    // If searching by email and found exactly one, return it directly
    if (!empty($_GET['email']) && count($accounts) === 1) {
        jsonResponse([
            'success' => true,
            'data' => [
                'account' => $accounts[0],
                'account_id' => $accounts[0]['id']  // Easy access to ID
            ]
        ]);
    }
    
    // If searching by ID and found exactly one, return it directly
    if (!empty($_GET['id']) && count($accounts) === 1) {
        jsonResponse([
            'success' => true,
            'data' => [
                'account' => $accounts[0]
            ]
        ]);
    }
    
    jsonResponse([
        'success' => true,
        'data' => [
            'accounts' => $accounts,
            'total' => count($accounts)
        ]
    ]);
    
} catch (Exception $e) {
    error_log("Accounts error: " . $e->getMessage());
    jsonResponse(['success' => false, 'error' => 'Failed to fetch accounts'], 500);
}