import WebSocket from 'ws'; // WebSocket 모듈 import
import https from 'node:https';
import http from 'node:http';
import { readFileSync } from 'node:fs';
import { join, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = dirname(fileURLToPath(import.meta.url));
const LS_CONFIG = JSON.parse(readFileSync(join(__dirname, "ls_config.json"), "utf8"));

const IS_MOCK = LS_CONFIG.mode === "mock";
const CONFIG_ACCOUNTS = IS_MOCK ? LS_CONFIG.mock_accounts : LS_CONFIG.accounts;

const LOG_PREFIX_F = IS_MOCK ? "[MOCK_FUTURES]" : "[FUTURES]";
const LOG_PREFIX_S = IS_MOCK ? "[MOCK_STOCK]" : "[STOCK]";

// LS증권 WebSocket API 설정
const WS_ENDPOINT = IS_MOCK ? LS_CONFIG.endpoints.wsUrlMock : LS_CONFIG.endpoints.wsUrl;
const TOKEN_ENDPOINT = LS_CONFIG.endpoints.tokenUrl;

// 앱키와 시크릿키는 환경변수와 설정 파일에서 가져옵니다. (Mock 모드일 때는 환경변수를 무시합니다)
const APP_KEY = (IS_MOCK ? null : process.env.LS_SEC_ACCESS_TOKEN) || CONFIG_ACCOUNTS.futures.appkey;
const APP_SECRET = CONFIG_ACCOUNTS.futures.appsecret;

const STOCK_APP_KEY = CONFIG_ACCOUNTS.stock.appkey;
const STOCK_APP_SECRET = CONFIG_ACCOUNTS.stock.appsecret;

// 실시간 시세 캐시 (메모리 DB 역할)
const realtimeCache = {};
let OAUTH_TOKEN = null;
let STOCK_OAUTH_TOKEN = null;

function log(message) {
    console.log(`[LS_WS_ADAPTER] ${new Date().toISOString()}: ${message}`);
}

async function getOAuthToken(appKey, appSecret) {
    return new Promise((resolve, reject) => {
        const body = `grant_type=client_credentials&appkey=${appKey}&appsecretkey=${appSecret}&scope=oob`;
        const url = new URL(TOKEN_ENDPOINT);
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
                const json = JSON.parse(data);
                if (json.access_token) resolve(json.access_token);
                else reject(new Error(`Token error: ${data}`));
            });
        });
        req.on("error", reject);
        req.write(body);
        req.end();
    });
}

async function connectWebSocket() {
    if (!APP_KEY || !STOCK_APP_KEY) {
        log('오류: 접근 가능한 선물/주식 앱키가 없습니다. 연결할 수 없습니다.');
        return;
    }
    log('OAuth2 토큰 발급 시도...');

    try {
        OAUTH_TOKEN = await getOAuthToken(APP_KEY, APP_SECRET);
        STOCK_OAUTH_TOKEN = await getOAuthToken(STOCK_APP_KEY, STOCK_APP_SECRET);
        log('OAuth2 발급 성공! 선물 및 주식 임시 토큰 획득.');
    } catch (e) {
        log(`토큰 발급 실패: ${e.message}`);
        return;
    }

    log('WebSocket 연결 시도...');

    // 로컬 메모리 캐시를 CLI(OpenClaw Tool)에 공유하기 위한 HTTP 마이크로서버 시작
    const CACHE_PORT = 18790;
    http.createServer((req, res) => {
        res.writeHead(200, { 'Content-Type': 'application/json' });
        // /get?symbol=005930 등의 쿼리 처리를 단순화하여 전체 캐시 반환
        res.end(JSON.stringify(realtimeCache));
    }).listen(CACHE_PORT, () => {
        log(`실시간 캐시 공유 HTTP 서버 시작 (Port: ${CACHE_PORT})`);
    });

    // ----------------------------------------------------
    // 1. Futures & Options WebSocket Connection
    // ----------------------------------------------------
    const wsFutures = new WebSocket(WS_ENDPOINT);

    wsFutures.onopen = () => {
        log(`${LOG_PREFIX_F} WebSocket 연결 성공. 실시간 시세 구독 요청 전송.`);

        const kospiFuturesQuoteMsg = {
            header: { token: OAUTH_TOKEN, tr_type: '3' },
            body: { tr_cd: 'FH0', tr_key: '' } // 전체 종목
        };
        wsFutures.send(JSON.stringify(kospiFuturesQuoteMsg));
        log(`${LOG_PREFIX_F} KOSPI 200 선물 호가 실시간 구독 요청 전송(FH0)`);

        const kospiOptionsQuoteMsg = {
            header: { token: OAUTH_TOKEN, tr_type: '3' },
            body: { tr_cd: 'OH0', tr_key: '' } // 전체 종목
        };
        wsFutures.send(JSON.stringify(kospiOptionsQuoteMsg));
        log(`${LOG_PREFIX_F} KOSPI 200 옵션 호가 실시간 구독 요청 전송(OH0)`);
    };

    wsFutures.onmessage = (event) => {
        const message = event.data.toString('utf8');
        try {
            const data = JSON.parse(message);
            const trCd = data.header.tr_cd;
            if (data.header.rsp_cd === '00000') {
                log(`[FUTURES] 구독 정상 승인: TR_CD = ${trCd}`);
                return;
            } else if (data.header.rsp_cd) {
                log(`[FUTURES] 구독 오류: TR_CD = ${trCd}, RSP_CD = ${data.header.rsp_cd}, RSP_MSG = ${data.header.rsp_msg}`);
                return;
            }
            if (trCd === 'FH0' && data.body) {
                const symbol = (data.body.shtnIsunm || "선물").trim();
                if (!realtimeCache[symbol]) realtimeCache[symbol] = {};
                realtimeCache[symbol].bid = data.body.bidho1 || "N/A";
                realtimeCache[symbol].ask = data.body.offerho1 || "N/A";
                realtimeCache[symbol].time = new Date().toISOString();
                realtimeCache[symbol].type = "Futures";
            } else if (trCd === 'OH0' && data.body) {
                const symbol = (data.body.hname || "옵션").trim();
                if (!realtimeCache[symbol]) realtimeCache[symbol] = {};
                realtimeCache[symbol].bid = data.body.bidho1 || "N/A";
                realtimeCache[symbol].ask = data.body.offerho1 || "N/A";
                realtimeCache[symbol].time = new Date().toISOString();
                realtimeCache[symbol].type = "Option";
            }
        } catch (e) {
            log(`[FUTURES] 메시지 파싱 오류: ${e.message}`);
        }
    };

    wsFutures.onerror = (error) => log(`[FUTURES] WebSocket 오류: ${error.message}`);
    wsFutures.onclose = (event) => log(`[FUTURES] WebSocket 연결 종료: 코드 ${event.code}`);

    // ----------------------------------------------------
    // 2. Stock WebSocket Connection
    // ----------------------------------------------------
    const wsStock = new WebSocket(WS_ENDPOINT);

    wsStock.onopen = () => {
        log(`${LOG_PREFIX_S} WebSocket 연결 성공.실시간 시세 구독 요청 전송.`);

        const samsungStockSubscribeMsg = {
            header: { token: STOCK_OAUTH_TOKEN, tr_type: '3' },
            body: { tr_cd: 'K3_', tr_key: '005930' } // KOSPI 체결 (K3_) - 삼성전자
        };
        wsStock.send(JSON.stringify(samsungStockSubscribeMsg));
        log(`${LOG_PREFIX_S} 삼성전자 주식 실시간 체결 구독 요청 전송(K3_)`);
    };

    wsStock.onmessage = (event) => {
        const message = event.data.toString('utf8');
        try {
            const data = JSON.parse(message);
            const trCd = data.header.tr_cd;
            if (data.header.rsp_cd === '00000') {
                log(`[STOCK] 구독 정상 승인: TR_CD = ${trCd}`);
                return;
            } else if (data.header.rsp_cd) {
                log(`[STOCK] 구독 오류: TR_CD = ${trCd}, RSP_CD = ${data.header.rsp_cd}, RSP_MSG = ${data.header.rsp_msg}`);
                return;
            }
            if (trCd === 'K3_' && data.body) {
                const symbol = "삼성전자";
                if (!realtimeCache[symbol]) realtimeCache[symbol] = {};
                realtimeCache[symbol].price = data.body.price || data.body.cheprice || "N/A";
                realtimeCache[symbol].change = data.body.change || data.body.sign || "0";
                realtimeCache[symbol].time = new Date().toISOString();
                realtimeCache[symbol].type = "Stock";
            }
        } catch (e) {
            log(`[STOCK] 메시지 파싱 오류: ${e.message}`);
        }
    };

    wsStock.onerror = (error) => log(`[STOCK] WebSocket 오류: ${error.message}`);
    wsStock.onclose = (event) => log(`[STOCK] WebSocket 연결 종료: 코드 ${event.code}`);
}

