<?php
/**
 * 🐿️ Scurry Email API - Get Current User (DEBUG VERSION)
 * 
 * GET /auth/user.php
 */

error_reporting(E_ALL);
ini_set('display_errors', 1);

header('Content-Type: application/json');
header('Access-Control-Allow-Origin: *');
header('Access-Control-Allow-Methods: GET, POST, OPTIONS');
header('Access-Control-Allow-Headers: Content-Type, Authorization');

if ($_SERVER['REQUEST_METHOD'] === 'OPTIONS') {
    http_response_code(200);
    exit;
}

// Debug: Check if files exist
$config_path = __DIR__ . '/../config.php';
$db_path = __DIR__ . '/../db.php';
$auth_path = __DIR__ . '/../auth.php';

$debug = [
    'step' => 'init',
    'config_exists' => file_exists($config_path),
    'db_exists' => file_exists($db_path),
    'auth_exists' => file_exists($auth_path),
];

if (!file_exists($config_path)) {
    echo json_encode(['error' => 'config.php not found', 'debug' => $debug]);
    exit;
}

require_once $config_path;
require_once $db_path;

$debug['step'] = 'config_loaded';
$debug['jwt_method'] = defined('JWT_VERIFY_METHOD') ? JWT_VERIFY_METHOD : 'not defined';
$debug['auth_api_url'] = defined('AUTH_API_URL') ? AUTH_API_URL : 'not defined';

// Get Authorization header
$headers = getallheaders();
$authHeader = null;
foreach ($headers as $key => $value) {
    if (strtolower($key) === 'authorization') {
        $authHeader = $value;
        break;
    }
}

$debug['step'] = 'headers_checked';
$debug['auth_header_found'] = !empty($authHeader);
$debug['auth_header_preview'] = $authHeader ? substr($authHeader, 0, 30) . '...' : null;

if (!$authHeader) {
    echo json_encode([
        'success' => false,
        'error' => 'Missing Authorization header',
        'debug' => $debug,
        'all_headers' => $headers
    ], JSON_PRETTY_PRINT);
    exit;
}

// Extract token
$token = null;
if (preg_match('/Bearer\s+(.*)$/i', $authHeader, $matches)) {
    $token = $matches[1];
}

$debug['step'] = 'token_extracted';
$debug['token_found'] = !empty($token);
$debug['token_preview'] = $token ? substr($token, 0, 30) . '...' : null;

if (!$token) {
    echo json_encode([
        'success' => false,
        'error' => 'Could not extract Bearer token',
        'debug' => $debug
    ], JSON_PRETTY_PRINT);
    exit;
}

// Call your auth API to verify token
$debug['step'] = 'calling_auth_api';
$debug['calling_url'] = AUTH_API_URL;

$ch = curl_init();
curl_setopt_array($ch, [
    CURLOPT_URL => AUTH_API_URL,
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_HTTPHEADER => [
        'Authorization: Bearer ' . $token,
        'Content-Type: application/json'
    ],
    CURLOPT_TIMEOUT => 10,
    CURLOPT_SSL_VERIFYPEER => false // For testing
]);

$response = curl_exec($ch);
$httpCode = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$curlError = curl_error($ch);
curl_close($ch);

$debug['step'] = 'auth_api_called';
$debug['auth_api_http_code'] = $httpCode;
$debug['auth_api_curl_error'] = $curlError ?: null;
$debug['auth_api_response_raw'] = $response;
$debug['auth_api_response_parsed'] = json_decode($response, true);

if ($httpCode !== 200) {
    echo json_encode([
        'success' => false,
        'error' => 'Auth API returned non-200 status',
        'debug' => $debug
    ], JSON_PRETTY_PRINT);
    exit;
}

$userData = json_decode($response, true);

if (!$userData) {
    echo json_encode([
        'success' => false,
        'error' => 'Could not parse auth API response as JSON',
        'debug' => $debug
    ], JSON_PRETTY_PRINT);
    exit;
}

