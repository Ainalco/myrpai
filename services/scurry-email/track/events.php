<?php
/**
 * 🐿️ Scurry Email API - Tracking Events
 * 
 * GET /track/events.php
 * 
 * Headers:
 *   Authorization: Bearer {jwt_token}
 * 
 * Query Parameters:
 *   email_id - Required: Get events for specific email
 *   event_type - Filter by type: open, click (optional)
 *   limit - Results per page (default: 100, max: 500)
 *   offset - Pagination offset (default: 0)
 */

require_once __DIR__ . '/../auth.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    errorResponse('METHOD_NOT_ALLOWED', 'Only GET method allowed', 405);
}

// Require authentication
$user = requireAuth();

$db = getDB();

$email_id = isset($_GET['email_id']) ? intval($_GET['email_id']) : null;
$event_type = isset($_GET['event_type']) ? $_GET['event_type'] : null;
$limit = isset($_GET['limit']) ? min(intval($_GET['limit']), 500) : 100;
$offset = isset($_GET['offset']) ? intval($_GET['offset']) : 0;

if (!$email_id) {
    errorResponse('VALIDATION_ERROR', 'email_id is required', 400);
}

// Verify email ownership
$stmt = $db->prepare("SELECT id, subject, recipient_email FROM scurry_sent_emails WHERE id = ? AND user_id = ?");
$stmt->execute([$email_id, $user['gmail_user_id']]);
$email = $stmt->fetch();

if (!$email) {
    errorResponse('EMAIL_NOT_FOUND', 'Email not found or access denied', 404);
}

// Build query
$where = ["email_id = ?"];
$params = [$email_id];

if ($event_type && in_array($event_type, ['open', 'click'])) {
    $where[] = "event_type = ?";
    $params[] = $event_type;
}

$whereClause = implode(' AND ', $where);

// Get total count
$stmt = $db->prepare("SELECT COUNT(*) as total FROM scurry_email_tracking WHERE {$whereClause}");
$stmt->execute($params);
$total = $stmt->fetch()['total'];

// Get events
$params[] = $limit;
$params[] = $offset;

$stmt = $db->prepare("
    SELECT 
        id,
        event_type,
        url,
        ip_address,
        user_agent,
        created_at
    FROM scurry_email_tracking
    WHERE {$whereClause}
    ORDER BY created_at DESC
    LIMIT ? OFFSET ?
");
$stmt->execute($params);
$events = $stmt->fetchAll();

jsonResponse([
    'success' => true,
    'data' => [
        'email' => [
            'id' => $email['id'],
            'subject' => $email['subject'],
            'recipient' => $email['recipient_email']
        ],
        'events' => $events,
        'pagination' => [
            'total' => intval($total),
            'limit' => $limit,
            'offset' => $offset,
            'has_more' => ($offset + $limit) < $total
        ]
    ]
]);
