import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const CACHE_PORT = 18790;
const SAMSUNG_AVG_PRICE = 217750;
const SAMSUNG_SHARES = 9;
const TARGET_PREMIUM = 1.7;

http.get(`http://localhost:${CACHE_PORT}`, (res) => {
    let chunkData = "";
    res.on("data", (c) => chunkData += c);
    res.on("end", () => {
        try {
            const cacheDB = JSON.parse(chunkData);

            // 1. 삼성전자
            const samsung = cacheDB["삼성전자"];
            let samsungText = "- 데이터 없음";
            if (samsung && samsung.price && samsung.price !== "N/A") {
                const currentPrice = parseFloat(samsung.price);
                const profitLoss = (currentPrice - SAMSUNG_AVG_PRICE) * SAMSUNG_SHARES;
                samsungText = `${currentPrice.toLocaleString()}원 (평균단가: ${SAMSUNG_AVG_PRICE.toLocaleString()}원, 손익: ${profitLoss > 0 ? '+' : ''}${profitLoss.toLocaleString()}원)`;
            }

            // 2. KOSPI 200 선물 (2026년 3월물)
            // 캐시 키에서 '선물'과 '2603'가 들어간 항목을 찾습니다.
            let futuresText = "- 데이터 없음 (휴장 또는 수신 대기 중)";
            let targetFutureKey = Object.keys(cacheDB).find(k => k.includes("2603") && (cacheDB[k].type === "Futures"));
            // 만약 2603이 없으면 임의의 선물을 선택
            if (!targetFutureKey) targetFutureKey = Object.keys(cacheDB).find(k => cacheDB[k].type === "Futures");

            if (targetFutureKey) {
                const f = cacheDB[targetFutureKey];
                futuresText = `[${targetFutureKey}] 매수 1호가: ${f.bid}, 매도 1호가: ${f.ask} (본 포지션 기준단가 매핑 전)`;
            }

            // 3. 위클리 옵션 콜/풋 (프리미엄 1.7 근처 4개 필터링)
            // 캐시에서 'Option' 타입인 것을 찾아서 프리미엄(매도호가 기준)이 1.7에 가장 가까운 풋/콜 2개씩 골라냅니다.
            const optionKeys = Object.keys(cacheDB).filter(k => cacheDB[k].type === "Option");

            const calls = [];
            const puts = [];

            for (const key of optionKeys) {
                const opt = cacheDB[key];
                if (opt.ask && opt.ask !== "N/A" && parseFloat(opt.ask) > 0.0) {
                    const price = parseFloat(opt.ask);
                    const diff = Math.abs(price - TARGET_PREMIUM);
                    // 옵션 이름에 보통 '콜', '풋', 'C', 'P' 가 들어갑니다.
                    if (key.includes("콜") || key.includes(' C ')) calls.push({ key, price, display: opt, diff });
                    if (key.includes("풋") || key.includes(' P ')) puts.push({ key, price, display: opt, diff });
                }
            }

            calls.sort((a, b) => a.diff - b.diff);
            puts.sort((a, b) => a.diff - b.diff);

            const topCalls = calls.slice(0, 2);
            const topPuts = puts.slice(0, 2);

            let optionsText = "";
            if (topCalls.length === 0 && topPuts.length === 0) {
                optionsText = "- 데이터 없음 (휴장 또는 옵션 데이터 수신 대기 중)\n";
            } else {
                optionsText += "  [콜 옵션]\n";
                topCalls.forEach(c => optionsText += `   - ${c.key} (현재 프리미엄 1호가: ${c.price})\n`);
                optionsText += "  [풋 옵션]\n";
                topPuts.forEach(p => optionsText += `   - ${p.key} (현재 프리미엄 1호가: ${p.price})\n`);
            }

            console.log("=========================================");
            console.log("📊 [실시간 포트폴리오 분석 리포트]");
            console.log("=========================================");
            console.log("1. 삼성전자 (9주 보유)");
            console.log(`   현재가 및 손익: ${samsungText}`);
            console.log("");
            console.log("2. KOSPI 200 선물 (2026년 3월물 1개)");
            console.log(`   실시간 시세: ${futuresText}`);
            console.log("");
            console.log(`3. KOSPI 200 위클리 옵션 (목표 프리미엄: ${TARGET_PREMIUM} 부근 진입 후보)`);
            console.log(optionsText);
            console.log("=========================================");

            // 모의매매(Mock) 포트폴리오 상태 출력
            try {
                const mockPath = path.join(__dirname, 'mock_portfolio.json');

                if (fs.existsSync(mockPath)) {
                    const mockDB = JSON.parse(fs.readFileSync(mockPath, 'utf8'));
                    console.log("💰 [모의매매 가상 포트폴리오 계좌]");
                    console.log(`   - 현금 잔고: ${mockDB.cash_balance.toLocaleString()} 원`);

                    const mockOptions = Object.keys(mockDB.options);
                    if (mockOptions.length > 0) {
                        console.log(`   - 보유 옵션 목록:`);
                        mockOptions.forEach(opt => {
                            const p = mockDB.options[opt];
                            console.log(`     * ${opt} (${p.position.toUpperCase()} ${p.qty}개, 진입가: ${p.entry_price})`);
                        });
                    }
                    console.log("=========================================");
                }
            } catch (mockErr) {
                // 모의매매 파일이 없거나 읽을 수 없는 경우 무시 (옵션 기능)
            }

        } catch (e) {
            console.log(`[오류] 캐시 파싱 실패: ${e.message}`);
        }
    });

}).on("error", (e) => {
    console.log(`[오류] 캐시 서버(Port ${CACHE_PORT}) 통신 실패. ls_websocket_adapter 마스터 데몬이 실행 중인지 확인하세요. (${e.message})`);
});
