<?php
/**
 * 🐿️ Scurry Email API - Gmail OAuth Callback
 * 
 * GET /auth/gmail/callback.php?code=xxx&state=xxx
 * 
 * Called by Google after user authorizes
 */

require_once __DIR__ . '/../../config.php';
require_once __DIR__ . '/../../db.php';

// Get parameters
$code = isset($_GET['code']) ? $_GET['code'] : null;
$state = isset($_GET['state']) ? $_GET['state'] : null;
$error = isset($_GET['error']) ? $_GET['error'] : null;

// Handle errors from Google
if ($error) {
    showError('Google authorization failed: ' . htmlspecialchars($error));
}

if (!$code || !$state) {
    showError('Missing code or state parameter');
}

// Decode and validate state
$stateData = json_decode(base64_decode($state), true);

if (!$stateData || !isset($stateData['user_id']) || !isset($stateData['csrf'])) {
    showError('Invalid state parameter');
}

$db = getDB();

// Verify state token exists and not expired
$stmt = $db->prepare("
    SELECT * FROM scurry_oauth_states
    WHERE state_token = ? AND user_id = ? AND expires_at > CURRENT_TIMESTAMP
");
$stmt->execute([$stateData['csrf'], $stateData['user_id']]);
$validState = $stmt->fetch();

if (!$validState) {
    showError('Invalid or expired state token. Please try connecting again.');
}

// Delete used state token
$stmt = $db->prepare("DELETE FROM scurry_oauth_states WHERE state_token = ?");
$stmt->execute([$stateData['csrf']]);

$user_id = $stateData['user_id'];

// Exchange code for tokens
$ch = curl_init();
curl_setopt_array($ch, [
    CURLOPT_URL => 'https://oauth2.googleapis.com/token',
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => http_build_query([
        'code' => $code,
        'client_id' => GOOGLE_CLIENT_ID,
        'client_secret' => GOOGLE_CLIENT_SECRET,
        'redirect_uri' => GOOGLE_REDIRECT_URI,
        'grant_type' => 'authorization_code'
    ]),
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded']
]);

$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

if ($httpCode !== 200) {
    $errorData = json_decode($response, true);
    $errorMsg = isset($errorData['error_description']) ? $errorData['error_description'] : 'Token exchange failed';
    showError('Failed to get tokens: ' . $errorMsg);
}

$tokens = json_decode($response, true);

if (!isset($tokens['access_token'])) {
    showError('No access token received from Google');
}

$access_token = $tokens['access_token'];
$refresh_token = isset($tokens['refresh_token']) ? $tokens['refresh_token'] : null;
$expires_in = isset($tokens['expires_in']) ? $tokens['expires_in'] : 3600;
$scope = isset($tokens['scope']) ? $tokens['scope'] : '';

// Get user info from Google
$ch = curl_init();
curl_setopt_array($ch, [
    CURLOPT_URL => 'https://www.googleapis.com/oauth2/v2/userinfo',
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER => ['Authorization: Bearer ' . $access_token]
]);

$userInfoResponse = curl_exec($ch);
curl_close($ch);

$userInfo = json_decode($userInfoResponse, true);

if (!isset($userInfo['email'])) {
    showError('Could not get user email from Google');
}

$email = $userInfo['email'];
$displayName = isset($userInfo['name']) ? $userInfo['name'] : $email;

// Check if this email is already connected for this user
$stmt = $db->prepare("
    SELECT id FROM scurry_email_accounts
    WHERE user_id = ? AND email_address = ?
");
$stmt->execute([$user_id, $email]);
$existingAccount = $stmt->fetch();

$token_expires_at = date('Y-m-d H:i:s', time() + $expires_in);

if ($existingAccount) {
    // Update existing account
    $stmt = $db->prepare("
        UPDATE scurry_email_accounts SET
            access_token = ?,
            refresh_token = COALESCE(?, refresh_token),
            token_expires_at = ?,
            display_name = ?,
            scopes = ?,
            is_active = TRUE,
            sync_error = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ");
    $stmt->execute([
        encryptToken($access_token),
        $refresh_token ? encryptToken($refresh_token) : null,
        $token_expires_at,
        $displayName,
        $scope,
        $existingAccount['id']
    ]);
    $account_id = $existingAccount['id'];
} else {
    // Create new account
    if (!$refresh_token) {
        showError('No refresh token received. Please revoke access at https://myaccount.google.com/permissions and try again.');
    }
    
    $stmt = $db->prepare("
        INSERT INTO scurry_email_accounts
        (user_id, provider, email_address, display_name, access_token, refresh_token, token_expires_at, scopes, is_active, created_at)
        VALUES (?, 'gmail', ?, ?, ?, ?, ?, ?, TRUE, CURRENT_TIMESTAMP)
    ");
    $stmt->execute([
        $user_id,
        $email,
        $displayName,
        encryptToken($access_token),
        encryptToken($refresh_token),
        $token_expires_at,
        $scope
    ]);
    $account_id = $db->lastInsertId();
}

// Show success page
showSuccess($email, $displayName, $account_id, $user_id, $token_expires_at);


/**
 * Show error page
 */
function showError($message) {
    ?>
    <!DOCTYPE html>
    <html>
    <head>
        <title>Connection Failed - Scurry</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #FFF8E1; }
            .container { text-align: center; padding: 2rem; background: white; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); max-width: 500px; }
            h1 { color: #f44336; }
            p { color: #666; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>❌ Connection Failed</h1>
            <p><?= htmlspecialchars($message) ?></p>
            <p><a href="javascript:window.close()">Close this window</a></p>
        </div>
    </body>
    </html>
    <?php
    exit;
}

/**
 * Show success page
 */
function showSuccess($email, $displayName, $account_id, $user_id, $token_expires_at) {
    ?>
    <!DOCTYPE html>
    <html>
    <head>
        <title>Gmail Connected - Scurry</title>
        <style>
            body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; display: flex; justify-content: center; align-items: center; min-height: 100vh; margin: 0; background: #FFF8E1; }
            .container { text-align: center; padding: 2rem; background: white; border-radius: 16px; box-shadow: 0 4px 20px rgba(0,0,0,0.1); max-width: 500px; }
            h1 { color: #4CAF50; }
            .info { background: #f5f5f5; padding: 1rem; border-radius: 8px; margin: 1rem 0; text-align: left; }
            .info p { margin: 0.5rem 0; color: #333; }
            .label { color: #666; font-size: 0.875rem; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>🐿️ Gmail Connected!</h1>
            <div class="info">
                <p><span class="label">Email:</span> <?= htmlspecialchars($email) ?></p>
                <p><span class="label">Name:</span> <?= htmlspecialchars($displayName) ?></p>
                <p><span class="label">Account ID:</span> <?= $account_id ?></p>
                <p><span class="label">Token Expires:</span> <?= $token_expires_at ?></p>
            </div>
            <p>You can now send emails using this account!</p>
            <p>This window can be closed.</p>
        </div>
        <script>
            // Send message to parent window if opened in popup
            if (window.opener) {
                window.opener.postMessage({
                    type: 'gmail_connected',
                    account_id: <?= $account_id ?>,
                    email: '<?= htmlspecialchars($email) ?>'
                }, '*');
            }
        </script>
    </body>
    </html>
    <?php
    exit;
}
