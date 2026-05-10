<?php
/**
 * 🐿️ Scurry Email API - Send Email
 * 
 * POST /email/send.php
 * 
 * Headers:
 *   Authorization: Bearer {jwt_token}
 *   Content-Type: application/json
 * 
 * Body:
 * {
 *   "account_id": 1,
 *   "to": "recipient@example.com",
 *   "to_name": "Recipient Name",
 *   "subject": "Hello!",
 *   "body_html": "<p>Hello world</p>",
 *   "body_text": "Hello world",
 *   "cc": ["cc@example.com"],
 *   "bcc": ["bcc@example.com"],
 *   "track_opens": true,
 *   "track_clicks": true,
 *   "thread_id": "18d5a1234567890",
 *   "in_reply_to": "<message-id@example.com>",
 *   "references": "<message-id@example.com>"
 * }
 */

require_once __DIR__ . '/../auth.php';

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    errorResponse('METHOD_NOT_ALLOWED', 'Only POST method allowed', 405);
}

// Require authentication
$user = requireAuth();

$input = json_decode(file_get_contents('php://input'), true);

if (!$input) {
    errorResponse('INVALID_JSON', 'Invalid JSON body', 400);
}

// Accept legacy "body" field too
if (empty($input['body_html']) && !empty($input['body'])) {
    $input['body_html'] = $input['body'];
}

// Validate required fields
$required = ['account_id', 'to', 'subject', 'body_html'];
foreach ($required as $field) {
    if (empty($input[$field])) {
        errorResponse('VALIDATION_ERROR', "Field '{$field}' is required", 400);
    }
}

$account_id = intval($input['account_id']);
$to_email = trim($input['to']);
$to_name = isset($input['to_name']) ? trim($input['to_name']) : '';
$subject = $input['subject'];
$body_html = $input['body_html'];
$body_text = isset($input['body_text']) ? $input['body_text'] : strip_tags($body_html);
$cc = isset($input['cc']) ? $input['cc'] : [];
$bcc = isset($input['bcc']) ? $input['bcc'] : [];
$track_opens = isset($input['track_opens']) ? $input['track_opens'] : true;
$track_clicks = isset($input['track_clicks']) ? $input['track_clicks'] : true;
$thread_id = isset($input['thread_id']) ? trim($input['thread_id']) : '';
$in_reply_to = isset($input['in_reply_to']) ? trim($input['in_reply_to']) : '';
$references = isset($input['references']) ? trim($input['references']) : '';

if ($in_reply_to !== '') {
    $in_reply_to = validateMessageIdHeader($in_reply_to, 'in_reply_to');
}
if ($references !== '') {
    $references = validateReferencesHeader($references, 'references');
}

// Validate email format
if (!filter_var($to_email, FILTER_VALIDATE_EMAIL)) {
    errorResponse('INVALID_EMAIL', 'Invalid recipient email address', 400);
}

$db = getDB();

