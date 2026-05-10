<?php
/**
 * 🐿️ Scurry Outlook API - Authentication Helper
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';

/**
 * Verify JWT and return user
 */
function verifyAuth() {
    $headers = getallheaders();
    $authHeader = $headers['Authorization'] ?? $headers['authorization'] ?? '';
    
    if (empty($authHeader)) {
        errorResponse('UNAUTHORIZED', 'Authorization header required', 401);
    }
    
    if (!preg_match('/Bearer\s+(.+)$/i', $authHeader, $matches)) {
        errorResponse('UNAUTHORIZED', 'Invalid authorization format', 401);
    }
    
    $token = $matches[1];
    
    // Verify via API
    $ch = curl_init(AUTH_API_URL);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $token,
            'Content-Type: application/json'
        ],
        CURLOPT_TIMEOUT => 10
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        errorResponse('UNAUTHORIZED', 'Invalid or expired token', 401);
    }
    
    $userData = json_decode($response, true);
    
    if (!$userData || !isset($userData['id'])) {
        errorResponse('UNAUTHORIZED', 'Invalid token response', 401);
    }
    
    // Ensure user exists in scurry_users table (shared with Gmail)
    $user = ensureUserExists($userData);
    
    return $user;
}

/**
 * Ensure user exists in scurry_users table
 */
function ensureUserExists($authData) {
    $pdo = getDbConnection();
    
    // Check if user exists
    $stmt = $pdo->prepare("SELECT * FROM scurry_users WHERE external_user_id = ?");
    $stmt->execute([$authData['id']]);
    $user = $stmt->fetch();
    
    if (!$user) {
        // Create user
        $stmt = $pdo->prepare("INSERT INTO scurry_users (external_user_id, username, email, created_at) VALUES (?, ?, ?, CURRENT_TIMESTAMP)");
        $stmt->execute([
            $authData['id'],
            $authData['username'] ?? null,
            $authData['email'] ?? null
        ]);
        
        $user = [
            'id' => $pdo->lastInsertId(),
            'external_user_id' => $authData['id'],
            'username' => $authData['username'] ?? null,
            'email' => $authData['email'] ?? null
        ];
    }
    
    return $user;
}

/**
 * Get account and refresh token if needed
 */
function getAccountWithValidToken($accountId, $userId) {
    $pdo = getDbConnection();
    
    $stmt = $pdo->prepare("SELECT * FROM scurry_outlook_accounts WHERE id = ? AND user_id = ? AND is_active = 1");
    $stmt->execute([$accountId, $userId]);
    $account = $stmt->fetch();
    
    if (!$account) {
        return null;
    }
    
    // Decrypt tokens
    $accessToken = decryptToken($account['access_token']);
    $refreshToken = $account['refresh_token'] ? decryptToken($account['refresh_token']) : null;
    
    // Check if token expired
    if ($account['token_expires_at'] && strtotime($account['token_expires_at']) < time()) {
        if (!$refreshToken) {
            return null; // Can't refresh
        }
        
        // Refresh the token
        $newTokens = refreshAccessToken($refreshToken);
        
        if (!$newTokens || isset($newTokens['error'])) {
            return null;
        }
        
        $accessToken = $newTokens['access_token'];
        $expiresAt = date('Y-m-d H:i:s', time() + ($newTokens['expires_in'] ?? 3600));
        
        // Update in database
        $stmt = $pdo->prepare("UPDATE scurry_outlook_accounts SET access_token = ?, refresh_token = ?, token_expires_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?");
        $stmt->execute([
            encryptToken($accessToken),
            isset($newTokens['refresh_token']) ? encryptToken($newTokens['refresh_token']) : $account['refresh_token'],
            $expiresAt,
            $accountId
        ]);
    }
    
    $account['access_token_decrypted'] = $accessToken;
    return $account;
}

/**
 * Refresh access token
 */
function refreshAccessToken($refreshToken) {
    $ch = curl_init(MICROSOFT_TOKEN_URL);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => http_build_query([
            'client_id' => MICROSOFT_CLIENT_ID,
            'client_secret' => MICROSOFT_CLIENT_SECRET,
            'refresh_token' => $refreshToken,
            'grant_type' => 'refresh_token',
            'scope' => MICROSOFT_SCOPES
        ]),
        CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded'],
        CURLOPT_TIMEOUT => 30
    ]);
    
    $response = curl_exec($ch);
    curl_close($ch);
    
    return json_decode($response, true);
}
