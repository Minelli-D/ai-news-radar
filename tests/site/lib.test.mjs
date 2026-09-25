// Unit tests for the site's pure logic. Run with: node --test tests/site/
import assert from "node:assert/strict";
import { test } from "node:test";

import {
  ALL,
  formatDate,
  isStale,
  relativeTime,
  safeHttpUrl,
  selectItems,
  sourceFromHash,
  unavailableSources,
} from "../../site/assets/lib.mjs";

const NOW = new Date("2026-09-25T12:00:00Z");

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

test("unavailableSources lists failing sources with their error", () => {
  const sources = [
    { slug: "openai", name: "OpenAI", ok: true, error: null },
    { slug: "deepseek", name: "DeepSeek", ok: false, error: "HTTP 403" },
  ];
  assert.deepEqual(unavailableSources(sources), [{ name: "DeepSeek", error: "HTTP 403" }]);
});

test("isStale flags data older than three hours", () => {
  assert.equal(isStale("2026-09-25T09:30:00Z", NOW), false);
  assert.equal(isStale("2026-09-25T08:59:00Z", NOW), true);
  assert.equal(isStale("invalid", NOW), true);
});
