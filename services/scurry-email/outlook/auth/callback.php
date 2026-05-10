<?php
/**
 * 🐿️ Scurry Outlook API - OAuth Callback
 * 
 * GET /outlook/auth/callback.php
 * Handles Microsoft OAuth redirect
 */

require_once __DIR__ . '/../config.php';
require_once __DIR__ . '/../db.php';

session_start();

// Check for errors
if (isset($_GET['error'])) {
    die("OAuth Error: " . $_GET['error'] . " - " . ($_GET['error_description'] ?? 'Unknown error'));
}

// Get code and state
$code = $_GET['code'] ?? null;
$state = $_GET['state'] ?? null;

if (!$code) {
    die('Authorization code not received');
}

if (!$state) {
    die('State parameter missing');
}

// Decode state to get user_id
$stateData = json_decode(base64UrlDecode($state), true);
$userId = $stateData['user_id'] ?? null;

if (!$userId) {
    die('Invalid state - user_id not found');
}

// Exchange code for tokens
$tokenData = exchangeCodeForTokens($code);

if (!$tokenData || isset($tokenData['error'])) {
    die("Token Error: " . ($tokenData['error_description'] ?? $tokenData['error'] ?? 'Failed to get tokens'));
}

// Get user info from Microsoft Graph
$userInfo = getMicrosoftUserInfo($tokenData['access_token']);

if (!$userInfo || (!isset($userInfo['mail']) && !isset($userInfo['userPrincipalName']))) {
    die('Failed to get user email from Microsoft');
}

$email = $userInfo['mail'] ?? $userInfo['userPrincipalName'];
$displayName = $userInfo['displayName'] ?? null;

// Store in database
$pdo = getDbConnection();
$expiresAt = date('Y-m-d H:i:s', time() + ($tokenData['expires_in'] ?? 3600));

// Check if account exists
$stmt = $pdo->prepare("SELECT id FROM scurry_outlook_accounts WHERE user_id = ? AND email_address = ?");
$stmt->execute([$userId, $email]);
$existing = $stmt->fetch();

if ($existing) {
    // Update existing
    $stmt = $pdo->prepare("UPDATE scurry_outlook_accounts SET 
        display_name = ?,
        access_token = ?, 
        refresh_token = ?, 
        token_expires_at = ?,
        scopes = ?,
        is_active = 1,
        updated_at = CURRENT_TIMESTAMP
        WHERE id = ?");
    $stmt->execute([
        $displayName,
        encryptToken($tokenData['access_token']),
        isset($tokenData['refresh_token']) ? encryptToken($tokenData['refresh_token']) : null,
        $expiresAt,
        MICROSOFT_SCOPES,
        $existing['id']
    ]);
    $accountId = $existing['id'];
} else {
    // Create new
    $stmt = $pdo->prepare("INSERT INTO scurry_outlook_accounts 
        (user_id, email_address, display_name, access_token, refresh_token, token_expires_at, scopes, created_at) 
        VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)");
    $stmt->execute([
        $userId,
        $email,
        $displayName,
        encryptToken($tokenData['access_token']),
        isset($tokenData['refresh_token']) ? encryptToken($tokenData['refresh_token']) : null,
        $expiresAt,
        MICROSOFT_SCOPES
    ]);
    $accountId = $pdo->lastInsertId();
}

// Success page
?>
<!DOCTYPE html>
<html>
<head>
    <title>🐿️ Outlook Connected - Scurry</title>
    <style>
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            margin: 0;
            background: linear-gradient(135deg, #0078d4 0%, #106ebe 100%);
        }
        .card {
            background: white;
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            text-align: center;
            max-width: 400px;
        }
        .icon { font-size: 64px; margin-bottom: 20px; }
        h1 { color: #0078d4; margin: 0 0 10px 0; }
        .email { 
            background: #f0f0f0; 
            padding: 10px 20px; 
            border-radius: 8px; 
            margin: 20px 0;
            font-family: monospace;
            word-break: break-all;
        }
        .info { color: #666; font-size: 14px; }
        .account-id {
            background: #e8f4fd;
            color: #0078d4;
            padding: 5px 10px;
            border-radius: 4px;
            font-family: monospace;
        }
    </style>
</head>
<body>
    <div class="card">
        <div class="icon">✅</div>
        <h1>Outlook Connected!</h1>
        <p>Successfully connected:</p>
        <div class="email"><?php echo htmlspecialchars($email); ?></div>
        <?php if ($displayName): ?>
        <p class="info">Name: <?php echo htmlspecialchars($displayName); ?></p>
        <?php endif; ?>
        <p class="info">
            Account ID: <span class="account-id"><?php echo $accountId; ?></span>
        </p>
        <p class="info">You can close this window.</p>
    </div>
</body>
</html>
<?php

function exchangeCodeForTokens($code) {
    $ch = curl_init(MICROSOFT_TOKEN_URL);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => http_build_query([
            'client_id' => MICROSOFT_CLIENT_ID,
            'client_secret' => MICROSOFT_CLIENT_SECRET,
            'code' => $code,
            'redirect_uri' => MICROSOFT_REDIRECT_URI,
            'grant_type' => 'authorization_code',
            'scope' => MICROSOFT_SCOPES
        ]),
        CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded'],
        CURLOPT_TIMEOUT => 30
    ]);
    
    $response = curl_exec($ch);
    curl_close($ch);
    
    return json_decode($response, true);
}

function getMicrosoftUserInfo($accessToken) {
    $ch = curl_init(MICROSOFT_GRAPH_URL . '/me');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $accessToken,
            'Content-Type: application/json'
        ],
        CURLOPT_TIMEOUT => 10
    ]);
    
    $response = curl_exec($ch);
    curl_close($ch);
    
    return json_decode($response, true);
}