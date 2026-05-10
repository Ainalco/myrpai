<?php
/**
 * 🐿️ Scurry Email API - Inbox (Read Emails)
 * 
 * GET /email/inbox.php?account_id=1                     → List recent emails
 * GET /email/inbox.php?account_id=1&limit=20            → Limit results
 * GET /email/inbox.php?account_id=1&q=from:john         → Search emails
 * GET /email/inbox.php?account_id=1&label=INBOX         → Filter by label
 * GET /email/inbox.php?account_id=1&message_id=xxx      → Get single email
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

// Get parameters - handle both $_GET and parsed query string
$accountId = $_GET['account_id'] ?? $_REQUEST['account_id'] ?? null;

// Fallback: parse from query string directly
if (!$accountId && !empty($_SERVER['QUERY_STRING'])) {
    parse_str($_SERVER['QUERY_STRING'], $queryParams);
    $accountId = $queryParams['account_id'] ?? null;
}

$messageId = $_GET['message_id'] ?? null;
$limit = min((int)($_GET['limit'] ?? 20), 100); // Max 100
$query = $_GET['q'] ?? '';
$label = $_GET['label'] ?? 'INBOX';
$pageToken = $_GET['page_token'] ?? null;

if (!$accountId) {
    jsonResponse([
        'success' => false, 
        'error' => 'account_id is required',
        'debug' => [
            'GET' => $_GET,
            'REQUEST' => $_REQUEST,
            'QUERY_STRING' => $_SERVER['QUERY_STRING'] ?? 'empty'
        ]
    ], 400);
}

try {
    $pdo = getDbConnection();
    
    // Get gmail user
    $stmt = $pdo->prepare("SELECT id FROM scurry_users WHERE external_user_id = ?");
    $stmt->execute([$user['user_id']]);
    $gmailUser = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if (!$gmailUser) {
        jsonResponse(['success' => false, 'error' => 'User not found'], 404);
    }
    
    // Get email account with tokens
    $stmt = $pdo->prepare("
        SELECT * FROM scurry_email_accounts 
        WHERE id = ? AND user_id = ? AND is_active = TRUE
    ");
    $stmt->execute([$accountId, $gmailUser['id']]);
    $account = $stmt->fetch(PDO::FETCH_ASSOC);
    
    if (!$account) {
        jsonResponse(['success' => false, 'error' => 'Account not found or not authorized'], 404);
    }
    
    // Decrypt access token
    $accessToken = decryptToken($account['access_token']);
    
    // Check if token is expired
    if (strtotime($account['token_expires_at']) <= time()) {
        // Refresh the token
        $refreshToken = decryptToken($account['refresh_token']);
        $newTokens = refreshGoogleToken($refreshToken);
        
        if (!$newTokens) {
            jsonResponse(['success' => false, 'error' => 'Token expired and refresh failed. Please reconnect Gmail.'], 401);
        }
        
        // Update tokens in database
        $stmt = $pdo->prepare("
            UPDATE scurry_email_accounts 
            SET access_token = ?, token_expires_at = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ");
        $stmt->execute([
            encryptToken($newTokens['access_token']),
            date('Y-m-d H:i:s', time() + $newTokens['expires_in']),
            $accountId
        ]);
        
        $accessToken = $newTokens['access_token'];
    }
    
    // If message_id provided, get single email
    if ($messageId) {
        $email = getGmailMessage($accessToken, $messageId);
        
        if (!$email) {
            jsonResponse(['success' => false, 'error' => 'Message not found'], 404);
        }
        
        jsonResponse([
            'success' => true,
            'data' => ['message' => $email]
        ]);
    }
    
    // List emails
    $emails = listGmailMessages($accessToken, $limit, $query, $label, $pageToken);
    
    jsonResponse([
        'success' => true,
        'data' => $emails
    ]);
    
} catch (Exception $e) {
    error_log("Inbox error: " . $e->getMessage());
    jsonResponse(['success' => false, 'error' => 'Failed to fetch inbox: ' . $e->getMessage()], 500);
}

/**
 * Refresh Google access token
 */
function refreshGoogleToken($refreshToken) {
    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL => 'https://oauth2.googleapis.com/token',
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => http_build_query([
            'client_id' => GOOGLE_CLIENT_ID,
            'client_secret' => GOOGLE_CLIENT_SECRET,
            'refresh_token' => $refreshToken,
            'grant_type' => 'refresh_token'
        ])
    ]);
    
    $response = curl_exec($ch);
    curl_close($ch);
    
    $data = json_decode($response, true);
    
    if (isset($data['access_token'])) {
        return $data;
    }
    
    return null;
}

/**
 * List Gmail messages
 */
