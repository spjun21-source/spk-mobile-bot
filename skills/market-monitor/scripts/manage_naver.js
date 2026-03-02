import { readFileSync, existsSync } from "node:fs";
import { join } from "node:path";
import { homedir } from "node:os";
import https from "node:https";

const CREDS_PATH = join(homedir(), ".openclaw", ".naver-calendar-creds.json");
const CALDAV_HOST = "caldav.calendar.naver.com";
const CALDAV_PORT = 443;
const USER_AGENT = "OpenClaw/1.0";

function loadCreds() {
    if (!existsSync(CREDS_PATH)) {
        console.error("Credentials not found at " + CREDS_PATH);
        process.exit(1);
    }
    return JSON.parse(readFileSync(CREDS_PATH, "utf8"));
}

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

async function getFirstCalendar(creds) {
    const homeUrl = `/caldav/${creds.username}/calendar/`;
    const res = await request("PROPFIND", homeUrl, {
        "Authorization": getAuthHeader(creds),
        "Depth": "1",
        "Content-Type": "application/xml"
    }, `<?xml version="1.0" encoding="utf-8" ?><D:propfind xmlns:D="DAV:" xmlns:C="urn:ietf:params:xml:ns:caldav"><D:prop><D:resourcetype/><D:displayname/></D:prop></D:propfind>`);

    if (res.statusCode === 207) {
        // Regex to find hrefs that are calendars. 
        // We look for <D:href>...</D:href> blocks that are siblings to <caldav:calendar/>
        // Parsing XML with regex is fragile but acceptable here to avoid deps.
        // We iterate through responses.
        const responses = res.body.split("<D:response>");
        let bestCalendar = null;
        for (const resp of responses) {
            if (resp.includes("calendar")) {
                const hrefMatch = resp.match(/<D:href>(.*?)<\/D:href>/);
                const nameMatch = resp.match(/<D:displayname>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?<\/D:displayname>/);
                if (hrefMatch) {
                    const href = hrefMatch[1];
                    const name = nameMatch ? nameMatch[1] : "Unknown";
                    // Exclude the home URL itself if it matches
                    if (href !== homeUrl && href !== homeUrl.slice(0, -1)) {
                        console.log(`Found calendar: ${name} (${href})`);
                        // Prefer "Your Calendar" or "Calendar" (adjust for Korean "내 캘린더")
                        if (!bestCalendar) bestCalendar = href;
                        if (name.includes("내 캘린더") || name.includes("My Calendar")) {
                            bestCalendar = href;
                        }
                    }
                }
            }
        }
        return bestCalendar;
    }
    return null;
}

