<?php
/**
 * 🐿️ Scurry Outlook API - Sent Emails History
 * 
 * GET /outlook/email/sent.php - List all
 * GET /outlook/email/sent.php?account_id=1 - Filter by account
 * GET /outlook/email/sent.php?status=sent - Filter by status
 */

require_once __DIR__ . '/../auth.php';

setCorsHeaders();

$user = verifyAuth();
$pdo = getDbConnection();

// Parameters
$accountId = $_GET['account_id'] ?? null;
$status = $_GET['status'] ?? null;
$limit = min((int)($_GET['limit'] ?? 50), 100);
$offset = (int)($_GET['offset'] ?? 0);

// Build query
$sql = "SELECT e.*, a.email_address as from_email 
        FROM scurry_outlook_sent_emails e
        JOIN scurry_outlook_accounts a ON e.account_id = a.id
        WHERE e.user_id = ?";
$params = [$user['id']];

if ($accountId) {
    $sql .= " AND e.account_id = ?";
    $params[] = $accountId;
}

if ($status) {
    $sql .= " AND e.status = ?";
    $params[] = $status;
}

$sql .= " ORDER BY e.created_at DESC LIMIT ? OFFSET ?";
$params[] = $limit;
$params[] = $offset;

$stmt = $pdo->prepare($sql);
$stmt->execute($params);
$emails = $stmt->fetchAll();

// Get total count
$countSql = "SELECT COUNT(*) FROM scurry_outlook_sent_emails WHERE user_id = ?";
$countParams = [$user['id']];

if ($accountId) {
    $countSql .= " AND account_id = ?";
    $countParams[] = $accountId;
}
if ($status) {
    $countSql .= " AND status = ?";
    $countParams[] = $status;
}

$stmt = $pdo->prepare($countSql);
$stmt->execute($countParams);
$total = $stmt->fetchColumn();

jsonResponse([
    'success' => true,
    'data' => [
        'emails' => array_map(function($e) {
            return [
                'id' => (int)$e['id'],
                'account_id' => (int)$e['account_id'],
                'from_email' => $e['from_email'],
                'to_email' => $e['recipient_email'],
                'to_name' => $e['recipient_name'],
                'subject' => $e['subject'],
                'status' => $e['status'],
                'error_message' => $e['error_message'],
                'opens' => (int)$e['opens'],
                'clicks' => (int)$e['clicks'],
                'first_opened_at' => $e['first_opened_at'],
                'last_opened_at' => $e['last_opened_at'],
                'first_clicked_at' => $e['first_clicked_at'],
                'last_clicked_at' => $e['last_clicked_at'],
                'sent_at' => $e['sent_at'],
                'created_at' => $e['created_at']
            ];
        }, $emails),
        'total' => (int)$total,
        'limit' => $limit,
        'offset' => $offset
    ]
]);
