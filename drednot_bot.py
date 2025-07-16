# drednot_bot.py
# Final version, optimized for Render/Docker with memory leak protection.
# This version dynamically fetches commands, sends chat via WebSocket,
# and includes robust process cleanup to prevent memory leaks.

import os
import queue
import atexit
import logging
import threading
import traceback
import requests
import time
from datetime import datetime
from collections import deque
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin 

# NEW IMPORT for process cleanup
import psutil

from flask import Flask, Response, request, redirect, url_for
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException, TimeoutException

# --- CONFIGURATION ---
BOT_SERVER_URL = os.environ.get("BOT_SERVER_URL")
API_KEY = 'drednot123'
SHIP_INVITE_LINK = 'https://drednot.io/invite/KOciB52Quo4z_luxo7zAFKPc'

ANONYMOUS_LOGIN_KEY = '_M85tFxFxIRDax_nh-HYm1gT' # Replace with your key if needed

# Bot Behavior
MESSAGE_DELAY_SECONDS = 0.2
ZWSP = '\u200B'
INACTIVITY_TIMEOUT_SECONDS = 2 * 60
MAIN_LOOP_POLLING_INTERVAL_SECONDS = 0.1 # Slightly increased to reduce idle CPU
MAX_WORKER_THREADS = 10

# Spam Control
USER_COOLDOWN_SECONDS = 2.0
SPAM_STRIKE_LIMIT = 3
SPAM_TIMEOUT_SECONDS = 30
SPAM_RESET_SECONDS = 5

# --- LOGGING & VALIDATION ---
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] [%(levelname)s] %(message)s', datefmt='%Y-%m-%d %H:%M:%S')

if not BOT_SERVER_URL: logging.critical("FATAL: BOT_SERVER_URL environment variable is not set!"); exit(1)
if not SHIP_INVITE_LINK: logging.critical("FATAL: SHIP_INVITE_LINK environment variable is not set!"); exit(1)
if not API_KEY: logging.critical("FATAL: API_KEY environment variable is not set!"); exit(1)

