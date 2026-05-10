<?php
/**
 * 🐿️ Scurry Outlook API - Read Inbox
 * 
 * GET /outlook/email/inbox.php?account_id=1
 * GET /outlook/email/inbox.php?account_id=1&folder=sent
 * GET /outlook/email/inbox.php?account_id=1&search=invoice
 * GET /outlook/email/inbox.php?account_id=1&message_id=xxx
 */

require_once __DIR__ . '/../auth.php';

setCorsHeaders();

$user = verifyAuth();

// Get parameters
$accountId = $_GET['account_id'] ?? null;
$messageId = $_GET['message_id'] ?? null;
$limit = min((int)($_GET['limit'] ?? 20), 100);
$search = $_GET['search'] ?? '';
$folder = $_GET['folder'] ?? 'inbox';
$filter = $_GET['filter'] ?? '';
$skip = (int)($_GET['skip'] ?? 0);

if (!$accountId) {
    errorResponse('MISSING_PARAM', 'account_id is required', 400);
}

// Get account with valid token
$account = getAccountWithValidToken($accountId, $user['id']);

if (!$account) {
    errorResponse('ACCOUNT_ERROR', 'Outlook account not found or token expired', 401);
}

$accessToken = $account['access_token_decrypted'];

// Get single message
if ($messageId) {
    $result = getSingleMessage($accessToken, $messageId);
    if ($result['success']) {
        jsonResponse($result);
    } else {
        errorResponse('NOT_FOUND', $result['error'], 404);
    }
    exit;
}

// Build Graph API URL
$folderMap = [
    'inbox' => 'inbox',
    'sent' => 'sentitems',
    'sentitems' => 'sentitems',
    'drafts' => 'drafts',
    'deleted' => 'deleteditems',
    'deleteditems' => 'deleteditems',
    'junk' => 'junkemail',
    'junkemail' => 'junkemail'
];

$graphFolder = $folderMap[strtolower($folder)] ?? 'inbox';
$url = MICROSOFT_GRAPH_URL . "/me/mailFolders/{$graphFolder}/messages";

$params = [
    '$top' => $limit,
    '$skip' => $skip,
    '$select' => 'id,subject,from,toRecipients,ccRecipients,receivedDateTime,bodyPreview,isRead,flag,importance,hasAttachments',
    '$orderby' => 'receivedDateTime desc'
];

if ($search) {
    $params['$search'] = '"' . $search . '"';
    unset($params['$orderby']); // Can't use orderby with search
}

if ($filter) {
    $params['$filter'] = $filter;
}

$url .= '?' . http_build_query($params);

// Make request
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
    $errorData = json_decode($response, true);
    errorResponse('API_ERROR', $errorData['error']['message'] ?? 'Unknown error', $httpCode);
}

$data = json_decode($response, true);
$messages = $data['value'] ?? [];

// Format messages
$formattedMessages = array_map(function($msg) {
    return [
        'id' => $msg['id'],
        'subject' => $msg['subject'] ?? '(No Subject)',
        'from' => $msg['from']['emailAddress']['address'] ?? null,
        'from_name' => $msg['from']['emailAddress']['name'] ?? null,
        'to' => array_map(function($r) {
            return $r['emailAddress']['address'];
        }, $msg['toRecipients'] ?? []),
        'cc' => array_map(function($r) {
            return $r['emailAddress']['address'];
        }, $msg['ccRecipients'] ?? []),
        'date' => $msg['receivedDateTime'] ?? null,
        'snippet' => $msg['bodyPreview'] ?? '',
        'is_read' => $msg['isRead'] ?? false,
        'is_flagged' => ($msg['flag']['flagStatus'] ?? '') === 'flagged',
        'importance' => $msg['importance'] ?? 'normal',
        'has_attachments' => $msg['hasAttachments'] ?? false
    ];
}, $messages);

jsonResponse([
    'success' => true,
    'data' => [
        'emails' => $formattedMessages,
        'total' => count($formattedMessages),
        'folder' => $folder,
        'has_more' => isset($data['@odata.nextLink']),
        'next_skip' => count($formattedMessages) === $limit ? $skip + $limit : null
    ]
]);

/**
 * Get single message with full body
 */
function getSingleMessage($accessToken, $messageId) {
    $url = MICROSOFT_GRAPH_URL . "/me/messages/{$messageId}";
    $url .= '?$select=id,subject,from,toRecipients,ccRecipients,bccRecipients,receivedDateTime,body,isRead,flag,importance,hasAttachments';
    
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
        return ['success' => false, 'error' => 'Message not found'];
    }
    
    $msg = json_decode($response, true);
    
    // Get attachments if any
    $attachments = [];
    if ($msg['hasAttachments'] ?? false) {
        $attachments = getAttachments($accessToken, $messageId);
    }
    
    return [
        'success' => true,
        'data' => [
            'id' => $msg['id'],
            'subject' => $msg['subject'] ?? '(No Subject)',
            'from' => $msg['from']['emailAddress']['address'] ?? null,
            'from_name' => $msg['from']['emailAddress']['name'] ?? null,
            'to' => array_map(function($r) {
                return $r['emailAddress']['address'];
            }, $msg['toRecipients'] ?? []),
            'cc' => array_map(function($r) {
                return $r['emailAddress']['address'];
            }, $msg['ccRecipients'] ?? []),
            'bcc' => array_map(function($r) {
                return $r['emailAddress']['address'];
            }, $msg['bccRecipients'] ?? []),
            'date' => $msg['receivedDateTime'] ?? null,
            'body_html' => $msg['body']['content'] ?? '',
            'body_type' => $msg['body']['contentType'] ?? 'html',
            'is_read' => $msg['isRead'] ?? false,
            'is_flagged' => ($msg['flag']['flagStatus'] ?? '') === 'flagged',
            'importance' => $msg['importance'] ?? 'normal',
            'has_attachments' => $msg['hasAttachments'] ?? false,
            'attachments' => $attachments
        ]
    ];
}

/**
 * Get message attachments
 */
function getAttachments($accessToken, $messageId) {
    $url = MICROSOFT_GRAPH_URL . "/me/messages/{$messageId}/attachments";
    
    $ch = curl_init($url);
    curl_setopt_array($ch, [
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $accessToken
        ],
        CURLOPT_TIMEOUT => 30
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        return [];
    }
    
    $data = json_decode($response, true);
    
    return array_map(function($att) {
        return [
            'id' => $att['id'],
            'name' => $att['name'],
            'content_type' => $att['contentType'],
            'size' => $att['size'],
            'is_inline' => $att['isInline'] ?? false
        ];
    }, $data['value'] ?? []);
}
