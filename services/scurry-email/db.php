<?php
/**
 * 🐿️ Scurry Email API - Database & Helpers
 */

require_once __DIR__ . '/config.php';

/**
 * Get PDO database connection
 */
function getDB() {
    return getDbConnection();
}

/**
 * Get PDO database connection (primary function)
 */
function getDbConnection() {
    static $pdo = null;
    
    if ($pdo === null) {
        try {
            $dsn = "pgsql:host=" . DB_HOST . ";port=" . DB_PORT . ";dbname=" . DB_NAME;
            $pdo = new PDO(
                $dsn,
                DB_USER,
                DB_PASS,
                [
                    PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION,
                    PDO::ATTR_DEFAULT_FETCH_MODE => PDO::FETCH_ASSOC,
                    PDO::ATTR_EMULATE_PREPARES => false
                ]
            );
        } catch (PDOException $e) {
            errorResponse('DATABASE_ERROR', 'Database connection failed', 500);
        }
    }
    
    return $pdo;
}

/**
 * Return JSON success response
 */
function jsonResponse($data, $code = 200) {
    http_response_code($code);
    header('Content-Type: application/json');
    echo json_encode($data, JSON_PRETTY_PRINT);
    exit;
}

/**
 * Return JSON error response
 */
function errorResponse($code, $message, $httpCode = 400) {
    http_response_code($httpCode);
    header('Content-Type: application/json');
    echo json_encode([
        'success' => false,
        'error' => [
            'code' => $code,
            'message' => $message
        ]
    ], JSON_PRETTY_PRINT);
    exit;
}

/**
 * Encrypt token for storage
 */
function encryptToken($token) {
    $key = base64_decode(ENCRYPTION_KEY);
    $iv = random_bytes(16);
    $encrypted = openssl_encrypt($token, 'AES-256-CBC', $key, 0, $iv);
    return base64_encode($iv . '::' . $encrypted);
}

/**
 * Decrypt token from storage
 */
function decryptToken($encryptedToken) {
    $key = base64_decode(ENCRYPTION_KEY);
    $parts = explode('::', base64_decode($encryptedToken), 2);
    if (count($parts) !== 2) return null;
    
    list($iv, $encrypted) = $parts;
    return openssl_decrypt($encrypted, 'AES-256-CBC', $key, 0, $iv);
}

/**
 * Set CORS headers
 */
function setCorsHeaders() {
    header('Access-Control-Allow-Origin: ' . CORS_ALLOWED_ORIGINS);
    header('Access-Control-Allow-Methods: GET, POST, PUT, DELETE, OPTIONS');
    header('Access-Control-Allow-Headers: Content-Type, Authorization');
    
    if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
        http_response_code(200);
        exit;
    }
}