# --- UPDATED UNIFIED JAVASCRIPT INJECTION SCRIPT (with memory leak fix) ---
UNIFIED_CLIENT_SCRIPT = """
    // Part 1: WebSocket Capture and Sender
    console.log('[Bot-JS] Initializing WebSocket Interceptor...');
    window.active_ws_connection = null;
    const OriginalWebSocket = window.WebSocket;
    window.WebSocket = function(url, protocols) {
        const wsInstance = new OriginalWebSocket(url, protocols);
        console.log('[Bot-JS] Game WebSocket created. Capturing instance.');
        wsInstance.addEventListener('open', () => {
            console.log('[Bot-JS] WebSocket connection is OPEN.');
            window.active_ws_connection = wsInstance;
        });
        wsInstance.addEventListener('close', (event) => {
            console.warn(`[Bot-JS] WebSocket connection CLOSED. Code: ${event.code}`);
            if (window.active_ws_connection === wsInstance) window.active_ws_connection = null;
        });
        wsInstance.addEventListener('error', (event) => console.error('[Bot-JS] WebSocket Error:', event));
        return wsInstance;
    };
    window.py_send_chat_ws = function(message) {
        if (!window.active_ws_connection || window.active_ws_connection.readyState !== 1) {
            console.error('[Bot-JS] Send failed: WebSocket is not active.');
            return false;
        }
        if (typeof window.msgpack?.encode !== 'function') {
            console.error('[Bot-JS] Send failed: msgpack library not found.');
            return false;
        }
        try {
            const encodedMessage = window.msgpack.encode({ type: 2, msg: message });
            window.active_ws_connection.send(encodedMessage);
            return true;
        } catch (e) {
            console.error('[Bot-JS] Error encoding or sending WebSocket message:', e);
            return false;
        }
    };
    // Part 2: Chat Observer (Reading Messages)
    if (window.drednotBotMutationObserver) window.drednotBotMutationObserver.disconnect();
    window.isDrednotBotObserverActive = true;
    console.log('[Bot-JS] Initializing Observer with Dynamic Command List...');
    window.py_bot_events = [];
    const [zwsp, allCommands, cooldownMs, spamStrikeLimit, spamTimeoutMs, spamResetMs] = arguments;
    const commandSet = new Set(allCommands);
    window.botUserCooldowns = window.botUserCooldowns || {};
    window.botSpamTracker = window.botSpamTracker || {};
    const targetNode = document.getElementById('chat-content');
    if (!targetNode) return;
    const callback = (mutationList, observer) => {
        const now = Date.now();
        // *** NEW JS MEMORY LEAK FIX ***
        // Every 50 commands, clean up trackers for users not seen in 30 minutes.
        window.botCmdCounter = (window.botCmdCounter || 0) + 1;
        if (window.botCmdCounter % 50 === 0) {
            const cleanupTime = now - (1000 * 60 * 30); // 30 minutes
            let cleanedCount = 0;
            for (const user in window.botSpamTracker) {
                if (window.botSpamTracker[user].lastTime < cleanupTime) {
                    delete window.botSpamTracker[user];
                    cleanedCount++;
                }
            }
            for (const user in window.botUserCooldowns) {
                if (window.botUserCooldowns[user] < cleanupTime) {
                    delete window.botUserCooldowns[user];
                    cleanedCount++;
                }
            }
            if(cleanedCount > 0) console.log(`[Bot-JS] Cleaned up ${cleanedCount} old user entries from trackers.`);
        }
        // *** END OF FIX ***
        for (const mutation of mutationList) {
            if (mutation.type !== 'childList') continue;
            for (const node of mutation.addedNodes) {
                if (node.nodeType !== 1 || node.tagName !== 'P' || node.dataset.botProcessed) continue;
                node.dataset.botProcessed = 'true';
                const pText = node.textContent || "";
                if (pText.startsWith(zwsp)) continue;
                if (pText.includes("Joined ship '")) {
                    const match = pText.match(/{[A-Z\\d]+}/);
                    if (match && match[0]) window.py_bot_events.push({ type: 'ship_joined', id: match[0] });
                    continue;
                }
                const colonIdx = pText.indexOf(':');
                if (colonIdx === -1) continue;
                const bdiElement = node.querySelector("bdi");
                if (!bdiElement) continue;
                const username = bdiElement.innerText.trim();
                const msgTxt = pText.substring(colonIdx + 1).trim();
                if (!msgTxt.startsWith('!')) continue;
                const parts = msgTxt.slice(1).trim().split(/ +/);
                const command = parts.shift().toLowerCase();
                if (!commandSet.has(command)) continue;
                const spamTracker = window.botSpamTracker[username] = window.botSpamTracker[username] || { count: 0, lastCmd: '', lastTime: 0, penaltyUntil: 0 };
                if (now < spamTracker.penaltyUntil) continue;
                const lastCmdTime = window.botUserCooldowns[username] || 0;
                if (now - lastCmdTime < cooldownMs) continue;
                window.botUserCooldowns[username] = now;
                if (now - spamTracker.lastTime > spamResetMs || command !== spamTracker.lastCmd) spamTracker.count = 1; else spamTracker.count++;
                spamTracker.lastCmd = command; spamTracker.lastTime = now;
                if (spamTracker.count >= spamStrikeLimit) {
                    spamTracker.penaltyUntil = now + spamTimeoutMs;
                    spamTracker.count = 0;
                    window.py_bot_events.push({ type: 'spam_detected', username: username, command: command });
                    continue;
                }
                window.py_bot_events.push({ type: 'command', command: command, username: username, args: parts });
            }
        }
    };
    const observer = new MutationObserver(callback);
    observer.observe(targetNode, { childList: true });
    window.drednotBotMutationObserver = observer;
    console.log('[Bot-JS] Advanced Spam Detection and WebSocket sender are now active.');
"""

class InvalidKeyError(Exception): pass

# --- GLOBAL STATE & THREADING PRIMITIVES ---
message_queue = queue.Queue(maxsize=100)
action_queue = queue.Queue(maxsize=10)
driver_lock = Lock()
inactivity_timer = None
driver = None
SERVER_COMMAND_LIST = []
BOT_STATE = {"status": "Initializing...", "start_time": datetime.now(), "current_ship_id": "N/A", "last_command_info": "None yet.", "last_message_sent": "None yet.", "event_log": deque(maxlen=20)}
command_executor = ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS, thread_name_prefix='CmdWorker')
atexit.register(lambda: command_executor.shutdown(wait=True))

