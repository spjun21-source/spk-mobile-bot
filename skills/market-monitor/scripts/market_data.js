import https from "node:https";

// ============================================================
// data.go.kr API Configuration
// ============================================================
const API_KEY = "b54b56bbc01baee17e4a9a2a5a4011e84e7f20b7929ac65484f6ea69fdeb2526";
const BASE_URL = "apis.data.go.kr";

const ENDPOINTS = {
    stock: "/1160100/service/GetStockSecuritiesInfoService/getStockPriceInfo",
    futures: "/1160100/service/GetDerivativeProductInfoService/getStockFuturesPriceInfo",
    options: "/1160100/service/GetDerivativeProductInfoService/getOptionsPriceInfo",
};

// ============================================================
// HTTP Helper
// ============================================================
function apiCall(endpoint, params = {}) {
    return new Promise((resolve, reject) => {
        const query = new URLSearchParams({
            serviceKey: API_KEY,
            resultType: "json",
            numOfRows: "100",
            pageNo: "1",
            ...params,
        }).toString();

        const path = `${endpoint}?${query}`;
        const options = {
            hostname: BASE_URL,
            port: 443,
            path,
            method: "GET",
            headers: { "User-Agent": "OpenClaw-MarketMonitor/1.0" },
            timeout: 15000,
        };

        const req = https.request(options, (res) => {
            let data = "";
            res.on("data", (chunk) => (data += chunk));
            res.on("end", () => {
                try {
                    const json = JSON.parse(data);
                    resolve(json);
                } catch {
                    reject(new Error(`Invalid JSON response: ${data.substring(0, 200)}`));
                }
            });
        });
        req.on("timeout", () => { req.destroy(); reject(new Error("Request timed out")); });
        req.on("error", reject);
        req.end();
    });
}

// ============================================================
// Date helpers
// ============================================================
function getRecentBusinessDate() {
    const now = new Date();
    // Offset to KST (UTC+9)
    const kst = new Date(now.getTime() + 9 * 60 * 60 * 1000);
    // Data updates T+1 at 1pm KST, so use yesterday
    kst.setDate(kst.getDate() - 1);
    const day = kst.getUTCDay();
    if (day === 0) kst.setDate(kst.getDate() - 2); // Sunday → Friday
    if (day === 6) kst.setDate(kst.getDate() - 1); // Saturday → Friday
    return formatDate(kst);
}

function formatDate(d) {
    const y = d.getUTCFullYear();
    const m = String(d.getUTCMonth() + 1).padStart(2, "0");
    const dd = String(d.getUTCDate()).padStart(2, "0");
    return `${y}${m}${dd}`;
}

function formatNumber(n) {
    return Number(n).toLocaleString("ko-KR");
}

// ============================================================
// Commands
// ============================================================

