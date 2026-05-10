<?php
/**
 * 🐿️ Scurry Email API - Click Tracking
 * 
 * GET /track/click.php?id={email_id}&url={encoded_url}
 * 
 * Logs the click event and redirects to the actual URL
 */

require_once __DIR__ . '/../config.php';
require_once __DIR__ . '/../db.php';

$email_id = isset($_GET['id']) ? intval($_GET['id']) : 0;
$url = isset($_GET['url']) ? $_GET['url'] : '';

// Validate URL
if (empty($url)) {
    header('HTTP/1.1 400 Bad Request');
    echo 'Missing URL parameter';
    exit;
}

// Decode URL if needed
$decoded_url = urldecode($url);

// Basic URL validation
if (!filter_var($decoded_url, FILTER_VALIDATE_URL)) {
    header('HTTP/1.1 400 Bad Request');
    echo 'Invalid URL';
    exit;
}

// Log click event
if ($email_id > 0) {
    try {
        $db = getDB();
        
        // Log click event
        $stmt = $db->prepare("
            INSERT INTO scurry_email_tracking (email_id, event_type, url, ip_address, user_agent, created_at)
            VALUES (?, 'click', ?, ?, ?, CURRENT_TIMESTAMP)
        ");
        $stmt->execute([
            $email_id,
            $decoded_url,
            $_SERVER['REMOTE_ADDR'] ?? null,
            $_SERVER['HTTP_USER_AGENT'] ?? null
        ]);
        
        // Update counters on scurry_sent_emails
        $stmt = $db->prepare("
            UPDATE scurry_sent_emails SET 
                clicks = clicks + 1,
                first_clicked_at = COALESCE(first_clicked_at, CURRENT_TIMESTAMP),
                last_clicked_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ");
        $stmt->execute([$email_id]);
        
    } catch (Exception $e) {
        // Silently fail - still redirect user
    }
}

// Redirect to actual URL
header('HTTP/1.1 302 Found');
header('Location: ' . $decoded_url);
header('Cache-Control: no-store, no-cache, must-revalidate');
exit;
