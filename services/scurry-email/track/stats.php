<?php
/**
 * 🐿️ Scurry Email API - Tracking Statistics
 * 
 * GET /track/stats.php
 * 
 * Headers:
 *   Authorization: Bearer {jwt_token}
 * 
 * Query Parameters:
 *   email_id - Get stats for specific email (optional)
 *   account_id - Filter by account (optional)
 *   days - Stats for last N days (default: 30)
 */

require_once __DIR__ . '/../auth.php';

if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    errorResponse('METHOD_NOT_ALLOWED', 'Only GET method allowed', 405);
}

// Require authentication
$user = requireAuth();

$db = getDB();

$email_id = isset($_GET['email_id']) ? intval($_GET['email_id']) : null;
$account_id = isset($_GET['account_id']) ? intval($_GET['account_id']) : null;
$days = isset($_GET['days']) ? intval($_GET['days']) : 30;

// If specific email requested
if ($email_id) {
    // Verify ownership
    $stmt = $db->prepare("SELECT * FROM scurry_sent_emails WHERE id = ? AND user_id = ?");
    $stmt->execute([$email_id, $user['gmail_user_id']]);
    $email = $stmt->fetch();
    
    if (!$email) {
        errorResponse('EMAIL_NOT_FOUND', 'Email not found or access denied', 404);
    }
    
    // Get tracking events for this email
    $stmt = $db->prepare("
        SELECT 
            event_type,
            COUNT(*) as count,
            MIN(created_at) as first_at,
            MAX(created_at) as last_at
        FROM scurry_email_tracking 
        WHERE email_id = ?
        GROUP BY event_type
    ");
    $stmt->execute([$email_id]);
    $events = $stmt->fetchAll();
    
    $stats = [
        'opens' => 0,
        'clicks' => 0,
        'first_opened_at' => null,
        'last_opened_at' => null,
        'first_clicked_at' => null,
        'last_clicked_at' => null,
        'unique_clicks' => []
    ];
    
    foreach ($events as $event) {
        if ($event['event_type'] === 'open') {
            $stats['opens'] = $event['count'];
            $stats['first_opened_at'] = $event['first_at'];
            $stats['last_opened_at'] = $event['last_at'];
        } elseif ($event['event_type'] === 'click') {
            $stats['clicks'] = $event['count'];
            $stats['first_clicked_at'] = $event['first_at'];
            $stats['last_clicked_at'] = $event['last_at'];
        }
    }
    
    // Get clicked URLs
    $stmt = $db->prepare("
        SELECT url, COUNT(*) as clicks 
        FROM scurry_email_tracking 
        WHERE email_id = ? AND event_type = 'click' AND url IS NOT NULL
        GROUP BY url
        ORDER BY clicks DESC
    ");
    $stmt->execute([$email_id]);
    $stats['unique_clicks'] = $stmt->fetchAll();
    
    jsonResponse([
        'success' => true,
        'data' => [
            'email_id' => $email_id,
            'subject' => $email['subject'],
            'recipient' => $email['recipient_email'],
            'sent_at' => $email['sent_at'],
            'stats' => $stats
        ]
    ]);
}

// Overall stats
$where = ["se.user_id = ?", "se.created_at >= CURRENT_TIMESTAMP - INTERVAL '1 day' * ?"];
$params = [$user['gmail_user_id'], $days];

if ($account_id) {
    $where[] = "se.account_id = ?";
    $params[] = $account_id;
}

$whereClause = implode(' AND ', $where);

// Get summary stats
$stmt = $db->prepare("
    SELECT 
        COUNT(*) as total_emails,
        SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as sent,
        SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
        SUM(opens) as total_opens,
        SUM(clicks) as total_clicks,
        SUM(CASE WHEN opens > 0 THEN 1 ELSE 0 END) as emails_opened,
        SUM(CASE WHEN clicks > 0 THEN 1 ELSE 0 END) as emails_clicked
    FROM scurry_sent_emails se
    WHERE {$whereClause}
");
$stmt->execute($params);
$summary = $stmt->fetch();

// Calculate rates
$sent = intval($summary['sent']);
$open_rate = $sent > 0 ? round((intval($summary['emails_opened']) / $sent) * 100, 2) : 0;
$click_rate = $sent > 0 ? round((intval($summary['emails_clicked']) / $sent) * 100, 2) : 0;

// Daily breakdown
$stmt = $db->prepare("
    SELECT 
        se.sent_at::date as date,
        COUNT(*) as sent,
        SUM(opens) as opens,
        SUM(clicks) as clicks
    FROM scurry_sent_emails se
    WHERE {$whereClause} AND se.status = 'sent'
    GROUP BY se.sent_at::date
    ORDER BY date DESC
    LIMIT 30
");
$stmt->execute($params);
$daily = $stmt->fetchAll();

jsonResponse([
    'success' => true,
    'data' => [
        'period_days' => $days,
        'summary' => [
            'total_emails' => intval($summary['total_emails']),
            'sent' => $sent,
            'failed' => intval($summary['failed']),
            'total_opens' => intval($summary['total_opens']),
            'total_clicks' => intval($summary['total_clicks']),
            'emails_opened' => intval($summary['emails_opened']),
            'emails_clicked' => intval($summary['emails_clicked']),
            'open_rate' => $open_rate,
            'click_rate' => $click_rate
        ],
        'daily' => $daily
    ]
]);
