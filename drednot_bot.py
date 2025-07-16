# drednot_bot.py
# Final version, corrected to inject msgpack library dependency, fixing the send error.

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
ANONYMOUS_LOGIN_KEY = '_M85tFxFxIRDax_nh-HYm1gT'

# Bot Behavior
MESSAGE_DELAY_SECONDS = 0.2
ZWSP = '\u200B'
INACTIVITY_TIMEOUT_SECONDS = 2 * 60
MAIN_LOOP_POLLING_INTERVAL_SECONDS = 0.1
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


# --- NEW: MSGPACK JAVASCRIPT LIBRARY ---
MSGPACK_JS_LIBRARY = """
!function(e,t){"object"==typeof exports&&"undefined"!=typeof module?t(exports):"function"==typeof define&&define.amd?define(["exports"],t):t((e="undefined"!=typeof globalThis?globalThis:e||self).msgpack={})}(this,(function(e){"use strict";const t=new Uint8Array(0);class n{constructor(e,t){this.type=e,this.data=t}}class r{constructor(){this.typeToData=new Map,this.dataToType=new Map}add({type:e,data:t,encode:r,decode:o}){const i=this.typeToData.get(e),s=this.dataToType.get(t);if(i&&s)throw new Error(`The type ${e} is already registered to ${t}, and the data is already registered to ${i}`);if(i)throw new Error(`The type ${e} is already registered to ${i}`);if(s)throw new Error(`The data is already registered to ${s}`);this.typeToData.set(e,t),this.dataToType.set(t,{type:e,encode:r,decode:o})}tryToEncode(e,t){const r=Object.getPrototypeOf(e);if(null==r)return null;const o=this.dataToType.get(r);return o?new n(o.type,o.encode(e,t)):null}}const o=new r;o.add({type:-1,data:Date.prototype,encode:e=>{const n=e.getTime(),r=Math.floor(n/4294967296),o=4294967295&n;if(r>0){const e=new Uint8Array(8);return(new DataView(e.buffer)).setBigUint64(0,BigInt(n),!1),e}if(4294967295&(o|4294967296*r)>>>0!==o)throw new Error("32-bit date-time is not supported yet");{const n=new Uint8Array(4);return(new DataView(n.buffer)).setUint32(0,o,!1),n}},decode(e){const t=new DataView(e.buffer,e.byteOffset,e.byteLength);switch(e.byteLength){case 4:return new Date(1e3*t.getUint32(0,!1));case 8:{const e=t.getBigUint64(0,!1);return new Date(Number(e))}case 12:return new Date(1e3*Number(t.getBigInt64(4,!1))+t.getUint32(0,!1)/1e6);default:throw new Error(`Unrecognized data size for timestamp: ${e.byteLength}`)}}});const i={maxStrLength:4294967295,maxBinLength:4294967295,maxArrayLength:4294967295,maxMapLength:4294967295,maxExtLength:4294967295};class s{constructor(e){this.options=Object.assign({},i,e),this.extensionCodec=this.options.extensionCodec??o,this.context=this.options.context,this.pos=0;const t=this.options.initialBufferSize??2048;this.buffer=new Uint8Array(t),this.view=new DataView(this.buffer.buffer)}getUint8Array(){return this.buffer.subarray(0,this.pos)}ensureBufferSize(e){const t=this.buffer.byteLength;if(t<this.pos+e){const n=Math.max(2*t,this.pos+e),r=new Uint8Array(n);r.set(this.buffer),this.buffer=r,this.view=new DataView(r.buffer)}}pack(e){if(null==e)return this.packNil();if(!1===e)return this.packBoolean(!1);if(!0===e)return this.packBoolean(!0);if("number"==typeof e)return this.packNumber(e);if("bigint"==typeof e)return this.packBigInt(e);if("string"==typeof e)return this.packString(e);if(Array.isArray(e))return this.packArray(e);if(e instanceof Uint8Array)return this.packBinary(e);if("object"==typeof e)return this.packObject(e);throw new Error("Unrecognized object: "+Object.prototype.toString.apply(e))}packNil(){this.ensureBufferSize(1),this.view.setUint8(this.pos++,192)}packBoolean(e){this.ensureBufferSize(1),e?this.view.setUint8(this.pos++,195):this.view.setUint8(this.pos++,194)}packNumber(e){if(Number.isSafeInteger(e)&&!this.options.forceFloat32&&!this.options.forceFloat64&&!this.options.forceIntegerToFloat){if(e>=0)return e<128?this.packInt(e):e<256?this.packU8(e):e<65536?this.packU16(e):this.packU32(e);if(e>=-32)return this.packInt(e);if(e>=-128)return this.packI8(e);if(e>=-32768)return this.packI16(e);if(e>=-2147483648)return this.packI32(e)}this.options.forceFloat32?this.packF32(e):this.packF64(e)}packBigInt(e){if(e>=BigInt(0)){if(e<BigInt(1<<64))return this.packU64(e)}else if(e>=BigInt(-(1<<63)))return this.packI64(e);const t=this.extensionCodec.tryToEncode(e,this.context);if(null!=t)return this.packExtension(t);throw new Error("The value is too large for bigint: "+e)}writeU8(e){this.ensureBufferSize(2),this.view.setUint8(this.pos++,204),this.view.setUint8(this.pos++,e)}writeU16(e){this.ensureBufferSize(3),this.view.setUint8(this.pos++,205),this.view.setUint16(this.pos,e,!1),this.pos+=2}writeU32(e){this.ensureBufferSize(5),this.view.setUint8(this.pos++,206),this.view.setUint32(this.pos,e,!1),this.pos+=4}packU8(e){this.ensureBufferSize(2),this.view.setUint8(this.pos++,204),this.view.setUint8(this.pos++,e)}packU16(e){this.ensureBufferSize(3),this.view.setUint8(this.pos++,205),this.view.setUint16(this.pos,e,!1),this.pos+=2}packU32(e){this.ensureBufferSize(5),this.view.setUint8(this.pos++,206),this.view.setUint32(this.pos,e,!1),this.pos+=4}packU64(e){this.ensureBufferSize(9),this.view.setUint8(this.pos++,207),this.view.setBigUint64(this.pos,e,!1),this.pos+=8}packI8(e){this.ensureBufferSize(2),this.view.setUint8(this.pos++,208),this.view.setInt8(this.pos++,e)}packI16(e){this.ensureBufferSize(3),this.view.setUint8(this.pos++,209),this.view.setInt16(this.pos,e,!1),this.pos+=2}packI32(e){this.ensureBufferSize(5),this.view.setUint8(this.pos++,210),this.view.setInt32(this.pos,e,!1),this.pos+=4}packI64(e){this.ensureBufferSize(9),this.view.setUint8(this.pos++,211),this.view.setBigInt64(this.pos,e,!1),this.pos+=8}packF32(e){this.ensureBufferSize(5),this.view.setUint8(this.pos++,202),this.view.setFloat32(this.pos,e,!1),this.pos+=4}packF64(e){this.ensureBufferSize(5),this.view.setUint8(this.pos++,203),this.view.setFloat64(this.pos,e,!1),this.pos+=4}packInt(e){this.ensureBufferSize(1),this.view.setUint8(this.pos++,e)}packString(e){const t=this.options.maxStrLength;if(e.length>t)throw new Error(`String is too long: ${e.length} > ${t}`);const n=4*e.length;this.ensureBufferSize(5+n);const r=TEXT_ENCODER.encode(e),o=r.length;if(o<32)this.ensureBufferSize(1+o),this.view.setUint8(this.pos++,160|o);else if(o<256){if(this.ensureBufferSize(2+o),this.view.setUint8(this.pos++,217),this.view.setUint8(this.pos++,o),o>t)throw new Error(`String is too long: ${o} > ${t}`)}else if(o<65536){if(this.ensureBufferSize(3+o),this.view.setUint8(this.pos++,218),this.view.setUint16(this.pos,o,!1),this.pos+=2,o>t)throw new Error(`String is too long: ${o} > ${t}`)}else{if(!(o<4294967296))throw new Error("Too long string: "+o+" bytes in UTF-8");if(this.ensureBufferSize(5+o),this.view.setUint8(this.pos++,219),this.view.setUint32(this.pos,o,!1),this.pos+=4,o>t)throw new Error(`String is too long: ${o} > ${t}`)}this.buffer.set(r,this.pos),this.pos+=o}packArray(e){const t=e.length;if(t<16)this.ensureBufferSize(1),this.view.setUint8(this.pos++,144|t);else if(t<65536)this.ensureBufferSize(3),this.view.setUint8(this.pos++,220),this.view.setUint16(this.pos,t,!1),this.pos+=2;else{if(!(t<4294967296))throw new Error("Too large array: "+t);this.ensureBufferSize(5),this.view.setUint8(this.pos++,221),this.view.setUint32(this.pos,t,!1),this.pos+=4}for(const n of e)this.pack(n)}packBinary(e){const t=e.length,n=this.options.maxBinLength;if(t>n)throw new Error(`Binary is too long: ${t} > ${n}`);if(t<256)this.ensureBufferSize(2+t),this.view.setUint8(this.pos++,196),this.view.setUint8(this.pos++,t);else if(t<65536)this.ensureBufferSize(3+t),this.view.setUint8(this.pos++,197),this.view.setUint16(this.pos,t,!1),this.pos+=2;else{if(!(t<4294967296))throw new Error("Too large binary: "+t);this.ensureBufferSize(5+t),this.view.setUint8(this.pos++,198),this.view.setUint32(this.pos,t,!1),this.pos+=4}this.buffer.set(e,this.pos),this.pos+=t}packExtension(e){const t=e.data.length,n=this.options.maxExtLength;if(t>n)throw new Error(`Extension is too long: ${t} > ${n}`);1===t?(this.ensureBufferSize(2+t),this.view.setUint8(this.pos++,212)):2===t?(this.ensureBufferSize(2+t),this.view.setUint8(this.pos++,213)):4===t?(this.ensureBufferSize(2+t),this.view.setUint8(this.pos++,214)):8===t?(this.ensureBufferSize(2+t),this.view.setUint8(this.pos++,215)):16===t?(this.ensureBufferSize(2+t),this.view.setUint8(this.pos++,216)):t<256?(this.ensureBufferSize(3+t),this.view.setUint8(this.pos++,199),this.view.setUint8(this.pos++,t)):t<65536?(this.ensureBufferSize(4+t),this.view.setUint8(this.pos++,200),this.view.setUint16(this.pos,t,!1),this.pos+=2):t<4294967296&&(this.ensureBufferSize(6+t),this.view.setUint8(this.pos++,201),this.view.setUint32(this.pos,t,!1),this.pos+=4),this.view.setInt8(this.pos++,e.type),this.buffer.set(e.data,this.pos),this.pos+=t}packObject(e){const t=this.extensionCodec.tryToEncode(e,this.context);if(null!=t)return this.packExtension(t);const n=Object.keys(e).filter(t=>void 0!==e[t]),r=n.length,o=this.options.maxMapLength;if(r>o)throw new Error(`Map is too large: ${r} > ${o}`);if(this.options.sortKeys){const e=n.map(e=>[TEXT_ENCODER.encode(e),e]);e.sort(([e],[t])=>{for(let n=0;n<e.length;n++)if(n>=t.length)return 1;else{const r=e[n]-t[n];if(0!==r)return r}return e.length-t.length});const t=[];for(const[n,r]of e)t.push(r);return this.packObjectByOrder(e,t)}this.packMapHeader(r);for(const t of n)this.pack(t),this.pack(e[t])}packMapHeader(e){if(e<16)this.ensureBufferSize(1),this.view.setUint8(this.pos++,128|e);else if(e<65536)this.ensureBufferSize(3),this.view.setUint8(this.pos++,222),this.view.setUint16(this.pos,e,!1),this.pos+=2;else{if(!(e<4294967296))throw new Error("Too large map: "+e);this.ensureBufferSize(5),this.view.setUint8(this.pos++,223),this.view.setUint32(this.pos,e,!1),this.pos+=4}}packObjectByOrder(e,t){this.packMapHeader(e.length);for(const n of t)this.pack(n),this.pack(e[n])}}const TEXT_ENCODER=new TextEncoder;class c extends Error{constructor(e){super(e),Object.setPrototypeOf(this,new.target.prototype),this.name=new.target.name}}const a={maxStrLength:4294967295,maxBinLength:4294967295,maxArrayLength:4294967295,maxMapLength:4294967295,maxExtLength:4294967295};class u{constructor(e){this.options=Object.assign({},a,e),this.extensionCodec=this.options.extensionCodec??o,this.context=this.options.context,this.pos=0,this.buffer=t}decode(e){this.setBuffer(e);try{return this.doDecode()}catch(e){if(e instanceof c)throw e;throw new c(e.message)}}doDecode(){const e=this.readHeadByte();return e>=224?e-256:e<=127?e:e>=128&&e<=143?this.decodeMap(e-128):e>=144&&e<=159?this.decodeArray(e-144):e>=160&&e<=191?this.decodeStr(e-160):192===e?null:193===e?this.decodeNeverUsed():194===e?!1:195===e?!0:196===e?this.decodeBin(this.readU8()):197===e?this.decodeBin(this.readU16()):198===e?this.decodeBin(this.readU32()):199===e?this.decodeExt(this.readU8()):200===e?this.decodeExt(this.readU16()):201===e?this.decodeExt(this.readU32()):202===e?this.readF32():203===e?this.readF64():204===e?this.readU8():205===e?this.readU16():206===e?this.readU32():207===e?this.readU64():208===e?this.readI8():209===e?this.readI16():210===e?this.readI32():211===e?this.readI64():212===e?this.decodeExt(1):213===e?this.decodeExt(2):214===e?this.decodeExt(4):215===e?this.decodeExt(8):216===e?this.decodeExt(16):217===e?this.decodeStr(this.readU8()):218===e?this.decodeStr(this.readU16()):219===e?this.decodeStr(this.readU32()):220===e?this.decodeArray(this.readU16()):221===e?this.decodeArray(this.readU32()):222===e?this.decodeMap(this.readU16()):223===e?this.decodeMap(this.readU32()):(()=>{throw new c(`Unrecognized header byte: ${e}`)})()}setBuffer(e){e instanceof ArrayBuffer?this.buffer=new Uint8Array(e):e instanceof Uint8Array?this.buffer=e:(()=>{if(!ArrayBuffer.isView(e))throw new Error("buffer must be an ArrayBuffer or an ArrayBufferView");this.buffer=new Uint8Array(e.buffer,e.byteOffset,e.byteLength)})(),this.view=new DataView(this.buffer.buffer),this.pos=0}readHeadByte(){return this.view.getUint8(this.pos++)}readU8(){const e=this.view.getUint8(this.pos);return this.pos+=1,e}readU16(){const e=this.view.getUint16(this.pos,!1);return this.pos+=2,e}readU32(){const e=this.view.getUint32(this.pos,!1);return this.pos+=4,e}readU64(){const e=this.view.getBigUint64(this.pos,!1);return this.pos+=8,e}readI8(){const e=this.view.getInt8(this.pos);return this.pos+=1,e}readI16(){const e=this.view.getInt16(this.pos,!1);return this.pos+=2,e}readI32(){const e=this.view.getInt32(this.pos,!1);return this.pos+=4,e}readI64(){const e=this.view.getBigInt64(this.pos,!1);return this.pos+=8,e}readF32(){const e=this.view.getFloat32(this.pos,!1);return this.pos+=4,e}readF64(){const e=this.view.getFloat64(this.pos,!1);return this.pos+=8,e}decodeStr(e){const t=this.options.maxStrLength;if(e>t)throw new Error(`String is too long: ${e} > ${t}`);const n=this.pos;this.pos+=e;try{return TEXT_DECODER_RUNTIME.decode(this.buffer.subarray(n,this.pos))}catch(t){if(!(t instanceof TypeError))throw t;const e=new TextDecoder(this.options.string_decoder||"utf-8",{fatal:!1});return e.decode(this.buffer.subarray(n,this.pos))}}decodeBin(e){const t=this.options.maxBinLength;if(e>t)throw new Error(`Binary is too long: ${e} > ${t}`);const n=this.pos,r=this.buffer.subarray(n,n+e);return this.pos+=e,r}decodeArray(e){const t=this.options.maxArrayLength;if(e>t)throw new Error(`Array is too long: ${e} > ${t}`);const n=[];for(let t=0;t<e;t++){const e=this.doDecode();n.push(e)}return n}decodeMap(e){const t=this.options.maxMapLength;if(e>t)throw new Error(`Map is too long: ${e} > ${t}`);const n=Object.create(null);for(let t=0;t<e;t++){const e=this.doDecode();if("string"!=typeof e&&"number"!=typeof e)throw new c("The key of a map must be a string or a number");const r=this.doDecode();n[e]=r}return n}decodeExt(e){const t=this.options.maxExtLength;if(e>t)throw new Error(`Extension is too long: ${e} > ${t}`);const r=this.readI8(),o=this.decodeBin(e);return this.extensionCodec.decode(o,r,this.context)}decodeNeverUsed(){throw new c("Invalid byte code: 0xc1 is reserved")}}{const e="undefined"!=typeof process&&null!=process?.versions?.node;let t;const n="undefined"!=typeof TextDecoder&&!e;t=n?new TextDecoder("utf-8",{fatal:!0}):null;const r=e=>n?t.decode(e):Buffer.from(e).toString("utf-8");var TEXT_DECODER_RUNTIME={decode:r}}e.DecodeError=c,e.Encoder=s,e.ExtensionCodec=r,e.ExtData=n,e.decode=(e,t)=>{const n=new u(t);return n.decode(e)},e.encode=(e,t)=>{const n=new s(t);return n.pack(e),n.getUint8Array()},Object.defineProperty(e,"__esModule",{value:!0})}));
"""

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
            console.error('[Bot-JS] Send failed: msgpack library not found on window object.');
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

