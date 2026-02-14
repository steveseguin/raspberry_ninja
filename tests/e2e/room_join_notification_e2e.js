#!/usr/bin/env node
"use strict";

/**
 * End-to-end validation for room join notifications.
 *
 * Flow:
 * 1) Start a local webhook receiver.
 * 2) Start `publish.py` in room monitor mode with --join-webhook.
 * 3) Use Playwright Chromium to join a VDO.Ninja room as data-only publisher.
 * 4) Assert webhook receives a room join payload.
 */

const http = require("node:http");
const path = require("node:path");
const { spawn } = require("node:child_process");
const { chromium } = require("playwright");

function wait(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

async function waitFor(predicate, timeoutMs, intervalMs = 250) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) {
      return true;
    }
    await wait(intervalMs);
  }
  return false;
}

async function startWebhookServer() {
  const events = [];
  const server = http.createServer((req, res) => {
    if (req.method === "POST" && req.url === "/join") {
      let body = "";
      req.on("data", (chunk) => {
        body += chunk.toString("utf8");
      });
      req.on("end", () => {
        try {
          events.push(JSON.parse(body));
        } catch {
          events.push({ _raw: body, _parseError: true });
        }
        res.writeHead(200, { "Content-Type": "application/json" });
        res.end(JSON.stringify({ ok: true }));
      });
      return;
    }

    res.writeHead(404, { "Content-Type": "text/plain" });
    res.end("not found");
  });

  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });

  const addr = server.address();
  if (!addr || typeof addr === "string") {
    throw new Error("Failed to get webhook server address");
  }

  return {
    server,
    events,
    port: addr.port,
    url: `http://127.0.0.1:${addr.port}/join`,
    async stop() {
      await new Promise((resolve) => server.close(resolve));
    },
  };
}

async function run() {
  const repoRoot = path.resolve(__dirname, "..", "..");
  const now = Date.now();
  const room = `rn_e2e_room_${now}`;
  const streamID = `rn_e2e_stream_${now}`;

  const webhook = await startWebhookServer();
  const logs = [];

  const monitorProc = spawn(
    "python3",
    [
      "-u",
      "publish.py",
      "--room",
      room,
      "--room-monitor",
      "--join-webhook",
      webhook.url,
      "--password",
      "false",
    ],
    {
      cwd: repoRoot,
      stdio: ["ignore", "pipe", "pipe"],
    }
  );

  monitorProc.stdout.on("data", (chunk) => {
    const text = chunk.toString("utf8");
    logs.push(text);
    process.stdout.write(`[monitor] ${text}`);
  });
  monitorProc.stderr.on("data", (chunk) => {
    const text = chunk.toString("utf8");
    logs.push(text);
    process.stdout.write(`[monitor-err] ${text}`);
  });

  let browser;
  let context;
  let page;

  try {
    const monitorReady = await waitFor(
      () =>
        logs.some((line) => line.includes("WebSocket ready")) ||
        logs.some((line) => line.includes("WebSocket connection lost")),
      60000
    );

    if (!monitorReady) {
      throw new Error("Monitor did not become ready within 60s");
    }

    if (monitorProc.exitCode !== null) {
      throw new Error(`Monitor exited early with code ${monitorProc.exitCode}`);
    }

    browser = await chromium.launch({ headless: true });
    context = await browser.newContext();
    page = await context.newPage();

    const joinUrl = `https://vdo.ninja/?room=${encodeURIComponent(
      room
    )}&push=${encodeURIComponent(streamID)}&autostart&dataonly&password=false`;
    console.log(`[e2e] Joining room with: ${joinUrl}`);
    await page.goto(joinUrl, { waitUntil: "domcontentloaded", timeout: 90000 });

    const gotEvent = await waitFor(
      () => webhook.events.some((evt) => evt && evt.streamID === streamID),
      90000
    );

    if (!gotEvent) {
      throw new Error(
        `Expected join webhook for streamID=${streamID} not received. Events: ${JSON.stringify(
          webhook.events,
          null,
          2
        )}`
      );
    }

    const event = webhook.events.find((evt) => evt && evt.streamID === streamID);
    if (!event || event.event !== "streamAdded" || event.roomEvent !== "room_join") {
      throw new Error(`Unexpected webhook event payload: ${JSON.stringify(event, null, 2)}`);
    }

    if (event.room !== room) {
      throw new Error(`Unexpected room in payload. got=${event.room}, expected=${room}`);
    }

    console.log("[e2e] PASS: room join webhook received and validated");
  } finally {
    try {
      if (page) {
        await page.close();
      }
    } catch {}
    try {
      if (context) {
        await context.close();
      }
    } catch {}
    try {
      if (browser) {
        await browser.close();
      }
    } catch {}

    try {
      monitorProc.kill("SIGINT");
    } catch {}
    await wait(1200);
    if (monitorProc.exitCode === null) {
      try {
        monitorProc.kill("SIGKILL");
      } catch {}
    }

    await webhook.stop();
  }
}

run()
  .then(() => {
    process.exit(0);
  })
  .catch((err) => {
    console.error("[e2e] FAIL:", err && err.stack ? err.stack : err);
    process.exit(1);
  });

