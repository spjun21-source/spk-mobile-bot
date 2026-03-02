import https from "node:https";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));
const ALERT_CONFIG = JSON.parse(readFileSync(join(__dirname, "alert_config.json"), "utf8"));
const { botToken, chatId } = ALERT_CONFIG.telegram;

// ============================================================
// 해외선물 종목 목록
// ============================================================
const FUTURES_SYMBOLS = {
    "ES=F": { name: "S&P 500 E-mini", emoji: "🇺🇸" },
    "NQ=F": { name: "Nasdaq 100 E-mini", emoji: "🇺🇸" },
    "YM=F": { name: "Dow Jones E-mini", emoji: "🇺🇸" },
    "CL=F": { name: "WTI 원유", emoji: "🛢️" },
    "GC=F": { name: "금 (Gold)", emoji: "🥇" },
    "SI=F": { name: "은 (Silver)", emoji: "🥈" },
    "6E=F": { name: "유로/달러", emoji: "💶" },
    "ZB=F": { name: "미국 30년 국채", emoji: "📊" },
};

// ============================================================
// HTTP Helpers
// ============================================================
function yahooGet(url) {
    return new Promise((resolve, reject) => {
        const opts = {
            headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" },
            timeout: 10000,
        };
        https.get(url, opts, (res) => {
            let d = "";
            res.on("data", (c) => (d += c));
            res.on("end", () => {
                try { resolve(JSON.parse(d)); }
                catch { reject(new Error("Invalid JSON: " + d.substring(0, 200))); }
            });
        }).on("error", reject).on("timeout", function () { this.destroy(); reject(new Error("Timeout")); });
    });
}

function sendTelegram(text) {
    return new Promise((resolve, reject) => {
        const data = JSON.stringify({ chat_id: chatId, text, parse_mode: "HTML" });
        const opts = {
            hostname: "api.telegram.org", port: 443,
            path: "/bot" + botToken + "/sendMessage", method: "POST",
            headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(data) },
        };
        const req = https.request(opts, (res) => {
            let b = ""; res.on("data", c => b += c);
            res.on("end", () => resolve(res.statusCode === 200));
        });
        req.on("error", reject);
        req.write(data); req.end();
    });
}

// ============================================================
// Yahoo Finance API
// ============================================================
async function fetchFuturesQuotes(symbols) {
    const symStr = symbols.join(",");
    const url = "https://query1.finance.yahoo.com/v8/finance/chart/" + symbols[0] + "?interval=1d&range=1d";

    // Fetch each symbol individually via chart API
    const results = [];
    for (const sym of symbols) {
        try {
            const chartUrl = "https://query1.finance.yahoo.com/v8/finance/chart/" + encodeURIComponent(sym) + "?interval=1d&range=1d";
            const data = await yahooGet(chartUrl);
            const meta = data.chart?.result?.[0]?.meta;
            if (meta) {
                const price = meta.regularMarketPrice;
                const prevClose = meta.previousClose || meta.chartPreviousClose;
                const change = price - prevClose;
                const changePct = prevClose > 0 ? (change / prevClose) * 100 : 0;
                results.push({
                    symbol: sym,
                    price,
                    prevClose,
                    change,
                    changePct,
                    exchange: meta.exchangeName,
                    currency: meta.currency,
                });
            }
        } catch (err) {
            log("⚠️ " + sym + " 조회 실패: " + err.message);
        }
    }
    return results;
}

// ============================================================
// Commands
// ============================================================
async function cmdReport(sendToTelegram = false) {
    const symbols = Object.keys(FUTURES_SYMBOLS);
    log("🌍 해외선물 시세 조회 중...");

    const quotes = await fetchFuturesQuotes(symbols);
    if (quotes.length === 0) {
        log("데이터 없음");
        return;
    }

    const now = new Date().toLocaleString("ko-KR", { timeZone: "Asia/Seoul", hour12: false });
    let msg = "🌍 <b>해외선물 야간시장 현황</b>\n";
    msg += "📅 " + now + "\n\n";

    for (const q of quotes) {
        const info = FUTURES_SYMBOLS[q.symbol] || { name: q.symbol, emoji: "📊" };
        const sign = q.change >= 0 ? "+" : "";
        const arrow = q.change > 0 ? "▲" : q.change < 0 ? "▼" : "─";

        msg += info.emoji + " <b>" + info.name + "</b>\n";
        msg += "   " + arrow + " " + formatPrice(q.price, q.currency);
        msg += " (" + sign + q.change.toFixed(2) + ", " + sign + q.changePct.toFixed(2) + "%)\n";
    }

    console.log(msg.replace(/<[^>]+>/g, ""));

    if (sendToTelegram) {
        await sendTelegram(msg);
        log("✅ Telegram 전송 완료");
    }
}

async function cmdDaemon() {
    const intervalMin = 5;
    log("🚀 해외선물 야간 모니터링 시작 (" + intervalMin + "분 간격)");
    log("   종목: " + Object.values(FUTURES_SYMBOLS).map(s => s.name).join(", "));

    await cmdReport(true);

    setInterval(async () => {
        try {
            await checkAlerts();
        } catch (err) {
            log("❌ 오류: " + err.message);
        }
    }, intervalMin * 60 * 1000);
}

async function checkAlerts() {
    const symbols = Object.keys(FUTURES_SYMBOLS);
    const quotes = await fetchFuturesQuotes(symbols);

    const bigMovers = quotes.filter(q => Math.abs(q.changePct) >= 1.0);
    if (bigMovers.length > 0) {
        let msg = "🚨 <b>해외선물 등락 알림</b>\n\n";
        for (const q of bigMovers) {
            const info = FUTURES_SYMBOLS[q.symbol] || { name: q.symbol, emoji: "📊" };
            const sign = q.change >= 0 ? "+" : "";
            const icon = q.change > 0 ? "🔴" : "🔵";
            msg += icon + " " + info.name + ": " + formatPrice(q.price, q.currency);
            msg += " (" + sign + q.changePct.toFixed(2) + "%)\n";
        }
        await sendTelegram(msg);
        log("🚨 알림 전송: " + bigMovers.length + "건");
    } else {
        log("📊 특이사항 없음 (등락 1% 미만)");
    }
}

// ============================================================
// Helpers
// ============================================================
function formatPrice(price, currency) {
    if (currency === "KRW") return Number(price).toLocaleString("ko-KR") + "원";
    return Number(price).toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function log(msg) {
    const ts = new Date().toLocaleString("ko-KR", { timeZone: "Asia/Seoul", hour12: false });
    console.log("[" + ts + "] " + msg);
}

// ============================================================
// Main
// ============================================================
const args = process.argv.slice(2);
switch (args[0]) {
    case "report":
        cmdReport(false).then(() => process.exit(0));
        break;
    case "send":
        cmdReport(true).then(() => process.exit(0));
        break;
    case "start":
        cmdDaemon();
        break;
    default:
        console.log("해외선물 야간시장 모니터링 (Yahoo Finance)");
        console.log("");
        console.log("Commands:");
        console.log("  report     현재 시세 콘솔 출력");
        console.log("  send       현재 시세 Telegram 전송");
        console.log("  start      야간 모니터링 데몬 (5분 간격)");
        break;
}
