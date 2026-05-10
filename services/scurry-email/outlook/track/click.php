<?php
/**
 * 🐿️ Scurry Outlook API - Click Tracking
 * 
 * GET /outlook/track/click.php?id=123&url=https://example.com
 */

require_once __DIR__ . '/../config.php';
require_once __DIR__ . '/../db.php';

$emailId = $_GET['id'] ?? null;
$url = $_GET['url'] ?? null;

if (!$url) {
    http_response_code(400);
    die('Missing URL');
}

$url = urldecode($url);

if (!filter_var($url, FILTER_VALIDATE_URL)) {
    http_response_code(400);
    die('Invalid URL');
}

if ($emailId) {
    try {
        $pdo = getDbConnection();
        
        // Check if email exists
        $stmt = $pdo->prepare("SELECT id, first_clicked_at FROM scurry_outlook_sent_emails WHERE id = ?");
        $stmt->execute([$emailId]);
        $email = $stmt->fetch();
        
        if ($email) {
            // Log tracking event
            $stmt = $pdo->prepare("INSERT INTO scurry_outlook_tracking 
                (email_id, event_type, url, ip_address, user_agent, created_at) 
                VALUES (?, 'click', ?, ?, ?, CURRENT_TIMESTAMP)");
            $stmt->execute([
                $emailId,
                $url,
                $_SERVER['REMOTE_ADDR'] ?? null,
                $_SERVER['HTTP_USER_AGENT'] ?? null
            ]);
            
            // Update email clicks count
            $updateSql = "UPDATE scurry_outlook_sent_emails SET clicks = clicks + 1, last_clicked_at = CURRENT_TIMESTAMP";
            if (!$email['first_clicked_at']) {
                $updateSql .= ", first_clicked_at = CURRENT_TIMESTAMP";
            }
            $updateSql .= " WHERE id = ?";
            
            $stmt = $pdo->prepare($updateSql);
            $stmt->execute([$emailId]);
        }
    } catch (Exception $e) {
        // Silently fail - still redirect user
    }
}

// Redirect to actual URL
header('Location: ' . $url, true, 302);
exit;
