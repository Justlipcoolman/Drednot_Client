# drednot_bot.py
# Final version with IN-GAME LEADER ELECTION and a "Listening Phase" on startup.
# This prevents a "split-brain" scenario during redeployments.

import os
import queue
import atexit
import logging
import threading
import traceback
import requests
import time
import uuid # For unique instance IDs
from datetime import datetime
from collections import deque
from threading import Lock
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import urljoin 

from flask import Flask, Response
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

# --- BOT BEHAVIOR & LEADER ELECTION ---
INSTANCE_ID = str(uuid.uuid4()) # A unique ID for this specific bot instance
HEARTBEAT_INTERVAL_SECONDS = 10 # How often to send the in-game heartbeat
LEADER_TIMEOUT_SECONDS = 35   # If we don't hear from a bot in this time, assume it's gone
IS_LEADER = False # Global flag to determine if this instance is the active one
active_bots = {}  # Dictionary to track other bots: { "instance_id": last_seen_timestamp }
active_bots_lock = Lock() # Lock for safely modifying the active_bots dictionary
STARTUP_LISTEN_SECONDS = 5 # How long to listen for other bots before the first election.

MESSAGE_DELAY_SECONDS = 0.2
ZWSP = '\u200B'
ROLLCALL_PREFIX = "[ROLLCALL:"
HEARTBEAT_PREFIX = "[HBEAT:"
INACTIVITY_TIMEOUT_SECONDS = 2 * 60
MAIN_LOOP_POLLING_INTERVAL_SECONDS = 0.05
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

# --- JAVASCRIPT INJECTION SCRIPT ---
MUTATION_OBSERVER_SCRIPT = """
    if (window.isDrednotBotObserverActive) { return; }
    window.isDrednotBotObserverActive = true;
    console.log('[Bot-JS] Initializing Observer with In-Game Leader Election...');
    
    window.py_bot_events = [];
    const zwsp = arguments[0];
    const rollcallPrefix = arguments[1];
    const heartbeatPrefix = arguments[2];
    
    const targetNode = document.getElementById('chat-content');
    if (!targetNode) { return; }

    const callback = (mutationList, observer) => {
        for (const mutation of mutationList) {
            if (mutation.type !== 'childList') continue;
            for (const node of mutation.addedNodes) {
                if (node.nodeType !== 1 || node.tagName !== 'P' || node.dataset.botProcessed) continue;
                node.dataset.botProcessed = 'true';
                
                const pText = node.textContent || "";
                
                if (pText.startsWith(zwsp + rollcallPrefix)) {
                    const id = pText.slice((zwsp + rollcallPrefix).length, -1);
                    window.py_bot_events.push({ type: 'rollcall', id: id });
                    continue;
                }
                if (pText.startsWith(zwsp + heartbeatPrefix)) {
                    const id = pText.slice((zwsp + heartbeatPrefix).length, -1);
                    window.py_bot_events.push({ type: 'heartbeat', id: id });
                    continue;
                }
                
                if (pText.startsWith(zwsp)) continue;
                
                const colonIdx = pText.indexOf(':');
                if (colonIdx === -1) continue;
                
                const bdiElement = node.querySelector("bdi");
                if (!bdiElement) continue;
                
                const username = bdiElement.innerText.trim();
                const msgTxt = pText.substring(colonIdx + 1).trim();
                
                if (msgTxt.startsWith('!')) {
                    const parts = msgTxt.slice(1).trim().split(/ +/);
                    const command = parts.shift().toLowerCase();
                    if (command) {
                        window.py_bot_events.push({ type: 'potential_command', command: command, username: username, args: parts });
                    }
                }
            }
        }
    };
    const observer = new MutationObserver(callback);
    observer.observe(targetNode, { childList: true });
    console.log('[Bot-JS] In-Game Leader Election is now active.');
"""


class InvalidKeyError(Exception): pass

