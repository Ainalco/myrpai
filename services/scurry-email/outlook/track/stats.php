<?php
/**
 * 🐿️ Scurry Outlook API - Tracking Statistics
 * 
 * GET /outlook/track/stats.php - Overall stats
 * GET /outlook/track/stats.php?email_id=1 - Stats for specific email
 */

require_once __DIR__ . '/../auth.php';

setCorsHeaders();

$user = verifyAuth();
$pdo = getDbConnection();

$emailId = $_GET['email_id'] ?? null;

if ($emailId) {
    // Stats for specific email
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
    
    // Get unique opens and clicks
    $stmt = $pdo->prepare("
        SELECT 
            COUNT(DISTINCT CASE WHEN event_type = 'open' THEN ip_address END) as unique_opens,
            COUNT(DISTINCT CASE WHEN event_type = 'click' THEN CONCAT(ip_address, url) END) as unique_clicks
        FROM scurry_outlook_tracking
        WHERE email_id = ?
    ");
    $stmt->execute([$emailId]);
    $uniqueStats = $stmt->fetch();
    
    jsonResponse([
        'success' => true,
        'data' => [
            'email_id' => (int)$email['id'],
            'to' => $email['recipient_email'],
            'subject' => $email['subject'],
            'status' => $email['status'],
            'sent_at' => $email['sent_at'],
            'tracking' => [
                'opens' => (int)$email['opens'],
                'unique_opens' => (int)$uniqueStats['unique_opens'],
                'clicks' => (int)$email['clicks'],
                'unique_clicks' => (int)$uniqueStats['unique_clicks'],
                'first_opened_at' => $email['first_opened_at'],
                'last_opened_at' => $email['last_opened_at'],
                'first_clicked_at' => $email['first_clicked_at'],
                'last_clicked_at' => $email['last_clicked_at']
            ]
        ]
    ]);
    
} else {
    // Overall stats
    $stmt = $pdo->prepare("
        SELECT 
            COUNT(*) as total_sent,
            SUM(CASE WHEN status = 'sent' THEN 1 ELSE 0 END) as delivered,
            SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) as failed,
            SUM(opens) as total_opens,
            SUM(clicks) as total_clicks,
            SUM(CASE WHEN opens > 0 THEN 1 ELSE 0 END) as emails_opened,
            SUM(CASE WHEN clicks > 0 THEN 1 ELSE 0 END) as emails_clicked
        FROM scurry_outlook_sent_emails
        WHERE user_id = ?
    ");
    $stmt->execute([$user['id']]);
    $stats = $stmt->fetch();
    
    $totalSent = (int)$stats['delivered'];
    $openRate = $totalSent > 0 ? round(($stats['emails_opened'] / $totalSent) * 100, 1) : 0;
    $clickRate = $totalSent > 0 ? round(($stats['emails_clicked'] / $totalSent) * 100, 1) : 0;
    
    jsonResponse([
        'success' => true,
        'data' => [
            'total_sent' => (int)$stats['total_sent'],
            'delivered' => (int)$stats['delivered'],
            'failed' => (int)$stats['failed'],
            'total_opens' => (int)$stats['total_opens'],
            'total_clicks' => (int)$stats['total_clicks'],
            'emails_opened' => (int)$stats['emails_opened'],
            'emails_clicked' => (int)$stats['emails_clicked'],
            'open_rate' => $openRate . '%',
            'click_rate' => $clickRate . '%'
        ]
    ]);
}