async function cmdSummary(args) {
    const date = args.date || getRecentBusinessDate();
    const count = parseInt(args.count || "10", 10);

    console.log(`📊 시황 요약 (${date})\n`);

    try {
        // Fetch all stocks for the date (get more rows to find top movers)
        const res = await apiCall(ENDPOINTS.stock, { basDt: date, numOfRows: "500" });
        const items = res?.response?.body?.items?.item;

        if (!items || items.length === 0) {
            console.log("해당 날짜의 데이터가 없습니다. (데이터는 T+1 영업일 오후 1시 이후 업데이트)");
            return;
        }

        const total = res.response.body.totalCount;
        console.log(`전체 종목 수: ${formatNumber(total)}\n`);

        // Parse float rates
        const parsed = items.map((i) => ({
            name: i.itmsNm,
            code: i.srtnCd,
            market: i.mrktCtg,
            close: Number(i.clpr),
            change: Number(i.vs),
            changeRate: parseFloat(i.fltRt) || 0,
            open: Number(i.mkp),
            high: Number(i.hipr),
            low: Number(i.lopr),
            volume: Number(i.trqu),
            value: Number(i.trPrc),
        }));

        // Sort by change rate desc
        const byRate = [...parsed].sort((a, b) => b.changeRate - a.changeRate);
        const byVolume = [...parsed].sort((a, b) => b.volume - a.volume);
        const byValue = [...parsed].sort((a, b) => b.value - a.value);

        console.log(`🔺 등락률 상위 ${count}종목:`);
        console.log("─".repeat(65));
        console.log(`${"종목명".padEnd(16)} ${"시장".padEnd(8)} ${"종가".padStart(10)} ${"등락률".padStart(8)} ${"거래량".padStart(14)}`);
        console.log("─".repeat(65));
        byRate.slice(0, count).forEach((s) => {
            const sign = s.changeRate >= 0 ? "+" : "";
            console.log(
                `${s.name.padEnd(16)} ${s.market.padEnd(8)} ${formatNumber(s.close).padStart(10)} ${(sign + s.changeRate.toFixed(2) + "%").padStart(8)} ${formatNumber(s.volume).padStart(14)}`
            );
        });

        console.log(`\n🔻 등락률 하위 ${count}종목:`);
        console.log("─".repeat(65));
        byRate.slice(-count).reverse().forEach((s) => {
            const sign = s.changeRate >= 0 ? "+" : "";
            console.log(
                `${s.name.padEnd(16)} ${s.market.padEnd(8)} ${formatNumber(s.close).padStart(10)} ${(sign + s.changeRate.toFixed(2) + "%").padStart(8)} ${formatNumber(s.volume).padStart(14)}`
            );
        });

        console.log(`\n📈 거래대금 상위 ${count}종목:`);
        console.log("─".repeat(65));
        byValue.slice(0, count).forEach((s) => {
            const sign = s.changeRate >= 0 ? "+" : "";
            const valBillion = (s.value / 100_000_000).toFixed(1);
            console.log(
                `${s.name.padEnd(16)} ${s.market.padEnd(8)} ${formatNumber(s.close).padStart(10)} ${(sign + s.changeRate.toFixed(2) + "%").padStart(8)} ${(valBillion + "억").padStart(12)}`
            );
        });
    } catch (err) {
        console.error("API 호출 오류:", err.message);
    }
}

async function cmdStock(args) {
    const query = args.query;
    const date = args.date || getRecentBusinessDate();

    if (!query) {
        console.error("Usage: stock --query <종목코드 또는 종목명>");
        process.exit(1);
    }

    console.log(`🔍 종목 검색: "${query}" (${date})\n`);

    try {
        // Fetch a large set and filter locally (individual stock filter not available)
        const res = await apiCall(ENDPOINTS.stock, { basDt: date, numOfRows: "3000" });
        const items = res?.response?.body?.items?.item;

        if (!items || items.length === 0) {
            console.log("해당 날짜의 데이터가 없습니다.");
            return;
        }

        // Filter by code or name
        const matches = items.filter(
            (i) => i.srtnCd === query || i.isinCd === query || i.itmsNm.includes(query)
        );

        if (matches.length === 0) {
            console.log(`"${query}"에 해당하는 종목을 찾지 못했습니다.`);
            console.log("힌트: 종목코드(예: 005930) 또는 종목명 키워드(예: 삼성)를 입력하세요.");
            return;
        }

        matches.forEach((s) => {
            const sign = parseFloat(s.fltRt) >= 0 ? "▲" : "▼";
            console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
            console.log(`📌 ${s.itmsNm} (${s.srtnCd})`);
            console.log(`   시장: ${s.mrktCtg}`);
            console.log(`   종가: ${formatNumber(s.clpr)}원 ${sign} ${s.vs} (${s.fltRt}%)`);
            console.log(`   시가: ${formatNumber(s.mkp)}  고가: ${formatNumber(s.hipr)}  저가: ${formatNumber(s.lopr)}`);
            console.log(`   거래량: ${formatNumber(s.trqu)}  거래대금: ${formatNumber(s.trPrc)}원`);
            console.log(`   상장주식수: ${formatNumber(s.lstgStCnt)}  시가총액: ${formatNumber(s.mrktTotAmt)}원`);
        });
        console.log(`━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━`);
        console.log(`검색 결과: ${matches.length}건`);
    } catch (err) {
        console.error("API 호출 오류:", err.message);
    }
}

