<?php
/**
 * 🐿️ Scurry Outlook API - Tracking Events
 * 
 * GET /outlook/track/events.php?email_id=1
 */

require_once __DIR__ . '/../auth.php';

setCorsHeaders();

$user = verifyAuth();

$emailId = $_GET['email_id'] ?? null;

if (!$emailId) {
    errorResponse('MISSING_PARAM', 'email_id is required', 400);
}

$pdo = getDbConnection();

// Verify email belongs to user
$stmt = $pdo->prepare("SELECT id FROM scurry_outlook_sent_emails WHERE id = ? AND user_id = ?");
$stmt->execute([$emailId, $user['id']]);

if (!$stmt->fetch()) {
    errorResponse('NOT_FOUND', 'Email not found', 404);
}

// Get events
$stmt = $pdo->prepare("
    SELECT event_type, url, ip_address, user_agent, created_at
    FROM scurry_outlook_tracking
    WHERE email_id = ?
    ORDER BY created_at DESC
");
$stmt->execute([$emailId]);
$events = $stmt->fetchAll();

jsonResponse([
    'success' => true,
    'data' => [
        'email_id' => (int)$emailId,
        'events' => array_map(function($e) {
            return [
                'type' => $e['event_type'],
                'url' => $e['url'],
                'ip_address' => $e['ip_address'],
                'user_agent' => $e['user_agent'],
                'timestamp' => $e['created_at']
            ];
        }, $events),
        'total' => count($events)
    ]
]);
