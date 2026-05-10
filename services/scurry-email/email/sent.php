<?php
/**
 * 🐿️ Scurry Email API - List Sent Emails
 * 
 * GET /email/sent.php
 * 
 * Headers:
 *   Authorization: Bearer {jwt_token}
 * 
 * Query Parameters:
 *   account_id - Filter by account (optional)
 *   status - Filter by status: sent, failed, pending (optional)
 *   limit - Results per page (default: 50, max: 100)
 *   offset - Pagination offset (default: 0)
 */

require_once __DIR__ . '/../auth.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    errorResponse('METHOD_NOT_ALLOWED', 'Only GET method allowed', 405);
}

// Require authentication
$user = requireAuth();

$db = getDB();

// Get query parameters
$account_id = isset($_GET['account_id']) ? intval($_GET['account_id']) : null;
$status = isset($_GET['status']) ? $_GET['status'] : null;
$limit = isset($_GET['limit']) ? min(intval($_GET['limit']), 100) : 50;
$offset = isset($_GET['offset']) ? intval($_GET['offset']) : 0;

// Build query
$where = ["se.user_id = ?"];
$params = [$user['gmail_user_id']];

if ($account_id) {
    $where[] = "se.account_id = ?";
    $params[] = $account_id;
}

if ($status && in_array($status, ['sent', 'failed', 'pending'])) {
    $where[] = "se.status = ?";
    $params[] = $status;
}

$whereClause = implode(' AND ', $where);

// Get total count
$stmt = $db->prepare("SELECT COUNT(*) as total FROM scurry_sent_emails se WHERE {$whereClause}");
$stmt->execute($params);
$total = $stmt->fetch()['total'];

// Get emails
$params[] = $limit;
$params[] = $offset;

$stmt = $db->prepare("
    SELECT 
        se.id,
        se.account_id,
        ea.email_address as from_email,
        se.recipient_email,
        se.recipient_name,
        se.subject,
        se.status,
        se.gmail_message_id,
        se.gmail_thread_id,
        se.opens,
        se.clicks,
        se.first_opened_at,
        se.last_opened_at,
        se.first_clicked_at,
        se.last_clicked_at,
        se.sent_at,
        se.created_at
    FROM scurry_sent_emails se
    LEFT JOIN scurry_email_accounts ea ON se.account_id = ea.id
    WHERE {$whereClause}
    ORDER BY se.created_at DESC
    LIMIT ? OFFSET ?
");
$stmt->execute($params);
$emails = $stmt->fetchAll();

jsonResponse([
    'success' => true,
    'data' => [
        'emails' => $emails,
        'pagination' => [
            'total' => intval($total),
            'limit' => $limit,
            'offset' => $offset,
            'has_more' => ($offset + $limit) < $total
        ]
    ]
]);