$debug['step'] = 'user_data_parsed';
$debug['user_data_keys'] = array_keys($userData);

// Try to extract user info - ADJUST THESE BASED ON YOUR API RESPONSE
$user = [
    'user_id' => $userData['id'] ?? $userData['user_id'] ?? $userData['data']['id'] ?? null,
    'username' => $userData['username'] ?? $userData['name'] ?? $userData['data']['username'] ?? null,
    'email' => $userData['email'] ?? $userData['data']['email'] ?? null
];

$debug['step'] = 'user_extracted';
$debug['extracted_user'] = $user;

if (!$user['user_id']) {
    echo json_encode([
        'success' => false,
        'error' => 'Could not find user_id in auth response. Check the response structure.',
        'debug' => $debug,
        'hint' => 'Look at auth_api_response_parsed to see the actual structure'
    ], JSON_PRETTY_PRINT);
    exit;
}

// Try database connection
$debug['step'] = 'connecting_database';

try {
    $dsn = "pgsql:host=" . DB_HOST . ";port=" . DB_PORT . ";dbname=" . DB_NAME;
    $pdo = new PDO(
        $dsn,
        DB_USER,
        DB_PASS,
        [PDO::ATTR_ERRMODE => PDO::ERRMODE_EXCEPTION]
    );
    $debug['database_connected'] = true;
} catch (PDOException $e) {
    echo json_encode([
        'success' => false,
        'error' => 'Database connection failed: ' . $e->getMessage(),
        'debug' => $debug
    ], JSON_PRETTY_PRINT);
    exit;
}

// Check if scurry_users table exists
$debug['step'] = 'checking_tables';

try {
    $stmt = $pdo->query("SELECT to_regclass('scurry_users')");
    $tableExists = $stmt->fetchColumn() !== null;
    $debug['scurry_users_table_exists'] = $tableExists;

    if (!$tableExists) {
        echo json_encode([
            'success' => false,
            'error' => 'Table scurry_users does not exist. Run the Alembic migration first!',
            'debug' => $debug
        ], JSON_PRETTY_PRINT);
        exit;
    }
} catch (PDOException $e) {
    echo json_encode([
        'success' => false,
        'error' => 'Table check failed: ' . $e->getMessage(),
        'debug' => $debug
    ], JSON_PRETTY_PRINT);
    exit;
}

// Get or create gmail user
$debug['step'] = 'get_or_create_user';

$stmt = $pdo->prepare("SELECT * FROM scurry_users WHERE external_user_id = ?");
$stmt->execute([$user['user_id']]);
$gmailUser = $stmt->fetch(PDO::FETCH_ASSOC);

if (!$gmailUser) {
    $stmt = $pdo->prepare("
        INSERT INTO scurry_users (external_user_id, username, email, created_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    ");
    $stmt->execute([
        $user['user_id'],
        $user['username'],
        $user['email']
    ]);
    $gmailUserId = $pdo->lastInsertId();
    $debug['user_created'] = true;
} else {
    $gmailUserId = $gmailUser['id'];
    $debug['user_existed'] = true;
}

$debug['gmail_user_id'] = $gmailUserId;

// Get connected accounts
$debug['step'] = 'getting_accounts';

$stmt = $pdo->prepare("
    SELECT id, email_address, display_name, is_active, created_at
    FROM scurry_email_accounts 
    WHERE user_id = ? AND is_active = TRUE
");
$stmt->execute([$gmailUserId]);
$accounts = $stmt->fetchAll(PDO::FETCH_ASSOC);

$debug['step'] = 'complete';

// SUCCESS!
echo json_encode([
    'success' => true,
    'data' => [
        'user_id' => $gmailUserId,
        'external_user_id' => $user['user_id'],
        'username' => $user['username'],
        'email' => $user['email'],
        'gmail_connected' => count($accounts) > 0,
        'gmail_accounts' => $accounts
    ],
    'debug' => $debug
], JSON_PRETTY_PRINT);