# --- GLOBAL STATE & THREADING PRIMITIVES ---
message_queue = queue.Queue(maxsize=100)
driver_lock = Lock()
inactivity_timer = None
driver = None
SERVER_COMMAND_LIST = [] 
BOT_STATE = {"status": "Initializing...", "start_time": datetime.now(), "current_ship_id": "N/A", "last_command_info": "None yet.", "last_message_sent": "None yet.", "event_log": deque(maxlen=20)}
command_executor = ThreadPoolExecutor(max_workers=MAX_WORKER_THREADS, thread_name_prefix='CmdWorker')
atexit.register(lambda: command_executor.shutdown(wait=True))
heartbeat_thread_instance = None 

def log_event(message):
    timestamp = datetime.now().strftime('%H:%M:%S')
    full_message = f"[{timestamp}] {message}"
    BOT_STATE["event_log"].appendleft(full_message)
    logging.info(f"EVENT: {message}")

def setup_driver():
    logging.info("Launching headless browser for Docker environment...")
    chrome_options = Options()
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
    service = Service()
    return webdriver.Chrome(service=service, options=chrome_options)

flask_app = Flask('')
@flask_app.route('/')
def health_check():
    html = f"""
    <!DOCTYPE html><html lang="en"><head><meta charset="UTF-8"><meta http-equiv="refresh" content="10">
    <title>Drednot Bot Status</title><style>body{{font-family:'Courier New',monospace;background-color:#1e1e1e;color:#d4d4d4;padding:20px;}}.container{{max-width:800px;margin:auto;background-color:#252526;border:1px solid #373737;padding:20px;border-radius:8px;}}h1,h2{{color:#4ec9b0;border-bottom:1px solid #4ec9b0;padding-bottom:5px;}}p{{line-height:1.6;}}.status-ok{{color:#73c991;font-weight:bold;}}.status-warn{{color:#dccd85;font-weight:bold;}}.status-err{{color:#f44747;font-weight:bold;}}ul{{list-style-type:none;padding-left:0;}}li{{background-color:#2d2d2d;margin-bottom:8px;padding:10px;border-radius:4px;white-space:pre-wrap;word-break:break-all;}}.label{{color:#9cdcfe;font-weight:bold;}}</style></head>
    <body><div class="container"><h1>Drednot Bot Status</h1>
    <p><span class="label">Status:</span><span class="status-ok">{BOT_STATE['status']}</span></p>
    <p><span class="label">Current Ship ID:</span>{BOT_STATE['current_ship_id']}</p>
    <p><span class="label">Last Command:</span>{BOT_STATE['last_command_info']}</p>
    <p><span class="label">Last Message Sent:</span>{BOT_STATE['last_message_sent']}</p>
    <h2>Recent Events (Log)</h2><ul>{''.join(f'<li>{event}</li>' for event in BOT_STATE['event_log'])}</ul></div></body></html>
    """
    return Response(html, mimetype='text/html')

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
    while True:
        message = message_queue.get()
        try:
            with driver_lock:
                if driver:
                    driver.execute_script(
                        "const msg=arguments[0];const chatBox=document.getElementById('chat');const chatInp=document.getElementById('chat-input');const chatBtn=document.getElementById('chat-send');if(chatBox&&chatBox.classList.contains('closed')){chatBtn.click();}if(chatInp){chatInp.value=msg;}chatBtn.click();",
                        message
                    )
            clean_msg = message[1:]
            logging.info(f"SENT: {clean_msg}")
            BOT_STATE["last_message_sent"] = clean_msg
        except WebDriverException:
            logging.warning("Message processor: WebDriver not available.")
        except Exception as e:
            logging.error(f"Unexpected error in message processor: {e}")
        time.sleep(MESSAGE_DELAY_SECONDS)