def log_event(message):
    timestamp = datetime.now().strftime('%H:%M:%S')
    full_message = f"[{timestamp}] {message}"
    BOT_STATE["event_log"].appendleft(full_message)
    logging.info(f"EVENT: {message}")

# --- BROWSER & FLASK SETUP ---
def setup_driver():
    logging.info("Launching headless browser for Docker environment...")
    chrome_options = Options()
    chrome_options.binary_location = "/usr/bin/chromium"
    chrome_options.add_argument("--headless=new")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--mute-audio")
    chrome_options.add_argument("--disable-setuid-sandbox")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    service = Service(executable_path="/usr/bin/chromedriver")
    return webdriver.Chrome(service=service, options=chrome_options)

flask_app = Flask('')
@flask_app.route('/')
def health_check():
    # Flask HTML remains the same
    html = f"""
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta http-equiv="refresh" content="10">
    <title>Drednot Bot Status</title><style>body{{font-family:'Courier New',monospace;background-color:#1e1e1e;color:#d4d4d4;padding:20px;}}.container{{max-width:800px;margin:auto;background-color:#252526;border:1px solid #373737;padding:20px;border-radius:8px;}}h1,h2{{color:#4ec9b0;border-bottom:1px solid #4ec9b0;padding-bottom:5px;}}p{{line-height:1.6;}}.status-ok{{color:#73c991;font-weight:bold;}}.status-warn{{color:#dccd85;font-weight:bold;}}.status-err{{color:#f44747;font-weight:bold;}}ul{{list-style-type:none;padding-left:0;}}li{{background-color:#2d2d2d;margin-bottom:8px;padding:10px;border-radius:4px;white-space:pre-wrap;word-break:break-all;}}.label{{color:#9cdcfe;font-weight:bold;}}.btn{{background-color:#4ec9b0;color:#1e1e1e;border:none;padding:10px 15px;border-radius:4px;cursor:pointer;font-weight:bold;font-size:1em;margin-top:20px;}}.btn:hover{{background-color:#63d8c1;}}</style></head>
    <body><div class="container"><h1>Drednot Bot Status</h1>
    <p><span class="label">Status:</span><span class="status-ok">{BOT_STATE['status']}</span></p>
    <p><span class="label">Current Ship ID:</span>{BOT_STATE['current_ship_id']}</p>
    <p><span class="label">Last Command:</span>{BOT_STATE['last_command_info']}</p>
    <p><span class="label">Last Message Sent:</span>{BOT_STATE['last_message_sent']}</p>
    <form action="/update_commands" method="post">
        <button type="submit" class="btn">Refresh Commands Live</button>
    </form>
    <h2>Recent Events (Log)</h2><ul>{''.join(f'<li>{event}</li>' for event in BOT_STATE['event_log'])}</ul></div></body></html>
    """
    return Response(html, mimetype='text/html')

@flask_app.route('/update_commands', methods=['POST'])
def trigger_command_update():
    log_event("WEB UI: Command update triggered.")
    def task():
        if fetch_command_list():
            queue_browser_update()
    command_executor.submit(task)
    return redirect(url_for('health_check'))

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    logging.info(f"Health check server listening on http://0.0.0.0:{port}")
    flask_app.run(host='0.0.0.0', port=port)

# --- HELPER & CORE FUNCTIONS ---
def queue_reply(message):
    MAX_LEN = 199
    lines = message if isinstance(message, list) else [message]
    for line in lines:
        text = str(line)
        while len(text) > 0:
            try:
                if len(text) <= MAX_LEN:
                    if text.strip(): message_queue.put(ZWSP + text, timeout=5)
                    break
                else:
                    bp = text.rfind(' ', 0, MAX_LEN)
                    chunk = text[:bp if bp > 0 else MAX_LEN].strip()
                    if chunk: message_queue.put(ZWSP + chunk, timeout=5)
                    text = text[bp if bp > 0 else MAX_LEN:].strip()
            except queue.Full:
                logging.warning("Message queue is full. Dropping message.")
                log_event("WARN: Message queue full.")
                break