async function listEvents(creds) {
    const calendarUrl = await getFirstCalendar(creds);
    if (!calendarUrl) {
        console.error("No calendar found.");
        return;
    }

    console.log(`Using calendar: ${calendarUrl}`);

    const now = new Date();
    const startStr = now.toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
    const end = new Date(now.getTime() + 30 * 24 * 60 * 60 * 1000);
    const endStr = end.toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";

    const res = await request("REPORT", calendarUrl, {
        "Authorization": getAuthHeader(creds),
        "Depth": "1",
        "Content-Type": "application/xml; charset=utf-8"
    }, `<?xml version="1.0" encoding="utf-8" ?><caldav:calendar-query xmlns:D="DAV:" xmlns:caldav="urn:ietf:params:xml:ns:caldav"><D:prop><D:getetag/><caldav:calendar-data/></D:prop><caldav:filter><caldav:comp-filter name="VCALENDAR"><caldav:comp-filter name="VEVENT"><caldav:time-range start="${startStr}" end="${endStr}"/></caldav:comp-filter></caldav:comp-filter></caldav:filter></caldav:calendar-query>`);



    if (res.statusCode >= 200 && res.statusCode < 300) {
        const events = [];

        // Naver didn't return calendar-data in REPORT, so we extract HREFs and fetch them individually.
        const hrefRegex = /<D:href>(.*?)<\/D:href>/g;
        let match;
        const hrefs = [];
        while ((match = hrefRegex.exec(res.body)) !== null) {
            const href = match[1];
            // Exclude calendar itself
            if (href !== calendarUrl && href !== calendarUrl.slice(0, -1) && href.endsWith(".ics")) {
                hrefs.push(href);
            }
        }

        console.log(`Found ${hrefs.length} event(s). Fetching details...`);

        for (const href of hrefs) {
            try {
                const eventRes = await request("GET", href, {
                    "Authorization": getAuthHeader(creds)
                });

                if (eventRes.statusCode >= 200 && eventRes.statusCode < 300) {
                    const eventBlock = eventRes.body;
                    const summaryMatch = eventBlock.match(/SUMMARY:(.*)/);
                    const dtStartMatch = eventBlock.match(/DTSTART(?:;.*)?:(.*)/);
                    if (summaryMatch) {
                        events.push({
                            summary: summaryMatch[1].trim(),
                            start: dtStartMatch ? dtStartMatch[1].trim() : "Unknown"
                        });
                    }
                } else {
                    console.error(`Failed to fetch ${href}: ${eventRes.statusCode}`);
                }
            } catch (err) {
                console.error(`Error fetching ${href}: ${err.message}`);
            }
        }

        if (events.length === 0) {
            console.log("No upcoming events found.");
        } else {
            console.log("Upcoming events:");
            events.forEach(e => console.log(`${e.start} - ${e.summary}`));

        }
    } else {
        console.error("Failed to list events. Status:", res.statusCode);
        // console.error("Body:", res.body); // Uncomment for debug
    }
}

async function addEvent(creds, summary, startIso, endIso) {
    const calendarUrl = await getFirstCalendar(creds);
    if (!calendarUrl) {
        console.error("No calendar found.");
        return;
    }

    const now = new Date();
    const dtStamp = now.toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";
    const uid = `${now.getTime()}-${Math.floor(Math.random() * 10000)}@openclaw`;
    const formatTime = (iso) => new Date(iso).toISOString().replace(/[-:]/g, "").split(".")[0] + "Z";

    const vcal = `BEGIN:VCALENDAR
VERSION:2.0
PRODID:-//OpenClaw//NONSGML Naver Calendar Skill//EN
BEGIN:VEVENT
UID:${uid}
DTSTAMP:${dtStamp}
DTSTART:${formatTime(startIso)}
DTEND:${formatTime(endIso)}
SUMMARY:${summary}
END:VEVENT
END:VCALENDAR`;

    const eventUrl = `${calendarUrl}${uid}.ics`;
    console.log(`Adding event to ${eventUrl}...`);

    const res = await request("PUT", eventUrl, {
        "Authorization": getAuthHeader(creds),
        "Content-Type": "text/calendar; charset=utf-8",
        "If-None-Match": "*"
    }, vcal);

    if (res.statusCode >= 200 && res.statusCode < 300) {
        console.log("Event created successfully!");
    } else {
        console.error("Failed to create event. Status:", res.statusCode);
        console.error("Body:", res.body);
    }
}

const args = process.argv.slice(2);
const command = args[0];
const creds = loadCreds();

if (command === "list") listEvents(creds);
else if (command === "add") {
    const summaryIdx = args.indexOf("--summary");
    const startIdx = args.indexOf("--start");
    const endIdx = args.indexOf("--end");
    if (summaryIdx === -1 || startIdx === -1) {
        console.error("Usage: add --summary <text> --start <iso> [--end <iso>]");
        process.exit(1);
    }
    const endIso = endIdx !== -1 ? args[endIdx + 1] : args[startIdx + 1];
    addEvent(creds, args[summaryIdx + 1], args[startIdx + 1], endIso);
} else console.log("Usage: node manage_naver.js <list|add>");
