import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const PORTFOLIO_DB_PATH = path.join(__dirname, 'mock_portfolio.json');

// 기본 포트폴리오 (모의매매 DB가 없을 경우 생성)
const DEFAULT_PORTFOLIO = {
    cash_balance: 100000000, // 1억 원
    stock: {
        "삼성전자": { symbol: "005930", qty: 9, avg_price: 217750 }
    },
    futures: {
        "KOSPI200_2603": { symbol: "2603", qty: 1, position: "buy", entry_price: 350.0 }
    },
    options: {}
};

function getPortfolio() {
    if (!fs.existsSync(PORTFOLIO_DB_PATH)) {
        fs.writeFileSync(PORTFOLIO_DB_PATH, JSON.stringify(DEFAULT_PORTFOLIO, null, 2));
    }
    return JSON.parse(fs.readFileSync(PORTFOLIO_DB_PATH, 'utf8'));
}

function savePortfolio(data) {
    fs.writeFileSync(PORTFOLIO_DB_PATH, JSON.stringify(data, null, 2));
}

function executeMockTrade(type, action, symbol, qty, price) {
    const portfolio = getPortfolio();

    console.log(`\n=========================================`);
    console.log(`[MOCK ORDER EXECUTION] 모의매매 주문 접수`);
    console.log(`=========================================`);
    console.log(`종류: ${type.toUpperCase()}`);
    console.log(`종목: ${symbol}`);
    console.log(`주문: ${action.toUpperCase()}`);
    console.log(`수량: ${qty}`);
    console.log(`단가: ${price}`);
    console.log(`-----------------------------------------`);

    let totalValue = qty * price;
    if (type === 'stock') {
        // 주식: 가격 * 수량
        if (action === 'buy') {
            portfolio.cash_balance -= totalValue;
            if (!portfolio.stock[symbol]) portfolio.stock[symbol] = { symbol, qty: 0, avg_price: 0 };
            const prev = portfolio.stock[symbol];
            const newTotalQty = prev.qty + qty;
            const newAvgPrice = ((prev.qty * prev.avg_price) + totalValue) / newTotalQty;
            portfolio.stock[symbol].qty = newTotalQty;
            portfolio.stock[symbol].avg_price = newAvgPrice;
        } else if (action === 'sell') {
            portfolio.cash_balance += totalValue;
            if (portfolio.stock[symbol]) {
                portfolio.stock[symbol].qty = Math.max(0, portfolio.stock[symbol].qty - qty);
            }
        }
    } else if (type === 'option') {
        // 옵션: 프리미엄 반영 (KOSPI 200 승수 25만원 가정)
        const multiplier = 250000;
        const optionValue = totalValue * multiplier;
        if (action === 'buy') {
            portfolio.cash_balance -= optionValue;
            if (!portfolio.options[symbol]) portfolio.options[symbol] = { symbol, qty: 0, entry_price: 0, position: 'buy' };
            portfolio.options[symbol].qty += qty;
            portfolio.options[symbol].entry_price = price;
        } else if (action === 'sell') {
            portfolio.cash_balance += optionValue; // 매도 시 프리미엄 수취
            if (!portfolio.options[symbol]) portfolio.options[symbol] = { symbol, qty: 0, entry_price: 0, position: 'sell' };
            portfolio.options[symbol].qty += qty;
            portfolio.options[symbol].entry_price = price;
        }
    }

    savePortfolio(portfolio);
    console.log(`✅ [성공] 모의매매 체결 및 가상 포트폴리오 업데이트 완료.`);
    console.log(`현재 현금 잔고: ${portfolio.cash_balance.toLocaleString()} 원`);
    console.log(`=========================================\n`);
}

// CLI 파싱
const args = process.argv.slice(2);
if (args.length < 5) {
    console.log("Usage: node mock_trade_executor.js <type: stock|option> <action: buy|sell> <symbol> <qty> <price>");
    process.exit(1);
}

const type = args[0];
const action = args[1];
const symbol = args[2];
const qty = parseInt(args[3]);
const price = parseFloat(args[4]);

executeMockTrade(type, action, symbol, qty, price);