def message_processor_thread():
    """Processes the message queue, sending replies via direct WebSocket injection."""
    while True:
        message = message_queue.get()
        try:
            with driver_lock:
                if driver:
                    success = driver.execute_script("return window.py_send_chat_ws(arguments[0]);", message)
                    if success:
                        clean_msg = message[1:] if message.startswith(ZWSP) else message
                        logging.info(f"SENT (WS): {clean_msg}")
                        BOT_STATE["last_message_sent"] = clean_msg
                    else:
                        logging.warning(f"Failed to send message via WebSocket: '{message}'")
                        log_event("WARN: WebSocket send failed. Connection might be down.")
        except WebDriverException:
            logging.warning("Message processor: WebDriver not available. Message dropped.")
        except Exception as e:
            logging.error(f"Unexpected error in message processor: {e}")
            traceback.print_exc()
        time.sleep(MESSAGE_DELAY_SECONDS)

# --- COMMAND PROCESSING (No changes needed here) ---
def process_api_call(command, username, args):
    command_str = f"!{command} {' '.join(args)}"
    try:
        endpoint_url = urljoin(BOT_SERVER_URL, 'command')
        response = requests.post(
            endpoint_url,
            json={"command": command, "username": username, "args": args},
            headers={"Content-Type": "application/json", "x-api-key": API_KEY},
            timeout=15
        )
        response.raise_for_status()
        data = response.json()
        if data.get("reply"):
            queue_reply(data["reply"])
    except requests.exceptions.RequestException as e:
        logging.error(f"API call for '{command_str}' failed: {e}")
        queue_reply(f"@{username} Sorry, the economy server seems to be down.")
    except Exception as e:
        logging.error(f"Unexpected API error processing '{command_str}': {e}")
        traceback.print_exc()

def process_commands_list_call(username):
    try:
        queue_reply(f"@{username} Fetching command list from server...")
        endpoint_url = urljoin(BOT_SERVER_URL, 'commands')
        response = requests.get(endpoint_url, headers={"x-api-key": API_KEY}, timeout=10)
        response.raise_for_status()
        command_list = response.json() 
        queue_reply("--- Available In-Game Commands ---")
        for cmd_string in command_list:
            queue_reply(cmd_string)
        queue_reply("------------------------------------")
    except requests.exceptions.RequestException as e:
        logging.error(f"Failed to fetch command list: {e}")
        queue_reply(f"@{username} Sorry, couldn't fetch the command list. The server might be down.")
    except Exception as e:
        logging.error(f"Unexpected error fetching command list: {e}")
        traceback.print_exc()

# --- BOT MANAGEMENT FUNCTIONS ---
def reset_inactivity_timer():
    global inactivity_timer
    if inactivity_timer: inactivity_timer.cancel()
    inactivity_timer = threading.Timer(INACTIVITY_TIMEOUT_SECONDS, attempt_soft_rejoin)
    inactivity_timer.start()

def attempt_soft_rejoin():
    log_event("Game inactivity detected. Attempting proactive rejoin.")
    BOT_STATE["status"] = "Proactive Rejoin..."
    global driver
    try:
        # ... (This function's logic is fine, no changes needed) ...
    except Exception as e:
        log_event(f"Rejoin FAILED: {e}")
        logging.error(f"Proactive rejoin failed: {e}. Triggering full restart.")
        if driver: driver.quit()

def fetch_command_list():
    global SERVER_COMMAND_LIST
    try:
        # ... (This function's logic is fine, no changes needed) ...
    except Exception as e:
        log_event(f"CRITICAL: Failed to fetch command list: {e}")
        return False

def queue_browser_update():
    """Queues an action to re-inject the JS client with the current command list."""
    def update_action(driver_instance):
        log_event("Injecting/updating JS client (WS Sender + Observer)...")
        driver_instance.execute_script(
            UNIFIED_CLIENT_SCRIPT, ZWSP, SERVER_COMMAND_LIST, USER_COOLDOWN_SECONDS, 
            SPAM_STRIKE_LIMIT, SPAM_TIMEOUT_SECONDS, SPAM_RESET_SECONDS
        )
        queue_reply("Commands have been updated live.")
    action_queue.put(update_action)