// Get account and verify ownership
$stmt = $db->prepare("
    SELECT * FROM scurry_email_accounts 
    WHERE id = ? AND user_id = ? AND is_active = TRUE
");
$stmt->execute([$account_id, $user['gmail_user_id']]);
$account = $stmt->fetch();

if (!$account) {
    errorResponse('ACCOUNT_NOT_FOUND', 'Email account not found, inactive, or access denied', 404);
}

// Check if token needs refresh
$access_token = decryptToken($account['access_token']);
$token_expires_at = strtotime($account['token_expires_at']);

if ($token_expires_at <= time() + 300) {
    $access_token = refreshGoogleToken($account, $db);
    if (!$access_token) {
        errorResponse('TOKEN_REFRESH_FAILED', 'Failed to refresh access token. Please reconnect Gmail.', 500);
    }
}

// Insert email record first (to get ID for tracking)
$stmt = $db->prepare("
    INSERT INTO scurry_sent_emails 
    (user_id, account_id, recipient_email, recipient_name, cc, bcc, subject, body_html, body_text, status)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending')
");
$stmt->execute([
    $user['gmail_user_id'],
    $account_id,
    $to_email,
    $to_name,
    !empty($cc) ? json_encode($cc) : null,
    !empty($bcc) ? json_encode($bcc) : null,
    $subject,
    $body_html,
    $body_text
]);
$email_id = $db->lastInsertId();

// Add tracking pixel to HTML body
if ($track_opens) {
    $tracking_pixel = '<img src="' . APP_URL . '/track/open.php?id=' . $email_id . '" width="1" height="1" style="display:none" />';
    
    if (stripos($body_html, '</body>') !== false) {
        $body_html = str_ireplace('</body>', $tracking_pixel . '</body>', $body_html);
    } else {
        $body_html .= $tracking_pixel;
    }
}

// Add click tracking to links
if ($track_clicks) {
    $body_html = preg_replace_callback(
        '/<a\s+([^>]*href=["\'])([^"\']+)(["\'][^>]*)>/i',
        function($matches) use ($email_id) {
            $url = $matches[2];
            if (preg_match('/^(mailto:|tel:|#)/i', $url)) {
                return $matches[0];
            }
            $tracked_url = APP_URL . '/track/click.php?id=' . $email_id . '&url=' . urlencode($url);
            return '<a ' . $matches[1] . $tracked_url . $matches[3] . '>';
        },
        $body_html
    );
}

// Build email
$from_email = $account['email_address'];
$from_name = $account['display_name'] ?: $from_email;
$from_domain = 'scurry.local';
$from_domain_part = strrchr($from_email, '@');
if ($from_domain_part !== false) {
    $parsed_from_domain = substr($from_domain_part, 1);
    if ($parsed_from_domain !== '') {
        $from_domain = $parsed_from_domain;
    }
}
$message_id_header = sprintf('<scurry-%d-%s@%s>', $email_id, bin2hex(random_bytes(8)), $from_domain);

$to_formatted = $to_name ? "=?UTF-8?B?" . base64_encode($to_name) . "?= <{$to_email}>" : $to_email;
$from_formatted = $from_name ? "=?UTF-8?B?" . base64_encode($from_name) . "?= <{$from_email}>" : $from_email;

// Build MIME message
$boundary = md5(time() . rand());
$email_content = "MIME-Version: 1.0\r\n";
$email_content .= "From: {$from_formatted}\r\n";
$email_content .= "To: {$to_formatted}\r\n";

if (!empty($cc)) {
    $email_content .= "Cc: " . implode(', ', $cc) . "\r\n";
}
if (!empty($bcc)) {
    $email_content .= "Bcc: " . implode(', ', $bcc) . "\r\n";
}

$email_content .= "Subject: =?UTF-8?B?" . base64_encode($subject) . "?=\r\n";
$email_content .= "Message-ID: {$message_id_header}\r\n";
if ($in_reply_to !== '') {
    $email_content .= "In-Reply-To: {$in_reply_to}\r\n";
}
if ($references !== '') {
    $email_content .= "References: {$references}\r\n";
}
$email_content .= "Content-Type: multipart/alternative; boundary=\"{$boundary}\"\r\n\r\n";

// Plain text part
$email_content .= "--{$boundary}\r\n";
$email_content .= "Content-Type: text/plain; charset=UTF-8\r\n";
$email_content .= "Content-Transfer-Encoding: base64\r\n\r\n";
$email_content .= base64_encode($body_text) . "\r\n\r\n";

// HTML part
$email_content .= "--{$boundary}\r\n";
$email_content .= "Content-Type: text/html; charset=UTF-8\r\n";
$email_content .= "Content-Transfer-Encoding: base64\r\n\r\n";
$email_content .= base64_encode($body_html) . "\r\n\r\n";

$email_content .= "--{$boundary}--";

// Base64url encode for Gmail API
$encoded_message = rtrim(strtr(base64_encode($email_content), '+/', '-_'), '=');
$gmail_payload = ['raw' => $encoded_message];
if ($thread_id !== '') {
    $gmail_payload['threadId'] = $thread_id;
}

// Send via Gmail API
$ch = curl_init();
curl_setopt_array($ch, [
    CURLOPT_URL => 'https://gmail.googleapis.com/gmail/v1/users/me/messages/send',
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => json_encode($gmail_payload),
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER => [
        'Authorization: Bearer ' . $access_token,
        'Content-Type: application/json'
    ]
]);

$response = curl_exec($ch);
$http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
curl_close($ch);

$result = json_decode($response, true);

if ($http_code !== 200) {
    $stmt = $db->prepare("UPDATE scurry_sent_emails SET status = 'failed' WHERE id = ?");
    $stmt->execute([$email_id]);
    
    $error_message = isset($result['error']['message']) ? $result['error']['message'] : 'Unknown error';
    errorResponse('SEND_FAILED', 'Failed to send email: ' . $error_message, 500);
}

// Update email record
$stmt = $db->prepare("
    UPDATE scurry_sent_emails 
    SET gmail_message_id = ?, gmail_thread_id = ?, status = 'sent', sent_at = CURRENT_TIMESTAMP
    WHERE id = ?
");
$stmt->execute([$result['id'], $result['threadId'], $email_id]);

jsonResponse([
    'success' => true,
    'data' => [
        'email_id' => $email_id,
        'message_id' => $result['id'],
        'thread_id' => $result['threadId'],
        'message_id_header' => $message_id_header,
        'from' => $from_email,
        'to' => $to_email,
        'subject' => $subject,
        'tracking' => [
            'opens' => $track_opens,
            'clicks' => $track_clicks
        ],
        'sent_at' => date('c')
    ]
]);


/**
 * Refresh Google access token
 */
function refreshGoogleToken($account, $db) {
    $refresh_token = decryptToken($account['refresh_token']);
    
    if (!$refresh_token) {
        return null;
    }
    
    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL => 'https://oauth2.googleapis.com/token',
        CURLOPT_POST => true,
        CURLOPT_POSTFIELDS => http_build_query([
            'client_id' => GOOGLE_CLIENT_ID,
            'client_secret' => GOOGLE_CLIENT_SECRET,
            'refresh_token' => $refresh_token,
            'grant_type' => 'refresh_token'
        ]),
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => ['Content-Type: application/x-www-form-urlencoded']
    ]);
    
    $response = curl_exec($ch);
    $http_code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($http_code !== 200) {
        $stmt = $db->prepare("UPDATE scurry_email_accounts SET sync_error = ? WHERE id = ?");
        $stmt->execute(['Token refresh failed', $account['id']]);
        return null;
    }
    
    $tokens = json_decode($response, true);
    $access_token = $tokens['access_token'];
    $expires_in = isset($tokens['expires_in']) ? $tokens['expires_in'] : 3600;
    $token_expires_at = date('Y-m-d H:i:s', time() + $expires_in);
    
    $stmt = $db->prepare("
        UPDATE scurry_email_accounts SET
            access_token = ?,
            token_expires_at = ?,
            sync_error = NULL,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ");
    $stmt->execute([
        encryptToken($access_token),
        $token_expires_at,
        $account['id']
    ]);
    
    return $access_token;
}

/**
 * Validate RFC 5322 Message-ID style value and block header injection.
 */
function validateMessageIdHeader($value, $fieldName) {
    if (preg_match('/[\r\n]/', $value)) {
        errorResponse('VALIDATION_ERROR', "Field '{$fieldName}' contains invalid control characters", 400);
    }

    $value = trim($value);
    if (!preg_match('/^<[^<>\s@]+@[^<>\s@]+>$/', $value)) {
        errorResponse('VALIDATION_ERROR', "Field '{$fieldName}' must be a valid Message-ID like <id@example.com>", 400);
    }

    return $value;
}

/**
 * Validate References header as one or more Message-ID values separated by whitespace.
 */
function validateReferencesHeader($value, $fieldName) {
    if (preg_match('/[\r\n]/', $value)) {
        errorResponse('VALIDATION_ERROR', "Field '{$fieldName}' contains invalid control characters", 400);
    }

    $value = trim(preg_replace('/\s+/', ' ', $value));
    if (!preg_match('/^<[^<>\s@]+@[^<>\s@]+>( <[^<>\s@]+@[^<>\s@]+>)*$/', $value)) {
        errorResponse('VALIDATION_ERROR', "Field '{$fieldName}' must contain valid Message-ID values", 400);
    }

    return $value;
}
