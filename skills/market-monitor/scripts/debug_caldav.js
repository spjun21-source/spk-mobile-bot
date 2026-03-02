import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import https from "node:https";

const CREDS_PATH = join(homedir(), ".openclaw", ".naver-calendar-creds.json");
const CALDAV_HOST = "caldav.calendar.naver.com";
const CALDAV_PORT = 443;
const USER_AGENT = "OpenClaw/1.0";

function loadCreds() { return JSON.parse(readFileSync(CREDS_PATH, "utf8")); }

function getAuthHeader(creds) {
    const authString = `${creds.username}:${creds.password}`;
    return `Basic ${Buffer.from(authString).toString("base64")}`;
}

function request(method, path, headers, body = null) {
    return new Promise((resolve, reject) => {
        const options = {
            hostname: CALDAV_HOST, port: CALDAV_PORT, path: path, method: method,
            headers: { "User-Agent": USER_AGENT, ...headers }
        };
        const req = https.request(options, (res) => {
            let data = "";
            res.on("data", (chunk) => data += chunk);
            res.on("end", () => resolve({ statusCode: res.statusCode, headers: res.headers, body: data }));
        });
        req.on("error", (e) => reject(e));
        if (body) req.write(body);
        req.end();
    });
}

async function probe() {
    const creds = loadCreds();
    // The home set URL from previous debug output
    const homeUrl = `/caldav/${creds.username}/calendar/`;

    console.log(`Probing ${homeUrl} for children...`);
    const res = await request("PROPFIND", homeUrl, {
        "Authorization": getAuthHeader(creds),
        "Depth": "1",
        "Content-Type": "application/xml"
    }, `<?xml version="1.0" encoding="utf-8" ?><D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav"><D:prop><D:resourcetype/><D:displayname/></D:prop></D:propfind>`);

    console.log(`Status: ${res.statusCode}`);
    console.log("Body:", res.body);
}

probe();
