import https from "node:https";
import { readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = dirname(fileURLToPath(import.meta.url));

// ============================================================
// Configuration
// ============================================================
const CONFIG = JSON.parse(readFileSync(join(__dirname, "alert_config.json"), "utf8"));
const { botToken, chatId } = CONFIG.telegram;
const API_KEY = "b54b56bbc01baee17e4a9a2a5a4011e84e7f20b7929ac65484f6ea69fdeb2526";
const STOCK_ENDPOINT = "/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo";
const FUTURES_ENDPOINT = "/1160100/service/GetDerivativeProductInfoService/getStockFuturesPriceInfo";

// ============================================================
// HTTP Helpers
// ============================================================
function dataGoKrCall(endpoint, params = {}) {
    return new Promise((resolve, reject) => {
        const query = new URLSearchParams({
            serviceKey: API_KEY, resultType: "json", numOfRows: "500", pageNo: "1", ...params,
        }).toString();
        const opts = {
            hostname: "apis.data.go.kr", port: 443, path: `${endpoint}?${query}`,
            method: "GET", headers: { "User-Agent": "MarketAlertDaemon/1.0" }, timeout: 15000,
        };
        const req = https.request(opts, (res) => {
            let data = "";
            res.on("data", (c) => (data += c));
            res.on("end", () => { try { resolve(JSON.parse(data)); } catch { reject(new Error("Invalid JSON")); } });
        });
        req.on("timeout", () => { req.destroy(); reject(new Error("Timeout")); });
        req.on("error", reject);
        req.end();
    });
}

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
// Date Helpers
// ============================================================
function getKST() {
    return new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Seoul" }));
}

function getRecentBusinessDate() {
    const kst = getKST();
    kst.setDate(kst.getDate() - 1);
    const day = kst.getDay();
    if (day === 0) kst.setDate(kst.getDate() - 2);
    if (day === 6) kst.setDate(kst.getDate() - 1);
    const y = kst.getFullYear();
    const m = String(kst.getMonth() + 1).padStart(2, "0");
    const d = String(kst.getDate()).padStart(2, "0");
    return `${y}${m}${d}`;
}

function formatNum(n) { return Number(n).toLocaleString("ko-KR"); }

function isMarketHours() {
    if (!CONFIG.schedule.marketHoursOnly) return true;
    const now = getKST();
    const hhmm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    return hhmm >= CONFIG.schedule.marketOpen && hhmm <= CONFIG.schedule.marketClose;
}

// ============================================================
// Alert Logic
// ============================================================
async function checkMarketAlerts() {
    const date = getRecentBusinessDate();
    log(`📡 시황 조회 중... (${date})`);

    try {
        const res = await dataGoKrCall(STOCK_ENDPOINT, { basDt: date, numOfRows: "3000" });
        const items = res?.response?.body?.items?.item;
        if (!items || items.length === 0) { log("데이터 없음"); return; }

        const parsed = items.map((i) => ({
            name: i.itmsNm, code: i.srtnCd, market: i.mrktCtg,
            close: Number(i.clpr), change: Number(i.vs),
            rate: parseFloat(i.fltRt) || 0,
            volume: Number(i.trqu), value: Number(i.trPrc),
        }));

        const alerts = [];

        // 1. Big movers (±threshold%)
        const threshold = CONFIG.alerts.priceChangeThreshold;
        const bigMovers = parsed.filter((s) => Math.abs(s.rate) >= threshold);
        if (bigMovers.length > 0) {
            const top = bigMovers.sort((a, b) => Math.abs(b.rate) - Math.abs(a.rate)).slice(0, 10);
            let msg = `🚨 <b>등락률 ${threshold}% 이상 종목</b> (${date})\n\n`;
            top.forEach((s) => {
                const icon = s.rate > 0 ? "🔴" : "🔵";
                msg += `${icon} ${s.name} (${s.code})\n`;
                msg += `   ${formatNum(s.close)}원 ${s.rate > 0 ? "+" : ""}${s.rate.toFixed(2)}% 거래량 ${formatNum(s.volume)}\n`;
            });
            alerts.push(msg);
        }

        // 2. Watchlist check
        const watchlist = CONFIG.alerts.watchlist;
        if (watchlist.length > 0) {
            const watchMatches = parsed.filter((s) =>
                watchlist.some((w) => w.code === s.code || s.name.includes(w.name))
            );
            if (watchMatches.length > 0) {
                let msg = `📋 <b>관심종목 현황</b> (${date})\n\n`;
                watchMatches.forEach((s) => {
                    const icon = s.rate > 0 ? "▲" : s.rate < 0 ? "▼" : "─";
                    msg += `${icon} <b>${s.name}</b> ${formatNum(s.close)}원 ${s.rate > 0 ? "+" : ""}${s.rate.toFixed(2)}%\n`;
                    msg += `  거래량 ${formatNum(s.volume)} | 거래대금 ${(s.value / 1e8).toFixed(0)}억\n`;
                });
                alerts.push(msg);
            }
        }

        // Send alerts
        for (const msg of alerts) {
            await sendTelegram(msg);
            log("✅ 알림 전송 완료");
        }

        if (alerts.length === 0) {
            log("특이사항 없음 — 알림 미발송");
        }
    } catch (err) {
        log(`❌ 오류: ${err.message}`);
    }
}

async function sendMorningBriefing() {
    const date = getRecentBusinessDate();
    log("☀️ 장 시작 브리핑 생성 중...");

    try {
        const [stockRes, futuresRes] = await Promise.all([
            dataGoKrCall(STOCK_ENDPOINT, { basDt: date, numOfRows: "500" }),
            dataGoKrCall(FUTURES_ENDPOINT, { basDt: date, numOfRows: "100" }),
        ]);

        const stocks = stockRes?.response?.body?.items?.item || [];
        const futures = futuresRes?.response?.body?.items?.item || [];

        const parsed = stocks.map((i) => ({
            name: i.itmsNm, close: Number(i.clpr),
            rate: parseFloat(i.fltRt) || 0, value: Number(i.trPrc),
        }));

        const topGainers = [...parsed].sort((a, b) => b.rate - a.rate).slice(0, CONFIG.reports.topMoversCount);
        const topLosers = [...parsed].sort((a, b) => a.rate - b.rate).slice(0, CONFIG.reports.topMoversCount);
        const topValue = [...parsed].sort((a, b) => b.value - a.value).slice(0, CONFIG.reports.topMoversCount);

        const activeFutures = futures.filter((f) => Number(f.trqu) > 0)
            .sort((a, b) => Number(b.trqu) - Number(a.trqu)).slice(0, 5);

        let msg = `☀️ <b>장 시작 시황 브리핑</b> (${date})\n\n`;

        msg += `🔺 <b>등락률 상위</b>\n`;
        topGainers.forEach((s) => { msg += `  ${s.name} ${formatNum(s.close)}원 +${s.rate.toFixed(2)}%\n`; });

        msg += `\n🔻 <b>등락률 하위</b>\n`;
        topLosers.forEach((s) => { msg += `  ${s.name} ${formatNum(s.close)}원 ${s.rate.toFixed(2)}%\n`; });

        msg += `\n💰 <b>거래대금 상위</b>\n`;
        topValue.forEach((s) => { msg += `  ${s.name} ${formatNum(s.close)}원 ${(s.value / 1e8).toFixed(0)}억\n`; });

        if (activeFutures.length > 0) {
            msg += `\n📊 <b>주요 선물</b>\n`;
            activeFutures.forEach((f) => {
                msg += `  ${(f.itmsNm || "").trim()} ${formatNum(f.clpr)} (${Number(f.vs) >= 0 ? "+" : ""}${f.vs}) 거래량 ${formatNum(f.trqu)}\n`;
            });
        }

        await sendTelegram(msg);
        log("✅ 브리핑 전송 완료");
    } catch (err) {
        log(`❌ 브리핑 오류: ${err.message}`);
    }
}

async function sendClosingReport() {
    log("🌙 장 마감 보고 전송...");
    await checkMarketAlerts(); // Same data, just relabeled
}

// ============================================================
// Scheduler
// ============================================================
function log(msg) {
    const now = getKST();
    const ts = `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")} ${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;
    console.log(`[${ts}] ${msg}`);
}

async function runScheduledTasks() {
    const now = getKST();
    const hhmm = `${String(now.getHours()).padStart(2, "0")}:${String(now.getMinutes()).padStart(2, "0")}`;

    // Morning briefing
    if (CONFIG.reports.morningBriefing && hhmm === CONFIG.reports.morningTime) {
        await sendMorningBriefing();
    }
    // Closing report
    if (CONFIG.reports.closingReport && hhmm === CONFIG.reports.closingTime) {
        await sendClosingReport();
    }
    // Regular market alerts (during market hours)
    if (isMarketHours()) {
        await checkMarketAlerts();
    }
}

// ============================================================
// Main
// ============================================================
const args = process.argv.slice(2);
const command = args[0];

switch (command) {
    case "test":
        log("🧪 테스트 모드 — 즉시 알림 전송");
        checkMarketAlerts().then(() => log("테스트 완료"));
        break;

    case "briefing":
        log("☀️ 수동 브리핑 전송");
        sendMorningBriefing().then(() => log("완료"));
        break;

    case "start":
        log(`🚀 백그라운드 알림 데몬 시작 (${CONFIG.schedule.intervalMinutes}분 간격)`);
        log(`   장 시간: ${CONFIG.schedule.marketOpen} ~ ${CONFIG.schedule.marketClose}`);
        log(`   알림 기준: 등락률 ±${CONFIG.alerts.priceChangeThreshold}%`);
        log(`   관심종목: ${CONFIG.alerts.watchlist.map((w) => w.name).join(", ")}`);

        // Initial run
        runScheduledTasks();

        // Schedule periodic checks
        setInterval(() => {
            runScheduledTasks();
        }, CONFIG.schedule.intervalMinutes * 60 * 1000);
        break;

    default:
        console.log("Market Alert Daemon");
        console.log("");
        console.log("Commands:");
        console.log("  start                    데몬 시작 (30분 간격 모니터링)");
        console.log("  test                     테스트 알림 즉시 전송");
        console.log("  briefing                 시황 브리핑 즉시 전송");
        break;
}
