import https from "node:https";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { WebSocket } from "ws";

const __dirname = dirname(fileURLToPath(import.meta.url));
const LS_CONFIG = JSON.parse(readFileSync(join(__dirname, "ls_config.json"), "utf8"));
const ALERT_CONFIG = JSON.parse(readFileSync(join(__dirname, "alert_config.json"), "utf8"));

const { botToken, chatId } = ALERT_CONFIG.telegram;

// ============================================================
// Telegram Helper
// ============================================================
function sendTelegram(text) {
    return new Promise((resolve, reject) => {
        const data = JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML" });
        const opts = {
            hostname: "api.telegram.org", port: 443,
            path: `/bot${botToken}/sendMessage`, method: "POST",
            headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) },
        };
        const req = https.request(opts, (res) => {
            let body = "";
            res.on("data", (c) => (body += c));
            res.on("end", () => resolve(res.statusCode === 200));
        });
        req.on("error", reject);
        req.write(data);
        req.end();
    });
}

// ============================================================
// OAuth2 Token
// ============================================================
function getAccessToken(account) {
    return new Promise((resolve, reject) => {
        const body = `grant_type=client_credentials&appkey=${account.appkey}&appsecretkey=${account.appsecret}&scope=oob`;
        const url = new URL(LS_CONFIG.endpoints.tokenUrl);
        const opts = {
            hostname: url.hostname, port: url.port || 8080,
            path: url.pathname, method: "POST",
            headers: { "Content-Type": "application/x-www-form-urlencoded", "Content-Length": Buffer.byteLength(body) },
            timeout: 10000,
        };
        const req = https.request(opts, (res) => {
            let data = "";
            res.on("data", (c) => (data += c));
            res.on("end", () => {
                try {
                    const json = JSON.parse(data);
                    if (json.access_token) resolve(json);
                    else reject(new Error(`Token error: ${data}`));
                } catch { reject(new Error(`Invalid token response: ${data.substring(0, 200)}`)); }
            });
        });
        req.on("timeout", () => { req.destroy(); reject(new Error("Token request timeout")); });
        req.on("error", reject);
        req.write(body);
        req.end();
    });
}

// ============================================================
// WebSocket Client
// ============================================================
class LSRealtimeClient {
    constructor(account, token) {
        this.account = account;
        this.token = token;
        this.ws = null;
        this.reconnectTimer = null;
        this.lastPrices = new Map();
    }

    connect() {
        const wsUrl = LS_CONFIG.endpoints.wsUrl;
        log(`🔌 WebSocket 연결 중: ${wsUrl}`);

        this.ws = new WebSocket(wsUrl);

        this.ws.on("open", () => {
            log("✅ WebSocket 연결 성공");
            this.subscribe();
        });

        this.ws.on("message", (raw) => {
            try {
                const msg = JSON.parse(raw.toString());
                this.handleMessage(msg);
            } catch {
                // Binary or unparseable message
                log(`📨 Raw: ${raw.toString().substring(0, 100)}`);
            }
        });

        this.ws.on("close", (code, reason) => {
            log(`❌ WebSocket 종료 (${code}: ${reason})`);
            this.scheduleReconnect();
        });

        this.ws.on("error", (err) => {
            log(`❌ WebSocket 오류: ${err.message}`);
        });
    }

    subscribe() {
        for (const sub of LS_CONFIG.subscriptions) {
            const req = {
                header: {
                    token: this.token.access_token,
                    tr_type: "3", // 실시간 등록
                },
                body: {
                    tr_cd: sub.tr,
                    tr_key: "",  // 전체 종목
                },
            };
            log(`📡 구독 등록: ${sub.tr} (${sub.desc})`);
            this.ws.send(JSON.stringify(req));
        }
    }

    handleMessage(msg) {
        const header = msg.header || {};
        const body = msg.body || {};
        const trCd = header.tr_cd || "";

        switch (trCd) {
            case "FCD": this.handleFuturesExecution(body); break;
            case "FH0": this.handleFuturesQuote(body); break;
            case "OCD": this.handleOptionsExecution(body); break;
            case "OH0": this.handleOptionsQuote(body); break;
            default:
                if (header.rsp_cd) {
                    const status = header.rsp_cd === "0000" ? "✅" : "⚠️";
                    log(`${status} 응답: [${header.rsp_cd}] ${header.rsp_msg || ""}`);
                }
                break;
        }
    }

