<?php
/**
 * 🐿️ Scurry Outlook API - Send Email
 * 
 * POST /outlook/email/send.php
 * 
 * Body:
 * {
 *   "account_id": 1,
 *   "to": "recipient@example.com",
 *   "to_name": "John Doe",
 *   "subject": "Hello!",
 *   "body": "<p>HTML content</p>",
 *   "cc": ["cc@example.com"],
 *   "bcc": ["bcc@example.com"],
 *   "track_opens": true,
 *   "track_clicks": true,
 *   "in_reply_to": "<message-id@example.com>",
 *   "references": "<message-id@example.com>"
 * }
 */

require_once __DIR__ . '/../auth.php';

setCorsHeaders();

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    errorResponse('METHOD_NOT_ALLOWED', 'POST method required', 405);
}

$user = verifyAuth();
$input = json_decode(file_get_contents('php://input'), true);

if (!$input) {
    errorResponse('INVALID_JSON', 'Invalid JSON body', 400);
}

// Validate required fields
$accountId = $input['account_id'] ?? null;
$to = $input['to'] ?? null;
$subject = $input['subject'] ?? null;
$body = $input['body'] ?? null;

if (!$accountId || !$to || !$subject || !$body) {
    errorResponse('MISSING_FIELDS', 'account_id, to, subject, and body are required', 400);
}

// Optional fields
$toName = $input['to_name'] ?? null;
$cc = $input['cc'] ?? null;
$bcc = $input['bcc'] ?? null;
$trackOpens = $input['track_opens'] ?? false;
$trackClicks = $input['track_clicks'] ?? false;
$inReplyTo = isset($input['in_reply_to']) ? trim($input['in_reply_to']) : '';
$references = isset($input['references']) ? trim($input['references']) : '';

if ($inReplyTo !== '') {
    $inReplyTo = validateMessageIdHeader($inReplyTo, 'in_reply_to');
}
if ($references !== '') {
    $references = validateReferencesHeader($references, 'references');
}

// Get account with valid token
$account = getAccountWithValidToken($accountId, $user['id']);

if (!$account) {
    errorResponse('ACCOUNT_ERROR', 'Outlook account not found or token expired. Please reconnect.', 401);
}

$accessToken = $account['access_token_decrypted'];
$pdo = getDbConnection();

// Strip HTML for plain text
$bodyText = strip_tags(str_replace(['<br>', '<br/>', '<br />'], "\n", $body));
$emailDomainPart = strrchr($account['email_address'], '@');
$fromDomain = $emailDomainPart !== false ? substr($emailDomainPart, 1) : 'scurry.local';
$fromDomain = $fromDomain !== '' ? $fromDomain : 'scurry.local';

// Create email record first
$stmt = $pdo->prepare("INSERT INTO scurry_outlook_sent_emails 
    (user_id, account_id, recipient_email, recipient_name, cc, bcc, subject, body_html, body_text, status, created_at) 
    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'pending', CURRENT_TIMESTAMP)");
$stmt->execute([
    $user['id'],
    $accountId,
    $to,
    $toName,
    $cc ? json_encode($cc) : null,
    $bcc ? json_encode($bcc) : null,
    $subject,
    $body,
    $bodyText
]);
$emailId = $pdo->lastInsertId();
$messageIdHeader = sprintf('<scurry-outlook-%d-%s@%s>', $emailId, bin2hex(random_bytes(8)), $fromDomain);

// Process body for tracking
$processedBody = $body;

if ($trackClicks) {
    $processedBody = preg_replace_callback(
        '/<a\s+([^>]*?)href=["\']([^"\']+)["\']([^>]*?)>/i',
        function($matches) use ($emailId) {
            $trackUrl = TRACKING_BASE_URL . '/click.php?id=' . $emailId . '&url=' . urlencode($matches[2]);
            return "<a {$matches[1]}href=\"{$trackUrl}\"{$matches[3]}>";
        },
        $processedBody
    );
}

if ($trackOpens) {
    $processedBody .= '<img src="' . TRACKING_BASE_URL . '/open.php?id=' . $emailId . '" width="1" height="1" style="display:none;" />';
}

// Build message for Microsoft Graph
$message = [
    'message' => [
        'subject' => $subject,
        'body' => [
            'contentType' => 'HTML',
            'content' => $processedBody
        ],
        'toRecipients' => [
            [
                'emailAddress' => [
                    'address' => $to,
                    'name' => $toName ?? $to
                ]
            ]
        ]
    ],
    'saveToSentItems' => true
];

$headers = [
    ['name' => 'Message-ID', 'value' => $messageIdHeader],
];
if (!empty($inReplyTo)) {
    $headers[] = ['name' => 'In-Reply-To', 'value' => $inReplyTo];
}
if (!empty($references)) {
    $headers[] = ['name' => 'References', 'value' => $references];
}
$message['message']['internetMessageHeaders'] = $headers;

// Add CC
if (!empty($cc)) {
    $message['message']['ccRecipients'] = array_map(function($email) {
        return ['emailAddress' => ['address' => $email]];
    }, (array)$cc);
}

// Add BCC
if (!empty($bcc)) {
    $message['message']['bccRecipients'] = array_map(function($email) {
        return ['emailAddress' => ['address' => $email]];
    }, (array)$bcc);
}

// Send via Microsoft Graph
$ch = curl_init(MICROSOFT_GRAPH_URL . '/me/sendMail');
curl_setopt_array($ch, [
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => json_encode($message),
    CURLOPT_HTTPHEADER => [
        'Authorization: Bearer ' . $accessToken,
        'Content-Type: application/json'
    ],
    CURLOPT_TIMEOUT => 30
]);

$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$curlError = curl_error($ch);
curl_close($ch);

if ($curlError) {
    $stmt = $pdo->prepare("UPDATE scurry_outlook_sent_emails SET status = 'failed', error_message = ? WHERE id = ?");
    $stmt->execute([$curlError, $emailId]);
    errorResponse('SEND_FAILED', 'Failed to send: ' . $curlError, 500);
}

// Microsoft returns 202 Accepted for sendMail
if ($httpCode === 202 || $httpCode === 200) {
    $stmt = $pdo->prepare("UPDATE scurry_outlook_sent_emails SET status = 'sent', sent_at = CURRENT_TIMESTAMP WHERE id = ?");
    $stmt->execute([$emailId]);
    
    jsonResponse([
        'success' => true,
        'message' => 'Email sent successfully',
        'data' => [
            'email_id' => (int)$emailId,
            'to' => $to,
            'subject' => $subject,
            'tracking_enabled' => $trackOpens || $trackClicks,
            'message_id_header' => $messageIdHeader,
        ]
    ]);
} else {
    $errorData = json_decode($response, true);
    $errorMessage = $errorData['error']['message'] ?? 'Unknown error (HTTP ' . $httpCode . ')';
    
    $stmt = $pdo->prepare("UPDATE scurry_outlook_sent_emails SET status = 'failed', error_message = ? WHERE id = ?");
    $stmt->execute([$errorMessage, $emailId]);
    
    errorResponse('SEND_FAILED', 'Failed to send: ' . $errorMessage, 500);
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
