import https from "node:https";

const APPKEY = "PSxAsiLpF4TXlpwmofCHQtDdTHmxc3CT1LdL";
const APPSECRET = "MVuvYEN2yaUWOAywgVmr578XBOTRFkGW";

function httpsReq(opts, body) {
    return new Promise((resolve, reject) => {
        const req = https.request(opts, (res) => {
            let d = ""; res.on("data", c => d += c);
            res.on("end", () => resolve({ status: res.statusCode, headers: res.headers, body: d }));
        });
        req.on("error", reject);
        req.on("timeout", () => { req.destroy(); reject(new Error("Timeout")); });
        if (body) req.write(body);
        req.end();
    });
}

async function getToken() {
    const body = `grant_type=client_credentials&appkey=${APPKEY}&appsecretkey=${APPSECRET}&scope=oob`;
    const res = await httpsReq({
        hostname: "openapi.ls-sec.co.kr", port: 8080,
        path: "/oauth2/token", method: "POST",
        headers: { "Content-Type": "application/x-www-form-urlencoded", "Content-Length": Buffer.byteLength(body) },
        timeout: 10000,
    }, body);
    return JSON.parse(res.body);
}

async function testEndpoint(token, trCd, path, reqBody) {
    console.log(`\n--- Testing tr_cd=${trCd}, path=${path} ---`);
    const bodyStr = JSON.stringify(reqBody);
    const res = await httpsReq({
        hostname: "openapi.ls-sec.co.kr", port: 8080,
        path, method: "POST",
        headers: {
            "content-type": "application/json; charset=utf-8",
            "authorization": `Bearer ${token}`,
            "tr_cd": trCd,
            "tr_cont": "N",
            "tr_cont_key": "",
            "mac_address": "000000000000",
        },
        timeout: 10000,
    }, bodyStr);
    console.log(`Status: ${res.status}`);
    console.log(`Body: ${res.body.substring(0, 1500)}`);
    return res;
}

async function main() {
    console.log("🔑 Token...");
    const tokenData = await getToken();
    const token = tokenData.access_token;
    console.log("✅ Token OK\n");

    // Test various paths for o3105 (해외선물 현재가)
    const paths = [
        "/overseas-futureoption/market-data",
        "/overseas-futureoption/v1/market-data",
        "/futureoption/market-data",
        "/stock/overseas-futureoption",
    ];

    for (const path of paths) {
        try {
            await testEndpoint(token, "o3105", path, {
                o3105InBlock: { Symbol: "ESH26" }
            });
        } catch (e) {
            console.log(`Error: ${e.message}`);
        }
    }

    // Also try with different body format
    console.log("\n=== Alternative body formats ===");
    try {
        await testEndpoint(token, "o3105", "/overseas-futureoption/market-data", {
            Symbol: "ESH26"
        });
    } catch (e) { console.log(`Error: ${e.message}`); }

    try {
        await testEndpoint(token, "o3105", "/overseas-futureoption/market-data", {
            t3105InBlock: { Symbol: "ESH26" }
        });
    } catch (e) { console.log(`Error: ${e.message}`); }
}

main().catch(e => console.error("Fatal:", e.message));
