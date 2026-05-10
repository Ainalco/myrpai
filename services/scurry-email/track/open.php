<?php
/**
 * 🐿️ Scurry Email API - Open Tracking Pixel
 * 
 * GET /track/open.php?id={email_id}
 * 
 * Returns a 1x1 transparent GIF and logs the open event
 */

require_once __DIR__ . '/../config.php';
require_once __DIR__ . '/../db.php';

$email_id = isset($_GET['id']) ? intval($_GET['id']) : 0;

if ($email_id > 0) {
    try {
        $db = getDB();
        
        // Log open event
        $stmt = $db->prepare("
            INSERT INTO scurry_email_tracking (email_id, event_type, ip_address, user_agent, created_at)
            VALUES (?, 'open', ?, ?, CURRENT_TIMESTAMP)
        ");
        $stmt->execute([
            $email_id,
            $_SERVER['REMOTE_ADDR'] ?? null,
            $_SERVER['HTTP_USER_AGENT'] ?? null
        ]);
        
        // Update counters on scurry_sent_emails
        $stmt = $db->prepare("
            UPDATE scurry_sent_emails SET 
                opens = opens + 1,
                first_opened_at = COALESCE(first_opened_at, CURRENT_TIMESTAMP),
                last_opened_at = CURRENT_TIMESTAMP
            WHERE id = ?
        ");
        $stmt->execute([$email_id]);
        
    } catch (Exception $e) {
        // Silently fail - don't break the email display
    }
}

// Return 1x1 transparent GIF
header('Content-Type: image/gif');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('Pragma: no-cache');
header('Expires: Thu, 01 Jan 1970 00:00:00 GMT');

// 1x1 transparent GIF (43 bytes)
echo base64_decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7');