# --- COMMAND PROCESSING ---
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
        with driver_lock:
            ship_id = BOT_STATE.get('current_ship_id')
            if not ship_id or ship_id == 'N/A': raise ValueError("Cannot rejoin, no known Ship ID.")
            try:
                driver.find_element(By.CSS_SELECTOR, "#disconnect-popup button").click()
                logging.info("Rejoin: Clicked disconnect pop-up.")
            except:
                try:
                    driver.find_element(By.ID, "exit_button").click()
                    logging.info("Rejoin: Exiting ship normally.")
                except:
                    logging.info("Rejoin: Not in game and no pop-up. Assuming at main menu.")
            wait = WebDriverWait(driver, 15)
            wait.until(EC.presence_of_element_located((By.ID, 'shipyard')))
            logging.info(f"Rejoin: At main menu. Searching for ship: {ship_id}")
            clicked = driver.execute_script("const sid=arguments[0];const s=Array.from(document.querySelectorAll('.sy-id')).find(e=>e.textContent===sid);if(s){s.click();return true}document.querySelector('#shipyard section:nth-of-type(3) .btn-small')?.click();return false", ship_id)
            if not clicked:
                time.sleep(0.5)
                clicked = driver.execute_script("const sid=arguments[0];const s=Array.from(document.querySelectorAll('.sy-id')).find(e=>e.textContent===sid);if(s){s.click();return true}return false", ship_id)
            if not clicked: raise RuntimeError(f"Could not find ship {ship_id} in list.")
            wait.until(EC.presence_of_element_located((By.ID, 'chat-input')))
            logging.info("✅ Proactive rejoin successful!")
            log_event("Proactive rejoin successful.")
            BOT_STATE["status"] = "Running"
            queue_browser_update()
            reset_inactivity_timer()
    except Exception as e:
        log_event(f"Rejoin FAILED: {e}")
        logging.error(f"Proactive rejoin failed: {e}. Triggering full restart.")
        if driver: driver.quit()

