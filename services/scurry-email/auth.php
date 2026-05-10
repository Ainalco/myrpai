<?php
/**
 * 🐿️ Scurry Email API - JWT Authentication Middleware
 * 
 * Verifies Bearer token and returns user info
 */

require_once __DIR__ . '/config.php';
require_once __DIR__ . '/db.php';

/**
 * Get Bearer token from Authorization header
 */
function getBearerToken() {
    $headers = getallheaders();
    
    // Check for Authorization header (case-insensitive)
    $authHeader = null;
    foreach ($headers as $key => $value) {
        if (strtolower($key) === 'authorization') {
            $authHeader = $value;
            break;
        }
    }
    
    if (!$authHeader) {
        return null;
    }
    
    // Extract token from "Bearer {token}"
    if (preg_match('/Bearer\s+(.*)$/i', $authHeader, $matches)) {
        return $matches[1];
    }
    
    return null;
}

/**
 * Verify JWT token and get user info
 * Returns user array or null if invalid
 */
function verifyToken($token) {
    if (JWT_VERIFY_METHOD === 'local') {
        return verifyTokenLocal($token);
    } else {
        return verifyTokenApi($token);
    }
}

/**
 * Verify JWT locally using secret key
 */
function verifyTokenLocal($token) {
    try {
        $parts = explode('.', $token);
        if (count($parts) !== 3) {
            return null;
        }
        
        list($header, $payload, $signature) = $parts;
        
        // Verify signature
        $expectedSignature = base64UrlEncode(
            hash_hmac('sha256', "$header.$payload", JWT_SECRET, true)
        );
        
        if ($signature !== $expectedSignature) {
            return null;
        }
        
        // Decode payload
        $data = json_decode(base64UrlDecode($payload), true);
        
        // Check expiration
        if (isset($data['exp']) && $data['exp'] < time()) {
            return null;
        }
        
        return $data;
        
    } catch (Exception $e) {
        return null;
    }
}

/**
 * Verify JWT by calling your existing API
 */
function verifyTokenApi($token) {
    $ch = curl_init();
    curl_setopt_array($ch, [
        CURLOPT_URL => AUTH_API_URL,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_HTTPHEADER => [
            'Authorization: Bearer ' . $token,
            'Content-Type: application/json'
        ],
        CURLOPT_TIMEOUT => 10
    ]);
    
    $response = curl_exec($ch);
    $httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
    curl_close($ch);
    
    if ($httpCode !== 200) {
        return null;
    }
    
    $data = json_decode($response, true);
    
    if (!$data) {
        return null;
    }
    
    // Return user info from your API response
    // Adjust field names based on your API response structure
    return [
        'user_id' => $data['id'] ?? $data['user_id'] ?? null,
        'username' => $data['username'] ?? $data['name'] ?? null,
        'email' => $data['email'] ?? null
    ];
}

/**
 * Base64 URL encode
 */
function base64UrlEncode($data) {
    return rtrim(strtr(base64_encode($data), '+/', '-_'), '=');
}

/**
 * Base64 URL decode
 */
function base64UrlDecode($data) {
    return base64_decode(strtr($data, '-_', '+/'));
}

/**
 * Require authentication - call at start of protected endpoints
 * Returns user info or exits with error
 */
function requireAuth() {
    setCorsHeaders();
    
    $token = getBearerToken();
    
    if (!$token) {
        errorResponse('UNAUTHORIZED', 'Missing Authorization header. Use: Bearer {token}', 401);
    }
    
    $user = verifyToken($token);
    
    if (!$user) {
        errorResponse('UNAUTHORIZED', 'Invalid or expired token', 401);
    }
    
    // Get or create user in our database
    $db = getDB();
    
    $stmt = $db->prepare("SELECT * FROM scurry_users WHERE external_user_id = ?");
    $stmt->execute([$user['user_id']]);
    $gmailUser = $stmt->fetch();
    
    if (!$gmailUser) {
        // Create user in our system
        $stmt = $db->prepare("
            INSERT INTO scurry_users (external_user_id, username, email, created_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
        ");
        $stmt->execute([
            $user['user_id'],
            $user['username'] ?? null,
            $user['email'] ?? null
        ]);
        
        $user['gmail_user_id'] = $db->lastInsertId();
    } else {
        $user['gmail_user_id'] = $gmailUser['id'];
    }
    
    return $user;
}