function listGmailMessages($accessToken, $limit, $query, $label, $pageToken) {
    // Build URL
    $params = [
        'maxResults' => $limit,
        'labelIds' => $label
    ];
    
    if ($query) {
        $params['q'] = $query;
    }
    
    if ($pageToken) {
        $params['pageToken'] = $pageToken;
    }
    
    $url = 'https://gmail.googleapis.com/gmail/v1/users/me/messages?' . http_build_query($params);
    
    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $accessToken
        ]
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        throw new Exception('Gmail API error: ' . $response);
    }
    
    $data = json_decode($response, true);
    
    // Get details for each message
    $messages = [];
    if (!empty($data['messages'])) {
        foreach ($data['messages'] as $msg) {
            $details = getGmailMessage($accessToken, $msg['id'], 'metadata');
            if ($details) {
                $messages[] = $details;
            }
        }
    }
    
    return [
        'messages' => $messages,
        'total' => $data['resultSizeEstimate'] ?? count($messages),
        'next_page_token' => $data['nextPageToken'] ?? null
    ];
}

/**
 * Get single Gmail message
 */
function getGmailMessage($accessToken, $messageId, $format = 'full') {
    $url = "https://gmail.googleapis.com/gmail/v1/users/me/messages/{$messageId}?format={$format}";
    
    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL => $url,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $accessToken
        ]
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        return null;
    }
    
    $data = json_decode($response, true);
    
    // Parse headers
    $headers = [];
    if (!empty($data['payload']['headers'])) {
        foreach ($data['payload']['headers'] as $header) {
            $headers[$header['name']] = $header['value'];
        }
    }
    
    // Build clean response
    $message = [
        'id' => $data['id'],
        'thread_id' => $data['threadId'],
        'label_ids' => $data['labelIds'] ?? [],
        'snippet' => $data['snippet'] ?? '',
        'from' => $headers['From'] ?? '',
        'to' => $headers['To'] ?? '',
        'cc' => $headers['Cc'] ?? '',
        'subject' => $headers['Subject'] ?? '(no subject)',
        'date' => $headers['Date'] ?? '',
        'timestamp' => isset($data['internalDate']) ? (int)($data['internalDate'] / 1000) : null,
        'is_unread' => in_array('UNREAD', $data['labelIds'] ?? []),
        'is_starred' => in_array('STARRED', $data['labelIds'] ?? []),
        'is_important' => in_array('IMPORTANT', $data['labelIds'] ?? []),
    ];
    
    // Include body for full format
    if ($format === 'full') {
        $message['body_text'] = '';
        $message['body_html'] = '';
        
        // Extract body from payload
        $body = extractBody($data['payload']);
        $message['body_text'] = $body['text'];
        $message['body_html'] = $body['html'];
        
        // Attachments
        $message['attachments'] = extractAttachments($data['payload']);
    }
    
    return $message;
}

/**
 * Extract body content from Gmail payload
 */
function extractBody($payload) {
    $text = '';
    $html = '';
    
    // Check if body is directly in payload
    if (!empty($payload['body']['data'])) {
        $content = base64UrlDecode($payload['body']['data']);
        if ($payload['mimeType'] === 'text/plain') {
            $text = $content;
        } elseif ($payload['mimeType'] === 'text/html') {
            $html = $content;
        }
    }
    
    // Check parts
    if (!empty($payload['parts'])) {
        foreach ($payload['parts'] as $part) {
            if ($part['mimeType'] === 'text/plain' && !empty($part['body']['data'])) {
                $text = base64UrlDecode($part['body']['data']);
            } elseif ($part['mimeType'] === 'text/html' && !empty($part['body']['data'])) {
                $html = base64UrlDecode($part['body']['data']);
            } elseif ($part['mimeType'] === 'multipart/alternative' && !empty($part['parts'])) {
                // Nested multipart
                $nested = extractBody($part);
                if ($nested['text']) $text = $nested['text'];
                if ($nested['html']) $html = $nested['html'];
            }
        }
    }
    
    return ['text' => $text, 'html' => $html];
}

/**
 * Extract attachments info
 */
function extractAttachments($payload) {
    $attachments = [];
    
    if (!empty($payload['parts'])) {
        foreach ($payload['parts'] as $part) {
            if (!empty($part['filename']) && !empty($part['body']['attachmentId'])) {
                $attachments[] = [
                    'id' => $part['body']['attachmentId'],
                    'filename' => $part['filename'],
                    'mime_type' => $part['mimeType'],
                    'size' => $part['body']['size'] ?? 0
                ];
            }
            
            // Check nested parts
            if (!empty($part['parts'])) {
                $nested = extractAttachments($part);
                $attachments = array_merge($attachments, $nested);
            }
        }
    }
    
    return $attachments;
}

/**
 * Decode base64url encoded string
 */
if (!function_exists('base64UrlDecode')) {
    function base64UrlDecode($data) {
        $data = str_replace(['-', '_'], ['+', '/'], $data);
        return base64_decode($data);
    }
}