def fetch_command_list():
    global SERVER_COMMAND_LIST
    try:
        log_event("Fetching command list from server...")
        endpoint_url = urljoin(BOT_SERVER_URL, 'commands')
        response = requests.get(endpoint_url, headers={"x-api-key": API_KEY}, timeout=10)
        response.raise_for_status()
        full_command_strings = response.json()
        SERVER_COMMAND_LIST = [s.split(' ')[0][1:] for s in full_command_strings]
        SERVER_COMMAND_LIST.append('verify')
        log_event(f"Successfully processed {len(SERVER_COMMAND_LIST)} commands.")
        return True
    except Exception as e:
        log_event(f"CRITICAL: Failed to fetch command list: {e}")
        return False

def queue_browser_update():
    def update_action(driver_instance):
        log_event("Injecting/updating JS client...")
        # Note: We don't need to re-inject msgpack on a simple update
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
        logging.info(f"Navigating to invite link...")
        driver.get(SHIP_INVITE_LINK)
        wait = WebDriverWait(driver, 30)
        
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
            raise

        wait.until(EC.presence_of_element_located((By.ID, "chat-input")))
        
        if not fetch_command_list():
            raise RuntimeError("Initial command fetch failed. Cannot start bot.")

        # === THE FIX: INJECT MSGPACK FIRST, THEN INJECT THE CLIENT SCRIPT ===
        log_event("Injecting required msgpack library...")
        driver.execute_script(MSGPACK_JS_LIBRARY)
        
        log_event("Injecting Unified JS Client (WS + Observer)...")
        driver.execute_script(
            UNIFIED_CLIENT_SCRIPT, ZWSP, SERVER_COMMAND_LIST, USER_COOLDOWN_SECONDS, 
            SPAM_STRIKE_LIMIT, SPAM_TIMEOUT_SECONDS, SPAM_RESET_SECONDS
        )
        
        log_event("Proactively scanning for Ship ID...")
        PROACTIVE_SCAN_SCRIPT = """const chatContent = document.getElementById('chat-content'); if (!chatContent) { return null; } const paragraphs = chatContent.querySelectorAll('p'); for (const p of paragraphs) { const pText = p.textContent || ""; if (pText.includes("Joined ship '")) { const match = pText.match(/{[A-Z\\d]+}/); if (match && match[0]) { return match[0]; } } } return null;"""
        found_id = driver.execute_script(PROACTIVE_SCAN_SCRIPT)
        
        if found_id:
            BOT_STATE["current_ship_id"] = found_id
            log_event(f"Confirmed Ship ID via scan: {found_id}")
        else:
            log_event("No existing ID found. Waiting for live event...")
            start_time = time.time()
            ship_id_found = False
            while time.time() - start_time < 15:
                new_events = driver.execute_script("return window.py_bot_events.splice(0, window.py_bot_events.length);")
                for event in new_events:
                    if event['type'] == 'ship_joined':
                        BOT_STATE["current_ship_id"] = event['id']
                        ship_id_found = True
                        log_event(f"Confirmed Ship ID via event: {BOT_STATE['current_ship_id']}")
                        break
                if ship_id_found: break
                time.sleep(0.5)
            if not ship_id_found:
                error_message = "Failed to get Ship ID via scan or live event."
                log_event(f"CRITICAL: {error_message}")
                raise RuntimeError(error_message)

    BOT_STATE["status"] = "Running"
    queue_reply("Bot online. Now using WebSocket communication.")
    reset_inactivity_timer()
    logging.info(f"Event-driven chat monitor active. Polling every {MAIN_LOOP_POLLING_INTERVAL_SECONDS}s.")
    
    while True:
        try:
            try:
                while not action_queue.empty():
                    action_to_run = action_queue.get_nowait()
                    with driver_lock:
                        if driver:
                            action_to_run(driver) 
            except queue.Empty:
                pass

            with driver_lock:
                if not driver: break
                new_events = driver.execute_script("return window.py_bot_events.splice(0, window.py_bot_events.length);")
            
            if new_events:
                reset_inactivity_timer()
                for event in new_events:
                    if event['type'] == 'ship_joined' and event['id'] != BOT_STATE["current_ship_id"]:
                        BOT_STATE["current_ship_id"] = event['id']
                        log_event(f"Switched to new ship: {BOT_STATE['current_ship_id']}")
                    elif event['type'] == 'command':
                        cmd, user, args = event['command'], event['username'], event['args']
                        command_str = f"!{cmd} {' '.join(args)}"
                        logging.info(f"RECV: '{command_str}' from {user}")
                        BOT_STATE["last_command_info"] = f"{command_str} (from {user})"

                        if cmd == "commands":
                            command_executor.submit(process_commands_list_call, user)
                        else:
                            command_executor.submit(process_api_call, cmd, user, args)
                            
                    elif event['type'] == 'spam_detected':
                        username, command = event['username'], event['command']
                        log_event(f"SPAM: Timed out '{username}' for {SPAM_TIMEOUT_SECONDS}s for spamming '!{command}'.")
        except WebDriverException as e:
            logging.error(f"WebDriver exception in main loop. Assuming disconnect: {e.msg}")
            raise
        time.sleep(MAIN_LOOP_POLLING_INTERVAL_SECONDS)

# --- MEMORY LEAK PREVENTION ---
def cleanup_processes():
    logging.info("Running cleanup task to find and kill zombie processes...")
    killed_count = 0
    target_processes = ['chrome', 'chromium', 'chromedriver']
    
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            proc_name = proc.info['name'].lower()
            if any(target in proc_name for target in target_processes):
                logging.warning(f"Found lingering process: {proc.info['name']} (PID: {proc.info['pid']}). Terminating.")
                p = psutil.Process(proc.info['pid'])
                p.terminate()
                killed_count += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
        except Exception as e:
            logging.error(f"Error during process cleanup for PID {proc.info.get('pid', '?')}: {e}")

    if killed_count > 0:
        time.sleep(2)
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

# --- MAIN EXECUTION ---
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
                    driver.quit()
                except Exception as e:
                    logging.warning(f"driver.quit() failed with an error: {e}")
            driver = None
            
            cleanup_processes()
            
            time.sleep(5)

if __name__ == "__main__":
    main()
