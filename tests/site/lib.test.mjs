// Unit tests for the site's pure logic. Run with: node --test tests/site/*.test.mjs
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ALL,
  arcPath,
  describeOutage,
  formatDate,
  groupByDay,
  hashUnit,
  isStale,
  newestBySource,
  pageLocale,
  polar,
  RADAR_DAYS,
  radarBlips,
  radarRadius,
  radarSummary,
  relativeTime,
  safeHttpUrl,
  selectItems,
  sourceFromHash,
  unavailableSources,
} from "../../site/assets/lib.mjs";

const NOW = new Date("2026-09-25T12:00:00Z");
const DAY = 24 * 60 * 60 * 1000;

test("relativeTime speaks in the largest whole unit", () => {
  assert.equal(relativeTime("2026-09-25T11:59:30Z", NOW), "just now");
  assert.equal(relativeTime("2026-09-25T11:48:00Z", NOW), "12 minutes ago");
  assert.equal(relativeTime("2026-09-25T10:31:00Z", NOW), "1 hour ago");
  assert.equal(relativeTime("2026-09-25T09:00:00Z", NOW), "3 hours ago");
  assert.equal(relativeTime("2026-09-24T12:00:00Z", NOW), "yesterday");
  assert.equal(relativeTime("2026-09-20T12:00:00Z", NOW), "5 days ago");
});

test("relativeTime returns an empty string for invalid dates", () => {
  assert.equal(relativeTime("not a date", NOW), "");
});

test("safeHttpUrl only lets http(s) links through", () => {
  assert.equal(safeHttpUrl("https://openai.com/index/x"), "https://openai.com/index/x");
  assert.equal(safeHttpUrl("http://example.com/a b"), "http://example.com/a%20b");
  assert.equal(safeHttpUrl("javascript:alert(1)"), null);
  assert.equal(safeHttpUrl("data:text/html,<script>alert(1)</script>"), null);
  assert.equal(safeHttpUrl("/relative/path"), null);
  assert.equal(safeHttpUrl(undefined), null);
});

const items = [
  ...Array.from({ length: 70 }, (_, i) => ({ source: i % 2 ? "openai" : "aws", title: `item ${i}` })),
];

test("selectItems shows the newest 60 for All", () => {
  const selected = selectItems(items, ALL);
  assert.equal(selected.length, 60);
  assert.equal(selected[0].title, "item 0");
});

test("selectItems shows every item of one source", () => {
  const selected = selectItems(items, "openai");
  assert.equal(selected.length, 35);
  assert.ok(selected.every((item) => item.source === "openai"));
});

test("formatDate renders a short calendar date", () => {
  assert.equal(formatDate("2026-09-23T16:00:00Z", "en-US", "UTC"), "Sep 23, 2026");
  assert.equal(formatDate("garbage", "en-US", "UTC"), "");
});

test("sourceFromHash accepts only known slugs", () => {
  const slugs = ["anthropic", "openai", "aws"];
  assert.equal(sourceFromHash("#aws", slugs), "aws");
  assert.equal(sourceFromHash("#AWS", slugs), "aws");
  assert.equal(sourceFromHash("#unknown", slugs), ALL);
  assert.equal(sourceFromHash("", slugs), ALL);
  assert.equal(sourceFromHash("#%E0%A4%A", slugs), ALL); // malformed escape must not throw
});

test("unavailableSources lists failing sources with their error and last success", () => {
  const sources = [
    { slug: "openai", name: "OpenAI", ok: true, error: null, lastSuccessAt: "2026-09-25T11:00:00Z" },
    { slug: "deepseek", name: "DeepSeek", ok: false, error: "HTTP 403", lastSuccessAt: "2026-09-25T07:00:00Z" },
  ];
  assert.deepEqual(unavailableSources(sources), [
    { slug: "deepseek", name: "DeepSeek", error: "HTTP 403", lastSuccessAt: "2026-09-25T07:00:00Z" },
  ]);
});

