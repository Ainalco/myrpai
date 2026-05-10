<?php
/**
 * 🐿️ Scurry Outlook API - Open Tracking
 * 
 * GET /outlook/track/open.php?id=123
 */

require_once __DIR__ . '/../config.php';
require_once __DIR__ . '/../db.php';

$emailId = $_GET['id'] ?? null;

if ($emailId) {
    try {
        $pdo = getDbConnection();
        
        // Check if email exists
        $stmt = $pdo->prepare("SELECT id, first_opened_at FROM scurry_outlook_sent_emails WHERE id = ?");
        $stmt->execute([$emailId]);
        $email = $stmt->fetch();
        
        if ($email) {
            // Log tracking event
            $stmt = $pdo->prepare("INSERT INTO scurry_outlook_tracking 
                (email_id, event_type, ip_address, user_agent, created_at) 
                VALUES (?, 'open', ?, ?, CURRENT_TIMESTAMP)");
            $stmt->execute([
                $emailId,
                $_SERVER['REMOTE_ADDR'] ?? null,
                $_SERVER['HTTP_USER_AGENT'] ?? null
            ]);
            
            // Update email opens count
            $updateSql = "UPDATE scurry_outlook_sent_emails SET opens = opens + 1, last_opened_at = CURRENT_TIMESTAMP";
            if (!$email['first_opened_at']) {
                $updateSql .= ", first_opened_at = CURRENT_TIMESTAMP";
            }
            $updateSql .= " WHERE id = ?";
            
            $stmt = $pdo->prepare($updateSql);
            $stmt->execute([$emailId]);
        }
    } catch (Exception $e) {
        // Silently fail - don't break email display
    }
}

// Return 1x1 transparent GIF
header('Content-Type: image/gif');
header('Cache-Control: no-store, no-cache, must-revalidate, max-age=0');
header('Pragma: no-cache');

echo base64_decode('R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7');
