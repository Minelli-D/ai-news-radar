// Pure helpers for the AI News Radar page (no DOM access, unit-tested with node --test).

export const ALL = "all";
export const HOMEPAGE_LIMIT = 60;
const STALE_AFTER_MS = 3 * 60 * 60 * 1000;

const UNITS = [
  ["year", 365 * 24 * 3600],
  ["month", 30 * 24 * 3600],
  ["week", 7 * 24 * 3600],
  ["day", 24 * 3600],
  ["hour", 3600],
  ["minute", 60],
];
const RELATIVE = new Intl.RelativeTimeFormat("en", { numeric: "auto" });

/** "12 minutes ago", "yesterday", ... ("" for an invalid date). */
export function relativeTime(iso, now = new Date()) {
  const seconds = (new Date(iso).getTime() - now.getTime()) / 1000;
  if (Number.isNaN(seconds)) return "";
  if (Math.abs(seconds) < 60) return "just now";
  for (const [unit, size] of UNITS) {
    if (Math.abs(seconds) >= size) return RELATIVE.format(Math.trunc(seconds / size), unit);
  }
  return "just now";
}

/** The normalized URL if it is an absolute http(s) URL, otherwise null. */
export function safeHttpUrl(value) {
  try {
    const url = new URL(value);
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : null;
  } catch {
    return null;
  }
}

/** "All" shows the newest 60 items; a company filter shows all of that company's items. */
export function selectItems(items, source, limit = HOMEPAGE_LIMIT) {
  return source === ALL ? items.slice(0, limit) : items.filter((item) => item.source === source);
}

/** "Sep 23, 2026" in the reader's locale and time zone ("" for an invalid date). */
export function formatDate(iso, locale = undefined, timeZone = undefined) {
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "";
  return date.toLocaleDateString(locale, { year: "numeric", month: "short", day: "numeric", timeZone });
}

/** Map "#aws" to a known source slug; anything else means "all". */
export function sourceFromHash(hash, slugs) {
  try {
    const slug = decodeURIComponent(String(hash ?? "").replace(/^#/, "")).toLowerCase();
    return slugs.includes(slug) ? slug : ALL;
  } catch {
    return ALL;
  }
}

/** Sources whose last collection failed, for the status line. */
export function unavailableSources(sources) {
  return sources.filter((source) => !source.ok).map(({ name, error }) => ({ name, error }));
}

/** True when news.json has not been refreshed for a while (or its date is unreadable). */
export function isStale(generatedAt, now = new Date()) {
  const age = now.getTime() - new Date(generatedAt).getTime();
  return Number.isNaN(age) || age > STALE_AFTER_MS;
}
