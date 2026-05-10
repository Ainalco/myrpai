<?php
/**
 * 🐿️ Scurry Outlook API - Check Replies
 * 
 * GET /outlook/email/replies.php?email_id=1 - Check reply for specific sent email
 * GET /outlook/email/replies.php?account_id=1 - Check all replies for account
 */

require_once __DIR__ . '/../auth.php';

setCorsHeaders();

$user = verifyAuth();
$pdo = getDbConnection();

$emailId = $_GET['email_id'] ?? null;
$accountId = $_GET['account_id'] ?? null;

if ($emailId) {
    // Check reply for specific email
    $stmt = $pdo->prepare("
        SELECT e.*, a.email_address as from_email 
        FROM scurry_outlook_sent_emails e
        JOIN scurry_outlook_accounts a ON e.account_id = a.id
        WHERE e.id = ? AND e.user_id = ?
    ");
    $stmt->execute([$emailId, $user['id']]);
    $email = $stmt->fetch();
    
    if (!$email) {
        errorResponse('NOT_FOUND', 'Email not found', 404);
    }
    
    // Get account with valid token
    $account = getAccountWithValidToken($email['account_id'], $user['id']);
    
    if (!$account) {
        errorResponse('ACCOUNT_ERROR', 'Outlook account not found or token expired', 401);
    }
    
    // Search for replies
    $reply = searchForReply(
        $account['access_token_decrypted'],
        $email['recipient_email'],
        $email['subject'],
        $email['sent_at']
    );
    
    // Update database if reply found
    if ($reply['has_reply'] && !$email['replied_at']) {
        $stmt = $pdo->prepare("UPDATE scurry_outlook_sent_emails SET replied_at = ?, reply_message_id = ? WHERE id = ?");
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
    $account = getAccountWithValidToken($accountId, $user['id']);
    
    if (!$account) {
        errorResponse('ACCOUNT_ERROR', 'Outlook account not found or token expired', 401);
    }
    
    // Get sent emails without replies
    $stmt = $pdo->prepare("
        SELECT * FROM scurry_outlook_sent_emails 
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
            $email['sent_at']
        );
        
        if ($reply['has_reply']) {
            $repliesFound++;
            
            // Update database
            $stmt = $pdo->prepare("UPDATE scurry_outlook_sent_emails SET replied_at = ?, reply_message_id = ? WHERE id = ?");
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
 * Search for reply in inbox
 */
function searchForReply($accessToken, $fromEmail, $originalSubject, $sentAt) {
    // Build search query - look for emails from the recipient after sent date
    $searchQuery = 'from:' . $fromEmail;
    
    // Also check for Re: subject
    $reSubject = 'Re: ' . preg_replace('/^Re:\s*/i', '', $originalSubject);
    
    $url = MICROSOFT_GRAPH_URL . '/me/messages';
    $params = [
        '$filter' => "from/emailAddress/address eq '" . $fromEmail . "' and receivedDateTime gt " . date('Y-m-d\TH:i:s\Z', strtotime($sentAt)),
        '$select' => 'id,subject,from,bodyPreview,receivedDateTime',
        '$orderby' => 'receivedDateTime desc',
        '$top' => 10
    ];
    
    $url .= '?' . http_build_query($params);
    
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
    $messages = $data['value'] ?? [];
    
    // Check each message for matching subject
    foreach ($messages as $msg) {
        $msgSubject = $msg['subject'] ?? '';
        
        // Check if subject matches (Re: original or contains original)
        if (stripos($msgSubject, $originalSubject) !== false || 
            stripos($msgSubject, preg_replace('/^Re:\s*/i', '', $originalSubject)) !== false) {
            
            return [
                'has_reply' => true,
                'reply_id' => $msg['id'],
                'from' => $msg['from']['emailAddress']['address'] ?? $fromEmail,
                'subject' => $msgSubject,
                'snippet' => $msg['bodyPreview'] ?? '',
                'received_at' => $msg['receivedDateTime'] ?? null,
                'replied_at' => $msg['receivedDateTime'] ?? date('Y-m-d H:i:s')
            ];
        }
    }
    
    return ['has_reply' => false];
}