// 실시간 캐시에서 특정 종목/지수의 현재가 조회
function getRealtimePrice(symbol) {
    return realtimeCache[symbol];
}

// 모듈 내보내기 (향후 OpenClaw Tool에서 호출할 함수)
export { connectWebSocket, getRealtimePrice };

// ============================================================
// CLI Command Parser (for OpenClaw Tools)
// ============================================================
const rawArgs = process.argv.slice(2);
const command = rawArgs[0];

switch (command) {
    case "connect":
        connectWebSocket();
        break;
    case "get": // 실시간 캐시 공유 데이터 조회 명령 (Tool 모드)
        const symbolToGet = rawArgs[1];
        if (!symbolToGet) {
            console.log("사용법: get <종목코드>");
            process.exit(1);
        }

        // 툴 모드: 백그라운드 구동 중인 데몬의 캐시 서버(Port: 18790)에 HTTP 요청하여 데이터를 받음
        const GET_PORT = 18790;
        http.get(`http://localhost:${GET_PORT}`, (res) => {
            let chunkData = "";
            res.on("data", (c) => chunkData += c);
            res.on("end", () => {
                try {
                    const cacheDB = JSON.parse(chunkData);
                    const priceInfo = cacheDB[symbolToGet];

                    if (priceInfo) {
                        console.log(`[LS_WS_ADAPTER] ${symbolToGet} 실시간 정보:`);
                        console.log(JSON.stringify(priceInfo, null, 2));
                    } else {
                        console.log(`[LS_WS_ADAPTER] '${symbolToGet}' 에 대한 실시간 데이터가 캐시에 없습니다. 시장 휴장 시간이거나 구독 기호가 틀렸을 수 있습니다.`);
                        console.log(`현재 저장된 캐시 목록: ${Object.keys(cacheDB).join(', ')}`);
                    }
                } catch (e) {
                    console.log(`[LS_WS_ADAPTER] 캐시 데이터 파싱 오류: ${e.message}`);
                }
            });
        }).on("error", (e) => {
            console.log(`[LS_WS_ADAPTER] 캐시 서버 통신 오류 (WebSocket 마스터 프로세스가 실행 중인지 확인하세요): ${e.message}`);
        });
        break;
    default:
        console.log("LS증권 WebSocket 어댑터 (테스트용)");
        console.log("Commands:");
        console.log("  connect    LS증권 WebSocket 연결을 시도합니다.");
        console.log("  get <종목코드> 실시간 캐시된 종목 정보를 조회합니다.");
        break;
}