    handleFuturesExecution(body) {
        const name = (body.item?.hname || body.item?.shtnIsunm || "선물").trim();
        const price = body.item?.price || body.item?.cvolume || "N/A";
        const change = body.item?.change || body.item?.drate || "0";
        const volume = body.item?.cvolume || body.item?.volume || "0";

        const key = `FCD_${name}`;
        const prev = this.lastPrices.get(key);
        this.lastPrices.set(key, price);

        // Log
        const sign = Number(change) >= 0 ? "+" : "";
        log(`📈 선물체결 | ${name} | ${price} (${sign}${change}) | 거래량 ${volume}`);
    }

    handleFuturesQuote(body) {
        const name = (body.item?.hname || "선물").trim();
        const bidho1 = body.item?.bidho1 || "N/A";
        const offerho1 = body.item?.offerho1 || "N/A";
        log(`📊 선물호가 | ${name} | 매도1 ${offerho1} | 매수1 ${bidho1}`);
    }

    handleOptionsExecution(body) {
        const name = (body.item?.hname || "옵션").trim();
        const price = body.item?.price || "N/A";
        const change = body.item?.change || "0";
        const sign = Number(change) >= 0 ? "+" : "";
        log(`📈 옵션체결 | ${name} | ${price} (${sign}${change})`);
    }

    handleOptionsQuote(body) {
        const name = (body.item?.hname || "옵션").trim();
        log(`📊 옵션호가 | ${name}`);
    }

    scheduleReconnect() {
        if (this.reconnectTimer) return;
        log("🔄 10초 후 재연결 시도...");
        this.reconnectTimer = setTimeout(() => {
            this.reconnectTimer = null;
            this.connect();
        }, 10000);
    }

    disconnect() {
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        if (this.reconnectTimer) {
            clearTimeout(this.reconnectTimer);
            this.reconnectTimer = null;
        }
    }
}

// ============================================================
// Logging
// ============================================================
function log(msg) {
    const now = new Date();
    const ts = now.toLocaleString("ko-KR", { timeZone: "Asia/Seoul", hour12: false });
    console.log(`[${ts}] ${msg}`);
}

// ============================================================
// Main
// ============================================================
const args = process.argv.slice(2);
const command = args[0] || "help";

async function main() {
    switch (command) {
        case "token": {
            log("🔑 접근토큰 발급 테스트...");
            const account = LS_CONFIG.accounts.futures;
            const token = await getAccessToken(account);
            log(`✅ 토큰 발급 성공 (유효: ${token.expires_in}초)`);
            log(`   Token: ${token.access_token.substring(0, 30)}...`);
            break;
        }

        case "start": {
            const accountKey = args[1] || "futures";
            const account = LS_CONFIG.accounts[accountKey];
            if (!account) { console.error(`Unknown account: ${accountKey}`); return; }

            log(`🚀 LS증권 실시간 시작 — ${account.label}`);
            log("🔑 접근토큰 발급 중...");
            const token = await getAccessToken(account);
            log(`✅ 토큰 발급 완료 (유효: ${Math.round(token.expires_in / 3600)}시간)`);

            await sendTelegram(`🟢 <b>LS증권 실시간 연결</b>\n${account.label}\n구독: ${LS_CONFIG.subscriptions.map((s) => s.desc).join(", ")}`);

            const client = new LSRealtimeClient(account, token);
            client.connect();

            // Graceful shutdown
            process.on("SIGINT", () => {
                log("🛑 종료 중...");
                client.disconnect();
                process.exit(0);
            });
            break;
        }

        default:
            console.log("LS증권 실시간 WebSocket 클라이언트");
            console.log("");
            console.log("Commands:");
            console.log("  token                    접근토큰 발급 테스트");
            console.log("  start [futures|stock|overseas]  실시간 연결 시작");
            break;
    }
}

main().catch((err) => {
    console.error("❌ 오류:", err.message);
    process.exit(1);
});