test("describeOutage says why a source failed and how old its posts may be", () => {
  assert.equal(
    describeOutage({ name: "DeepSeek", error: "HTTP 403", lastSuccessAt: "2026-09-25T07:00:00Z" }, NOW),
    "DeepSeek: HTTP 403. Last successful check 5 hours ago.",
  );
  assert.equal(
    describeOutage({ name: "AWS", error: "timed out.", lastSuccessAt: null }, NOW),
    "AWS: timed out. No successful check yet.",
  );
  assert.equal(
    describeOutage({ name: "AWS", error: null, lastSuccessAt: "2026-09-24T12:00:00Z" }, NOW),
    "AWS: unknown error. Last successful check yesterday.",
  );
});

test("isStale flags data older than three hours", () => {
  assert.equal(isStale("2026-09-25T09:30:00Z", NOW), false);
  assert.equal(isStale("2026-09-25T08:59:00Z", NOW), true);
  assert.equal(isStale("invalid", NOW), true);
});

test("newestBySource keeps the newest valid date of each source", () => {
  const newest = newestBySource([
    { source: "aws", publishedAt: "2026-09-20T10:00:00Z" },
    { source: "aws", publishedAt: "2026-09-24T10:00:00Z" },
    { source: "openai", publishedAt: "garbage" },
    { source: "openai", publishedAt: "2026-09-01T10:00:00Z" },
  ]);
  assert.deepEqual([...newest], [
    ["aws", "2026-09-24T10:00:00Z"],
    ["openai", "2026-09-01T10:00:00Z"],
  ]);
});

test("groupByDay labels days relative to today, in the reader's time zone", () => {
  const dated = [
    { title: "a", publishedAt: "2026-09-25T09:00:00Z" },
    { title: "b", publishedAt: "2026-09-24T20:00:00Z" },
    { title: "c", publishedAt: "2026-09-23T16:00:00Z" },
    { title: "d", publishedAt: "2026-09-23T08:00:00Z" },
    { title: "e", publishedAt: "2026-09-10T12:00:00Z" },
    { title: "f", publishedAt: "2025-08-21T12:00:00Z" },
    { title: "g", publishedAt: "not a date" },
  ];
  const groups = groupByDay(dated, { now: NOW, locale: "en-US", timeZone: "UTC" });
  assert.deepEqual(
    groups.map(({ key, label, items: grouped }) => [key, label, grouped.map((item) => item.title).join("")]),
    [
      ["2026-09-25", "Today", "a"],
      ["2026-09-24", "Yesterday", "b"],
      ["2026-09-23", "Wednesday, September 23", "cd"],
      ["2026-09-10", "September 10", "e"],
      ["2025-08-21", "August 21, 2025", "f"],
      ["", "Date unknown", "g"],
    ],
  );
});

test("pageLocale keeps the reader's English variant and falls back to en", () => {
  assert.equal(pageLocale(["it-IT", "en-GB", "en-US"]), "en-GB");
  assert.equal(pageLocale(["EN"]), "EN");
  assert.equal(pageLocale(["it-IT", "enx"]), "en");
  assert.equal(pageLocale([]), "en");
  assert.equal(pageLocale(), "en");
});

test("groupByDay uses the calendar day of the given time zone", () => {
  const late = [{ title: "late", publishedAt: "2026-09-24T23:30:00Z" }];
  assert.equal(groupByDay(late, { now: NOW, locale: "en-US", timeZone: "UTC" })[0].label, "Yesterday");
  assert.equal(groupByDay(late, { now: NOW, locale: "en-US", timeZone: "Europe/Rome" })[0].label, "Today");
});

test("groupByDay merges items of the same day even when they are not adjacent", () => {
  const groups = groupByDay(
    [
      { title: "x", publishedAt: "2026-09-25T09:00:00Z" },
      { title: "y", publishedAt: "2026-09-24T09:00:00Z" },
      { title: "z", publishedAt: "2026-09-25T08:00:00Z" },
    ],
    { now: NOW, locale: "en-US", timeZone: "UTC" },
  );
  assert.deepEqual(
    groups.map((group) => group.items.length),
    [2, 1],
  );
});