# --- LEADER ELECTION & COMMAND PROCESSING ---
def evaluate_leader():
    global IS_LEADER
    with active_bots_lock:
        now = time.time()
        # Prune bots that haven't sent a heartbeat recently
        timed_out_bots = [bot_id for bot_id, last_seen in active_bots.items() if now - last_seen > LEADER_TIMEOUT_SECONDS]
        for bot_id in timed_out_bots:
            if bot_id in active_bots:
                del active_bots[bot_id]
            log_event(f"LEADER: Bot {bot_id[:8]} timed out.")
        
        # Add ourself to the list if not present, updating our timestamp
        active_bots[INSTANCE_ID] = now

        # Sort the list of active bot IDs alphabetically
        sorted_bot_ids = sorted(active_bots.keys())
        
        # The leader is the one that comes first in the sorted list
        new_leader_id = sorted_bot_ids[0] if sorted_bot_ids else None
        
        was_leader = IS_LEADER
        IS_LEADER = (new_leader_id == INSTANCE_ID)
        
        leader_id_short = new_leader_id[:8] if new_leader_id else 'None'

        if IS_LEADER and not was_leader:
            log_event("LEADER: This instance has been promoted to LEADER.")
            BOT_STATE["status"] = "Leader: Running"
        elif not IS_LEADER and was_leader:
            log_event(f"LEADER: This instance was demoted. New leader: {leader_id_short}.")
            BOT_STATE["status"] = f"Standby (Leader: {leader_id_short})"
        
        if not IS_LEADER:
            BOT_STATE["status"] = f"Standby (Leader: {leader_id_short})"

def heartbeat_thread_func():
    while True:
        time.sleep(HEARTBEAT_INTERVAL_SECONDS)
        try:
            queue_reply(f"{HEARTBEAT_PREFIX}{INSTANCE_ID}]")
            evaluate_leader()
        except Exception as e:
            logging.error(f"Error in heartbeat thread: {e}")

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
        response = requests.get(
            endpoint_url,
            headers={"x-api-key": API_KEY},
            timeout=10
        )
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


