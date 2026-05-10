<?php
// Health check for Docker
if (php_sapi_name() !== 'cli' && !isset($_GET['ui'])) {
    require_once __DIR__ . '/config.php';
    header('Content-Type: application/json');
    try {
        require_once __DIR__ . '/db.php';
        $db = getDB();
        $db->query('SELECT 1');
        echo json_encode(['status' => 'healthy', 'service' => 'scurry-email', 'database' => 'connected']);
    } catch (Exception $e) {
        http_response_code(503);
        echo json_encode(['status' => 'unhealthy', 'service' => 'scurry-email', 'error' => $e->getMessage()]);
    }
    exit;
}
?>
<?php
/**
 * Scurry Email System - API Test Page
 *
 * Visit: test.php?ui to see the test UI
 *
 * This page helps you test the API without a frontend
 */

require_once __DIR__ . '/config.php';

$base_url = APP_URL;
?>
<!DOCTYPE html>
<html>
<head>
    <title>🐿️ Scurry Email API Test</title>
    <style>
        * { box-sizing: border-box; }
        body { 
            font-family: 'Inter', Arial, sans-serif; 
            padding: 20px; 
            max-width: 1000px;
            margin: 0 auto;
            background: #FAFAFA;
            color: #3E2723;
        }
        h1 { color: #FF5722; }
        h2 { color: #795548; border-bottom: 2px solid #FFF8E1; padding-bottom: 10px; }
        .card {
            background: white;
            padding: 20px;
            border-radius: 10px;
            margin: 20px 0;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
        }
        .step {
            background: #FFF8E1;
            border-left: 4px solid #FF5722;
            padding: 15px;
            margin: 10px 0;
        }
        .step-number {
            background: #FF5722;
            color: white;
            width: 30px;
            height: 30px;
            border-radius: 50%;
            display: inline-flex;
            align-items: center;
            justify-content: center;
            margin-right: 10px;
            font-weight: bold;
        }
        code {
            background: #3E2723;
            color: #FFC107;
            padding: 2px 8px;
            border-radius: 4px;
            font-family: monospace;
        }
        pre {
            background: #3E2723;
            color: #FFF8E1;
            padding: 15px;
            border-radius: 10px;
            overflow-x: auto;
            font-size: 13px;
        }
        .url {
            background: #E8F5E9;
            padding: 10px;
            border-radius: 5px;
            font-family: monospace;
            word-break: break-all;
        }
        a { color: #FF5722; }
        button {
            background: #FF5722;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
        }
        button:hover { background: #E64A19; }
        input, textarea {
            width: 100%;
            padding: 10px;
            margin: 5px 0 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
        }
        .result {
            background: #f5f5f5;
            padding: 15px;
            border-radius: 5px;
            margin-top: 15px;
            display: none;
        }
        label { font-weight: bold; color: #795548; }
    </style>
</head>
<body>
    <h1>🐿️ Scurry Email API Test</h1>
    <p>Test the Gmail integration API without a frontend</p>

    <!-- Step 1: Connect Gmail -->
    <div class="card">
        <h2><span class="step-number">1</span> Connect Gmail Account</h2>
        
        <div class="step">
            <p><strong>First, get the OAuth URL:</strong></p>
            <div class="url">
                GET <?= $base_url ?>/auth/gmail/connect.php?user_id=1
            </div>
            <br>
            <button onclick="getAuthUrl()">Get Auth URL</button>
            <div id="auth-result" class="result"></div>
        </div>
        
        <div class="step">
            <p><strong>Then open the auth_url in your browser to authorize.</strong></p>
            <p>Google will redirect back to callback.php and save the tokens.</p>
        </div>
    </div>

    <!-- Step 2: List Accounts -->
    <div class="card">
        <h2><span class="step-number">2</span> List Connected Accounts</h2>
        
        <div class="step">
            <div class="url">
                GET <?= $base_url ?>/email/accounts.php?user_id=1
            </div>
            <br>
            <button onclick="getAccounts()">List Accounts</button>
            <div id="accounts-result" class="result"></div>
        </div>
    </div>

    <!-- Step 3: Send Email -->
    <div class="card">
        <h2><span class="step-number">3</span> Send Test Email</h2>
        
        <div class="step">
            <form id="send-form">
                <label>Account ID:</label>
                <input type="number" id="account_id" value="1" required>
                
                <label>To Email:</label>
                <input type="email" id="to_email" placeholder="recipient@example.com" required>
                
                <label>To Name:</label>
                <input type="text" id="to_name" placeholder="Recipient Name">
                
                <label>Subject:</label>
                <input type="text" id="subject" value="🐿️ Test Email from Scurry!" required>
                
                <label>Body (HTML):</label>
                <textarea id="body_html" rows="5" required><h1>Hello from Scurry! 🐿️</h1>
<p>This is a test email sent via the Gmail API.</p>
<p>If you're seeing this, the integration is working!</p>
<p>— The Caffeinated Squirrel</p></textarea>
                
                <button type="submit">Send Email</button>
            </form>
            <div id="send-result" class="result"></div>
        </div>
    </div>

    <!-- cURL Examples -->
    <div class="card">
        <h2>📋 cURL Examples</h2>
        
        <p><strong>Get Auth URL:</strong></p>
        <pre>curl "<?= $base_url ?>/auth/gmail/connect.php?user_id=1"</pre>
        
        <p><strong>List Accounts:</strong></p>
        <pre>curl "<?= $base_url ?>/email/accounts.php?user_id=1"</pre>
        
        <p><strong>Send Email:</strong></p>
        <pre>curl -X POST "<?= $base_url ?>/email/send.php" \
  -H "Content-Type: application/json" \
  -d '{
    "account_id": 1,
    "to": "recipient@example.com",
    "to_name": "Recipient",
    "subject": "Test Email",
    "body_html": "&lt;p&gt;Hello World&lt;/p&gt;"
  }'</pre>
    </div>

    <script>
        const BASE_URL = '<?= $base_url ?>';

        async function getAuthUrl() {
            const result = document.getElementById('auth-result');
            result.style.display = 'block';
            result.innerHTML = 'Loading...';
            
            try {
                const response = await fetch(BASE_URL + '/auth/gmail/connect.php?user_id=1');
                const data = await response.json();
                
                if (data.success) {
                    result.innerHTML = `
                        <p><strong>✅ Auth URL Generated!</strong></p>
                        <p><a href="${data.data.auth_url}" target="_blank">Click here to authorize Gmail</a></p>
                        <p><small>Or copy this URL:</small></p>
                        <textarea style="height: 100px; font-size: 11px;">${data.data.auth_url}</textarea>
                    `;
                } else {
                    result.innerHTML = '<p>❌ Error: ' + data.error.message + '</p>';
                }
            } catch (e) {
                result.innerHTML = '<p>❌ Error: ' + e.message + '</p>';
            }
        }

        async function getAccounts() {
            const result = document.getElementById('accounts-result');
            result.style.display = 'block';
            result.innerHTML = 'Loading...';
            
            try {
                const response = await fetch(BASE_URL + '/email/accounts.php?user_id=1');
                const data = await response.json();
                
                result.innerHTML = '<pre>' + JSON.stringify(data, null, 2) + '</pre>';
            } catch (e) {
                result.innerHTML = '<p>❌ Error: ' + e.message + '</p>';
            }
        }

        document.getElementById('send-form').addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const result = document.getElementById('send-result');
            result.style.display = 'block';
            result.innerHTML = 'Sending...';
            
            const payload = {
                account_id: parseInt(document.getElementById('account_id').value),
                to: document.getElementById('to_email').value,
                to_name: document.getElementById('to_name').value,
                subject: document.getElementById('subject').value,
                body_html: document.getElementById('body_html').value
            };
            
            try {
                const response = await fetch(BASE_URL + '/email/send.php', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                
                if (data.success) {
                    result.innerHTML = `
                        <p><strong>✅ Email Sent!</strong></p>
                        <pre>${JSON.stringify(data, null, 2)}</pre>
                    `;
                } else {
                    result.innerHTML = `<p>❌ Error: ${data.error.message}</p>`;
                }
            } catch (e) {
                result.innerHTML = '<p>❌ Error: ' + e.message + '</p>';
            }
        });
    </script>
</body>
</html>