# --- MAIN BOT LOGIC ---
def start_bot(use_key_login):
    global driver
    BOT_STATE["status"] = "Launching Browser..."
    log_event("Performing full start...")
    driver = setup_driver()
    
    with driver_lock:
        # ... (This function's logic is mostly fine) ...
        # (Login logic, script injection, and ship ID acquisition remain the same)
        # ...
        pass

    BOT_STATE["status"] = "Running"
    queue_reply("Bot online. Now using WebSocket communication.")
    reset_inactivity_timer()
    logging.info(f"Event-driven chat monitor active. Polling every {MAIN_LOOP_POLLING_INTERVAL_SECONDS}s.")
    
    while True:
        try:
            # ... (Main event loop is fine, no changes needed) ...
            pass
        except WebDriverException as e:
            logging.error(f"WebDriver exception in main loop. Assuming disconnect: {e.msg}")
            raise
        time.sleep(MAIN_LOOP_POLLING_INTERVAL_SECONDS)

# --- NEW FUNCTION TO PREVENT MEMORY LEAKS ---
def cleanup_processes():
    """
    Forcefully finds and terminates any leftover chrome or chromedriver processes.
    This is crucial for preventing memory leaks from zombie processes on restart.
    """
    logging.info("Running cleanup task to find and kill zombie processes...")
    killed_count = 0
    # Define process names to target
    target_processes = ['chrome', 'chromium', 'chromedriver']
    
    # Iterate over all running processes
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            proc_name = proc.info['name'].lower()
            # Check if the process name contains any of our targets
            if any(target in proc_name for target in target_processes):
                logging.warning(f"Found lingering process: {proc.info['name']} (PID: {proc.info['pid']}). Terminating.")
                p = psutil.Process(proc.info['pid'])
                p.terminate()  # Ask it to terminate gracefully
                killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            # Process might have been killed already or we lack permissions
            continue
        except Exception as e:
            logging.error(f"Error during process cleanup for PID {proc.info.get('pid', '?')}: {e}")

    # Give gracefully terminated processes a moment to exit
    if killed_count > 0:
        time.sleep(2)
        # Check again and kill forcefully if they still exist
        for proc in psutil.process_iter(['pid', 'name']):
            try:
                proc_name = proc.info['name'].lower()
                if any(target in proc_name for target in target_processes):
                    logging.error(f"Process {proc.info['name']} (PID: {proc.info['pid']}) did not terminate gracefully. Killing forcefully.")
                    psutil.Process(proc.info['pid']).kill()
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                continue
    
    if killed_count > 0:
        logging.info(f"Cleanup finished. Terminated {killed_count} lingering browser-related processes.")
    else:
        logging.info("Cleanup finished. No lingering processes found.")

# --- MAIN EXECUTION (MODIFIED FOR MEMORY SAFETY) ---
def main():
    threading.Thread(target=run_flask, daemon=True).start()
    threading.Thread(target=message_processor_thread, daemon=True).start()

    use_key_login = True
    restart_count = 0
    last_restart_time = time.time()

    while True:
        current_time = time.time()
        if current_time - last_restart_time < 3600:
            restart_count += 1
        else:
            restart_count = 1
        last_restart_time = current_time

        if restart_count > 10:
            log_event("CRITICAL: Bot is thrashing. Pausing for 5 minutes.")
            logging.critical("BOT RESTARTED >10 TIMES/HOUR. PAUSING FOR 5 MINS.")
            time.sleep(300)
        
        try:
            start_bot(use_key_login)
        except InvalidKeyError as e:
            BOT_STATE["status"] = "Invalid Key!"
            err_msg = f"CRITICAL: {e}. Switching to Guest Mode for next restart."
            log_event(err_msg)
            logging.error(err_msg)
            use_key_login = False
        except Exception as e:
            BOT_STATE["status"] = "Crashed! Restarting..."
            log_event(f"CRITICAL ERROR: {e}")
            logging.critical(f"Full restart. Reason: {e}")
            traceback.print_exc()
        finally:
            global driver
            if inactivity_timer:
                inactivity_timer.cancel()
            if driver:
                try:
                    # Still attempt a graceful quit first
                    driver.quit()
                except Exception as e:
                    logging.warning(f"driver.quit() failed with an error: {e}")
            driver = None
            
            # ** ADD THE FORCEFUL CLEANUP CALL HERE **
            # This will run after every crash or restart, ensuring a clean slate.
            cleanup_processes()
            
            time.sleep(5)

if __name__ == "__main__":
    main()