# --- MAIN BOT LOGIC ---
def start_bot(use_key_login):
    global driver, SERVER_COMMAND_LIST, heartbeat_thread_instance
    BOT_STATE["status"] = "Launching Browser..."
    log_event("Performing full start...")
    driver = setup_driver()
    
    with driver_lock:
        logging.info(f"Navigating to invite link...")
        driver.get(SHIP_INVITE_LINK)
        wait = WebDriverWait(driver, 15)
        
        try:
            btn = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".modal-container .btn-green")))
            driver.execute_script("arguments[0].click();", btn)
            logging.info("Clicked 'Accept' on notice.")
            
            if ANONYMOUS_LOGIN_KEY and use_key_login:
                log_event("Attempting login with hardcoded key.")
                link = wait.until(EC.presence_of_element_located((By.XPATH, "//a[contains(., 'Restore old anonymous key')]")))
                driver.execute_script("arguments[0].click();", link)
                wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, 'div.modal-window input[maxlength="24"]'))).send_keys(ANONYMOUS_LOGIN_KEY)
                submit_btn = wait.until(EC.presence_of_element_located((By.XPATH, "//div[.//h2[text()='Restore Account Key']]//button[contains(@class, 'btn-green')]")))
                driver.execute_script("arguments[0].click();", submit_btn)
                wait.until(EC.invisibility_of_element_located((By.XPATH, "//div[.//h2[text()='Restore Account Key']]")))
                wait.until(EC.any_of(EC.presence_of_element_located((By.ID, "chat-input")), EC.presence_of_element_located((By.XPATH, "//h2[text()='Login Failed']"))))
                if driver.find_elements(By.XPATH, "//h2[text()='Login Failed']"):
                    raise InvalidKeyError("Login Failed! Key may be invalid.")
                log_event("✅ Successfully logged in with key.")
            else:
                log_event("Playing as new guest.")
                play_btn = wait.until(EC.presence_of_element_located((By.XPATH, "//button[contains(., 'Play Anonymously')]")))
                driver.execute_script("arguments[0].click();", play_btn)

        except TimeoutException:
            logging.warning("Login procedure timed out. Assuming already in-game.")
            log_event("Login timeout; assuming in-game.")
        except Exception as e:
            log_event(f"Login failed critically: {e}")
            raise e

        WebDriverWait(driver, 60).until(EC.presence_of_element_located((By.ID, "chat-input")))
        
        try:
            log_event("Fetching command list from server for validation...")
            endpoint_url = urljoin(BOT_SERVER_URL, 'commands')
            response = requests.get(endpoint_url, headers={"x-api-key": API_KEY}, timeout=10)
            response.raise_for_status()
            full_command_strings = response.json()
            SERVER_COMMAND_LIST = [s.split(' ')[0][1:] for s in full_command_strings]
            log_event(f"Successfully fetched {len(SERVER_COMMAND_LIST)} commands.")
        except Exception as e:
            raise RuntimeError(f"FATAL: Failed to fetch command list from server: {e}")

        log_event("Injecting chat observer...")
        driver.execute_script(MUTATION_OBSERVER_SCRIPT, ZWSP, ROLLCALL_PREFIX, HEARTBEAT_PREFIX)
        
        log_event(f"Joining ship. Announcing presence with ROLLCALL...")
        queue_reply(f"{ROLLCALL_PREFIX}{INSTANCE_ID}]")
        
        log_event(f"Entering {STARTUP_LISTEN_SECONDS}s listening phase to discover other bots...")
        BOT_STATE["status"] = "Listening for peers..."
        
        start_time = time.time()
        while time.time() - start_time < STARTUP_LISTEN_SECONDS:
            new_events = driver.execute_script("return window.py_bot_events.splice(0, window.py_bot_events.length);")
            for event in new_events:
                if event['type'] == 'rollcall' or event['type'] == 'heartbeat':
                    with active_bots_lock:
                        active_bots[event['id']] = time.time()
            time.sleep(0.5)
        
        log_event("Listening phase complete. Holding first election.")
        evaluate_leader()

    if heartbeat_thread_instance is None or not heartbeat_thread_instance.is_alive():
        heartbeat_thread_instance = threading.Thread(target=heartbeat_thread_func, daemon=True)
        heartbeat_thread_instance.start()
        log_event("Heartbeat thread started.")
    
    logging.info(f"Instance {INSTANCE_ID[:8]} is active. Leader: {IS_LEADER}. Polling...")
    
    while True:
        try:
            with driver_lock:
                new_events = driver.execute_script("return window.py_bot_events.splice(0, window.py_bot_events.length);")
            
            if new_events:
                for event in new_events:
                    if event['type'] == 'rollcall' or event['type'] == 'heartbeat':
                        with active_bots_lock:
                            active_bots[event['id']] = time.time()
                        evaluate_leader()
                        continue

                    if event['type'] == 'potential_command':
                        if not IS_LEADER:
                            continue

                        cmd, user, args = event['command'], event['username'], event['args']
                        
                        if cmd not in SERVER_COMMAND_LIST:
                            continue

                        command_str = f"!{cmd} {' '.join(args)}"
                        logging.info(f"LEADER RECV: '{command_str}' from {user}")
                        BOT_STATE["last_command_info"] = f"{command_str} (from {user})"
                        
                        if cmd == "commands":
                            command_executor.submit(process_commands_list_call, user)
                        else:
                            command_executor.submit(process_api_call, cmd, user, args)
        except WebDriverException as e:
            logging.error(f"WebDriver exception in main loop. Assuming disconnect: {e.msg}")
            raise
        time.sleep(MAIN_LOOP_POLLING_INTERVAL_SECONDS)

# --- MAIN EXECUTION ---
def main():
    log_event(f"Bot instance starting with ID: {INSTANCE_ID[:8]}")
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
            
            with active_bots_lock:
                active_bots.clear()
            global IS_LEADER
            IS_LEADER = False

            if driver:
                try:
                    driver.quit()
                except:
                    pass
            driver = None
            time.sleep(5)

if __name__ == "__main__":
    main()
