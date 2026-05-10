<?php
/**
 * 🐿️ Scurry Gmail API - Check Replies
 * 
 * GET /email/replies.php?email_id=1 - Check reply for specific sent email
 * GET /email/replies.php?account_id=3 - Check all replies for account
 */

require_once __DIR__ . '/../config.php';
require_once __DIR__ . '/../db.php';

setCorsHeaders();

// Verify JWT authentication
$user = verifyAuthToken();

$pdo = getDbConnection();

$emailId = $_GET['email_id'] ?? null;
$accountId = $_GET['account_id'] ?? null;

if ($emailId) {
    // Check reply for specific email
    $stmt = $pdo->prepare("
        SELECT e.*, a.email_address as from_email 
        FROM scurry_sent_emails e
        JOIN scurry_email_accounts a ON e.account_id = a.id
        WHERE e.id = ? AND e.user_id = ?
    ");
    $stmt->execute([$emailId, $user['id']]);
    $email = $stmt->fetch();
    
    if (!$email) {
        errorResponse('NOT_FOUND', 'Email not found', 404);
    }
    
    // Get account with valid token
    $account = getGmailAccountWithValidToken($email['account_id'], $user['id']);
    
    if (!$account) {
        errorResponse('ACCOUNT_ERROR', 'Gmail account not found or token expired', 401);
    }
    
    // Search for replies
    $reply = searchForReply(
        $account['access_token_decrypted'],
        $email['recipient_email'],
        $email['subject'],
        $email['sent_at'],
        $email['gmail_thread_id']
    );
    
    // Update database if reply found
    if ($reply['has_reply'] && !$email['replied_at']) {
        $stmt = $pdo->prepare("UPDATE scurry_sent_emails SET replied_at = ?, reply_message_id = ? WHERE id = ?");
        $stmt->execute([$reply['replied_at'], $reply['reply_id'], $emailId]);
    }
    
    jsonResponse([
        'success' => true,
        'data' => [
            'email_id' => (int)$emailId,
            'to' => $email['recipient_email'],
            'subject' => $email['subject'],
            'sent_at' => $email['sent_at'],
            'has_reply' => $reply['has_reply'],
            'reply' => $reply['has_reply'] ? [
                'id' => $reply['reply_id'],
                'from' => $reply['from'],
                'subject' => $reply['subject'],
                'snippet' => $reply['snippet'],
                'received_at' => $reply['received_at']
            ] : null
        ]
    ]);
    
} elseif ($accountId) {
    // Check replies for all sent emails from account
    $account = getGmailAccountWithValidToken($accountId, $user['id']);
    
    if (!$account) {
        errorResponse('ACCOUNT_ERROR', 'Gmail account not found or token expired', 401);
    }
    
    // Get sent emails without replies
    $stmt = $pdo->prepare("
        SELECT * FROM scurry_sent_emails 
        WHERE account_id = ? AND user_id = ? AND status = 'sent' AND replied_at IS NULL
        ORDER BY sent_at DESC
        LIMIT 50
    ");
    $stmt->execute([$accountId, $user['id']]);
    $emails = $stmt->fetchAll();
    
    $results = [];
    $repliesFound = 0;
    
    foreach ($emails as $email) {
        $reply = searchForReply(
            $account['access_token_decrypted'],
            $email['recipient_email'],
            $email['subject'],
            $email['sent_at'],
            $email['gmail_thread_id']
        );
        
        if ($reply['has_reply']) {
            $repliesFound++;
            
            // Update database
            $stmt = $pdo->prepare("UPDATE scurry_sent_emails SET replied_at = ?, reply_message_id = ? WHERE id = ?");
            $stmt->execute([$reply['replied_at'], $reply['reply_id'], $email['id']]);
            
            $results[] = [
                'email_id' => (int)$email['id'],
                'to' => $email['recipient_email'],
                'subject' => $email['subject'],
                'sent_at' => $email['sent_at'],
                'reply' => [
                    'from' => $reply['from'],
                    'snippet' => $reply['snippet'],
                    'received_at' => $reply['received_at']
                ]
            ];
        }
    }
    
    jsonResponse([
        'success' => true,
        'data' => [
            'checked' => count($emails),
            'replies_found' => $repliesFound,
            'replies' => $results
        ]
    ]);
    
} else {
    errorResponse('MISSING_PARAM', 'email_id or account_id is required', 400);
}

/**
 * Verify JWT Token
 */
function verifyAuthToken() {
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
    
    // Ensure user exists in scurry_users table
    $pdo = getDbConnection();
    $stmt = $pdo->prepare("SELECT * FROM scurry_users WHERE external_user_id = ?");
    $stmt->execute([$userData['id']]);
    $user = $stmt->fetch();
    
    if (!$user) {
        errorResponse('UNAUTHORIZED', 'User not found', 401);
    }
    
    return $user;
}

/**
 * Get Gmail account with valid token (refresh if needed)
 */
function getGmailAccountWithValidToken($accountId, $userId) {
    $pdo = getDbConnection();
    
    $stmt = $pdo->prepare("SELECT * FROM scurry_email_accounts WHERE id = ? AND user_id = ? AND is_active = 1");
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
            return null;
        }
        
        // Refresh the token
        $newTokens = refreshGmailToken($refreshToken);
        
        if (!$newTokens || isset($newTokens['error'])) {
            return null;
        }
        
        $accessToken = $newTokens['access_token'];
        $expiresAt = date('Y-m-d H:i:s', time() + ($newTokens['expires_in'] ?? 3600));
        
        // Update in database
        $stmt = $pdo->prepare("UPDATE scurry_email_accounts SET access_token = ?, token_expires_at = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?");
        $stmt->execute([
            encryptToken($accessToken),
            $expiresAt,
            $accountId
        ]);
    }
    
    $account['access_token_decrypted'] = $accessToken;
    return $account;
}