async function cmdFutures(args) {
    const date = args.date || getRecentBusinessDate();
    const query = args.query || "";

    console.log(`📊 선물 시세 (${date})${query ? ` — 검색: "${query}"` : ""}\n`);

    try {
        const res = await apiCall(ENDPOINTS.futures, { basDt: date, numOfRows: "200" });
        const items = res?.response?.body?.items?.item;

        if (!items || items.length === 0) {
            console.log("해당 날짜의 선물 데이터가 없습니다.");
            return;
        }

        let filtered = items;
        if (query) {
            filtered = items.filter(
                (i) => i.itmsNm?.includes(query) || i.prdCtg?.includes(query) || i.srtnCd?.includes(query)
            );
        }

        // Only show items with trading activity
        const active = filtered.filter((i) => Number(i.trqu) > 0);
        const display = active.length > 0 ? active : filtered.slice(0, 20);

        console.log(`${"종목명".padEnd(30)} ${"종가".padStart(10)} ${"전일대비".padStart(8)} ${"거래량".padStart(12)} ${"미결제".padStart(10)}`);
        console.log("─".repeat(75));

        display.forEach((f) => {
            const sign = Number(f.vs) >= 0 ? "+" : "";
            console.log(
                `${(f.itmsNm || "").trim().padEnd(30)} ${formatNumber(f.clpr).padStart(10)} ${(sign + f.vs).padStart(8)} ${formatNumber(f.trqu).padStart(12)} ${formatNumber(f.opnint).padStart(10)}`
            );
        });

        console.log(`\n총 ${filtered.length}건 (활성거래 ${active.length}건)`);
    } catch (err) {
        console.error("API 호출 오류:", err.message);
    }
}

async function cmdOptions(args) {
    const date = args.date || getRecentBusinessDate();
    const query = args.query || "";

    console.log(`📊 옵션 시세 (${date})${query ? ` — 검색: "${query}"` : ""}\n`);

    try {
        const res = await apiCall(ENDPOINTS.options, { basDt: date, numOfRows: "200" });
        const items = res?.response?.body?.items?.item;

        if (!items || items.length === 0) {
            console.log("해당 날짜의 옵션 데이터가 없습니다.");
            return;
        }

        let filtered = items;
        if (query) {
            filtered = items.filter(
                (i) => i.itmsNm?.includes(query) || i.prdCtg?.includes(query) || i.srtnCd?.includes(query)
            );
        }

        const active = filtered.filter((i) => Number(i.trqu) > 0);
        const display = active.length > 0 ? active : filtered.slice(0, 20);

        console.log(`${"종목명".padEnd(35)} ${"종가".padStart(10)} ${"전일대비".padStart(8)} ${"거래량".padStart(12)}`);
        console.log("─".repeat(70));

        display.forEach((o) => {
            const sign = Number(o.vs) >= 0 ? "+" : "";
            console.log(
                `${(o.itmsNm || "").trim().padEnd(35)} ${formatNumber(o.clpr).padStart(10)} ${(sign + o.vs).padStart(8)} ${formatNumber(o.trqu).padStart(12)}`
            );
        });

        console.log(`\n총 ${filtered.length}건 (활성거래 ${active.length}건)`);
    } catch (err) {
        console.error("API 호출 오류:", err.message);
    }
}

// ============================================================
// CLI Parser
// ============================================================
function parseArgs(argv) {
    const args = {};
    for (let i = 0; i < argv.length; i++) {
        if (argv[i].startsWith("--")) {
            const key = argv[i].slice(2);
            args[key] = argv[i + 1] || "";
            i++;
        }
    }
    return args;
}

const rawArgs = process.argv.slice(2);
const command = rawArgs[0];
const args = parseArgs(rawArgs.slice(1));

switch (command) {
    case "summary":
        cmdSummary(args);
        break;
    case "stock":
        cmdStock(args);
        break;
    case "futures":
        cmdFutures(args);
        break;
    case "options":
        cmdOptions(args);
        break;
    default:
        console.log("한국 증시 시황 모니터 (data.go.kr)");
        console.log("");
        console.log("Commands:");
        console.log("  summary [--date YYYYMMDD] [--count N]     시황 요약 (등락률/거래대금 상위)");
        console.log("  stock --query <코드|종목명> [--date YYYYMMDD]  종목 시세 조회");
        console.log("  futures [--date YYYYMMDD] [--query 키워드]    선물 시세 조회");
        console.log("  options [--date YYYYMMDD] [--query 키워드]    옵션 시세 조회");
        break;
}