test("radarRadius puts a day, a week and the whole window on the three rings", () => {
  assert.equal(radarRadius(0), 0.08);
  assert.equal(radarRadius(-5 * DAY), 0.08); // a clock slightly ahead still lands at the centre
  assert.ok(Math.abs(radarRadius(DAY) - 1 / 3) < 1e-9);
  assert.ok(Math.abs(radarRadius(7 * DAY) - 2 / 3) < 1e-9);
  assert.equal(radarRadius(RADAR_DAYS * DAY), 1);
  assert.equal(radarRadius(RADAR_DAYS * DAY + 1), null);
  assert.equal(radarRadius(Number.NaN), null);
});

test("hashUnit is stable and stays in [0, 1)", () => {
  assert.equal(hashUnit("https://openai.com/a"), hashUnit("https://openai.com/a"));
  assert.notEqual(hashUnit("https://openai.com/a"), hashUnit("https://openai.com/b"));
  for (const text of ["", "x", "https://aws.amazon.com/about-aws/whats-new/2026/09/", "é🙂"]) {
    const value = hashUnit(text);
    assert.ok(value >= 0 && value < 1, `${text} -> ${value}`);
  }
});

test("polar measures degrees clockwise from north", () => {
  assert.deepEqual(polar(1, 0), { x: 0, y: -1 });
  assert.deepEqual(polar(1, 90), { x: 1, y: 0 });
  assert.deepEqual(polar(2, 180), { x: 0, y: 2 });
  assert.deepEqual(polar(1, 270), { x: -1, y: 0 });
});

test("radarBlips places each source's recent posts inside its own sector", () => {
  const slugs = ["anthropic", "openai", "aws"];
  const posts = [
    { source: "openai", url: "https://openai.com/1", publishedAt: "2026-09-25T06:00:00Z" },
    { source: "aws", url: "https://aws.amazon.com/1", publishedAt: "2026-09-20T12:00:00Z" },
    { source: "aws", url: "https://aws.amazon.com/old", publishedAt: "2026-07-01T12:00:00Z" },
    { source: "unknown", url: "https://example.com/1", publishedAt: "2026-09-25T06:00:00Z" },
    { source: "anthropic", url: "https://www.anthropic.com/x", publishedAt: "garbage" },
  ];
  const blips = radarBlips(posts, slugs, NOW);
  assert.deepEqual(
    blips.map((blip) => blip.source),
    ["openai", "aws"],
  );
  const [openai, aws] = blips;
  assert.ok(openai.angle > 120 && openai.angle < 240, `openai at ${openai.angle}`);
  assert.ok(aws.angle > 240 && aws.angle < 360, `aws at ${aws.angle}`);
  assert.ok(openai.radius < 1 / 3, "a post from today sits inside the first ring");
  assert.ok(aws.radius > 1 / 3 && aws.radius < 2 / 3, "a post from this week sits in the second band");
  assert.equal(openai.bucket, Math.floor(openai.angle / 30));
  assert.ok(Math.abs(Math.hypot(aws.x, aws.y) - aws.radius) < 0.01);
  assert.deepEqual(radarBlips(posts, slugs, NOW), blips, "same input, same picture");
});

test("arcPath draws clockwise arcs, and splits a full circle in two", () => {
  assert.equal(arcPath(10, 0, 90), "M0 -10A10 10 0 0 1 10 0");
  assert.equal(arcPath(10, 0, 270), "M0 -10A10 10 0 1 1 -10 0");
  assert.equal(arcPath(10, 0, 360), "M0 -10A10 10 0 0 1 0 10M0 10A10 10 0 0 1 0 -10");
});

test("radarSummary counts recent posts per source, including silent ones", () => {
  const sources = [
    { slug: "openai", name: "OpenAI" },
    { slug: "aws", name: "AWS" },
    { slug: "ainewshub", name: "AI News Hub" },
  ];
  const blips = [{ source: "aws" }, { source: "openai" }, { source: "aws" }];
  assert.equal(
    radarSummary(blips, sources),
    `Posts from the last ${RADAR_DAYS} days: 1 from OpenAI, 2 from AWS, none from AI News Hub.`,
  );
});