/**
 * Refresh Gmail access token
 */
function refreshGmailToken($refreshToken) {
    $ch = curl_init('https://oauth2.googleapis.com/token');
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => http_build_query([
            'client_id' => GOOGLE_CLIENT_ID,
            'client_secret' => GOOGLE_CLIENT_SECRET,
            'refresh_token' => $refreshToken,
            'grant_type' => 'refresh_token'
        ]),
        CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded'],
        CURLOPT_TIMEOUT => 30
    ]);
    
    $response = curl_exec($ch);
    curl_close($ch);
    
    return json_decode($response, true);
}

/**
 * Search for reply in Gmail
 */
function searchForReply($accessToken, $fromEmail, $originalSubject, $sentAt, $threadId = null) {
    
    // Method 1: If we have thread ID, check the thread for replies
    if ($threadId) {
        $reply = checkThreadForReply($accessToken, $threadId, $fromEmail);
        if ($reply['has_reply']) {
            return $reply;
        }
    }
    
    // Method 2: Search inbox for emails from the recipient
    $query = 'from:' . $fromEmail . ' after:' . date('Y/m/d', strtotime($sentAt));
    $query = urlencode($query);
    
    $url = "https://gmail.googleapis.com/gmail/v1/users/me/messages?q={$query}&maxResults=10";
    
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $accessToken,
            'Content-Type: application/json'
        ],
        CURLOPT_TIMEOUT => 30
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        return ['has_reply' => false];
    }
    
    $data = json_decode($response, true);
    $messages = $data['messages'] ?? [];
    
    // Check each message
    foreach ($messages as $msg) {
        $messageDetails = getMessageDetails($accessToken, $msg['id']);
        
        if (!$messageDetails) continue;
        
        $msgSubject = $messageDetails['subject'] ?? '';
        $msgFrom = $messageDetails['from'] ?? '';
        
        // Check if subject matches (Re: original or contains original)
        $cleanSubject = preg_replace('/^Re:\s*/i', '', $originalSubject);
        
        if (stripos($msgSubject, $cleanSubject) !== false) {
            return [
                'has_reply' => true,
                'reply_id' => $msg['id'],
                'from' => $msgFrom,
                'subject' => $msgSubject,
                'snippet' => $messageDetails['snippet'] ?? '',
                'received_at' => $messageDetails['date'] ?? null,
                'replied_at' => $messageDetails['date'] ?? date('Y-m-d H:i:s')
            ];
        }
    }
    
    return ['has_reply' => false];
}

/**
 * Check thread for replies
 */
function checkThreadForReply($accessToken, $threadId, $expectedFrom) {
    $url = "https://gmail.googleapis.com/gmail/v1/users/me/threads/{$threadId}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date";
    
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $accessToken,
            'Content-Type: application/json'
        ],
        CURLOPT_TIMEOUT => 30
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        return ['has_reply' => false];
    }
    
    $thread = json_decode($response, true);
    $messages = $thread['messages'] ?? [];
    
    // Skip first message (our sent email), check rest for replies
    if (count($messages) > 1) {
        for ($i = 1; $i < count($messages); $i++) {
            $msg = $messages[$i];
            $headers = $msg['payload']['headers'] ?? [];
            
            $from = '';
            $subject = '';
            $date = '';
            
            foreach ($headers as $header) {
                if ($header['name'] === 'From') $from = $header['value'];
                if ($header['name'] === 'Subject') $subject = $header['value'];
                if ($header['name'] === 'Date') $date = $header['value'];
            }
            
            // Check if this message is from the recipient (not from us)
            if (stripos($from, $expectedFrom) !== false) {
                return [
                    'has_reply' => true,
                    'reply_id' => $msg['id'],
                    'from' => $from,
                    'subject' => $subject,
                    'snippet' => $msg['snippet'] ?? '',
                    'received_at' => $date,
                    'replied_at' => date('Y-m-d H:i:s', strtotime($date))
                ];
            }
        }
    }
    
    return ['has_reply' => false];
}

/**
 * Get message details
 */
function getMessageDetails($accessToken, $messageId) {
    $url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{$messageId}?format=metadata&metadataHeaders=From&metadataHeaders=Subject&metadataHeaders=Date";
    
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $accessToken,
            'Content-Type: application/json'
        ],
        CURLOPT_TIMEOUT => 30
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        return null;
    }
    
    $msg = json_decode($response, true);
    $headers = $msg['payload']['headers'] ?? [];
    
    $result = [
        'snippet' => $msg['snippet'] ?? ''
    ];
    
    foreach ($headers as $header) {
        if ($header['name'] === 'From') $result['from'] = $header['value'];
        if ($header['name'] === 'Subject') $result['subject'] = $header['value'];
        if ($header['name'] === 'Date') $result['date'] = date('Y-m-d H:i:s', strtotime($header['value']));
    }
    
    return $result;
}