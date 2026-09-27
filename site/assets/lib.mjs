// Pure helpers for the AI News Radar page (no DOM access, unit-tested with node --test).

export const ALL = "all";
export const HOMEPAGE_LIMIT = 60;
const STALE_AFTER_MS = 3 * 60 * 60 * 1000;
const DAY_MS = 24 * 60 * 60 * 1000;

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

/** Sources whose last collection failed, for the status notice. */
export function unavailableSources(sources) {
  return sources
    .filter((source) => !source.ok)
    .map(({ slug, name, error, lastSuccessAt }) => ({ slug, name, error, lastSuccessAt }));
}

/** One line of the status notice: why a source failed and how old its posts may be. */
export function describeOutage({ name, error, lastSuccessAt }, now = new Date()) {
  const reason = String(error || "unknown error").replace(/[.\s]+$/, "");
  const last = lastSuccessAt ? relativeTime(lastSuccessAt, now) : "";
  return `${name}: ${reason}. ${last ? `Last successful check ${last}.` : "No successful check yet."}`;
}

/** True when news.json has not been refreshed for a while (or its date is unreadable). */
export function isStale(generatedAt, now = new Date()) {
  const age = now.getTime() - new Date(generatedAt).getTime();
  return Number.isNaN(age) || age > STALE_AFTER_MS;
}

/** The newest publishedAt per source, as ISO strings (sources without items are absent). */
export function newestBySource(items) {
  const newest = new Map();
  for (const { source, publishedAt } of items) {
    const time = new Date(publishedAt).getTime();
    if (Number.isNaN(time)) continue;
    const seen = newest.get(source);
    if (!seen || time > new Date(seen).getTime()) newest.set(source, publishedAt);
  }
  return newest;
}

// --- Day groups -------------------------------------------------------------------------------

/** The reader's first English locale ("en-GB", ...), else "en": the page itself is in English. */
export function pageLocale(languages = []) {
  return languages.find((tag) => /^en(-|$)/i.test(String(tag))) ?? "en";
}

function calendarDays(timeZone) {
  const format = new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
  /** "2026-09-23": the calendar day of an instant in the time zone ("" if invalid). */
  return (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "";
    const part = Object.fromEntries(format.formatToParts(date).map(({ type, value: v }) => [type, v]));
    return `${part.year}-${part.month}-${part.day}`;
  };
}

const keyToUtcNoon = (key) => {
  const [year, month, day] = key.split("-").map(Number);
  return new Date(Date.UTC(year, month - 1, day, 12));
};

function dayLabel(key, todayKey, locale) {
  if (!key) return "Date unknown";
  const date = keyToUtcNoon(key);
  const daysAgo = Math.round((keyToUtcNoon(todayKey) - date) / DAY_MS);
  if (daysAgo === 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  const options = { month: "long", day: "numeric", timeZone: "UTC" };
  if (daysAgo > 1 && daysAgo < 7) options.weekday = "long";
  if (key.slice(0, 4) !== todayKey.slice(0, 4)) options.year = "numeric";
  return date.toLocaleDateString(locale, options);
}

/**
 * Items grouped by the reader's calendar day, in the order they arrive:
 * [{ key: "2026-09-23", label: "Wednesday, September 23", items: [...] }, ...].
 * Labels read "Today", "Yesterday", a weekday within the last week, then a date.
 */
export function groupByDay(items, { now = new Date(), locale = undefined, timeZone = undefined } = {}) {
  const dayOf = calendarDays(timeZone);
  const todayKey = dayOf(now);
  const groups = new Map();
  for (const item of items) {
    const key = dayOf(item.publishedAt);
    if (!groups.has(key)) groups.set(key, { key, label: dayLabel(key, todayKey, locale), items: [] });
    groups.get(key).items.push(item);
  }
  return [...groups.values()];
}

// --- Radar ------------------------------------------------------------------------------------

export const RADAR_DAYS = 30;
// Rings sit at a third, two thirds and the full radius: one day, one week, RADAR_DAYS.
const RADAR_BANDS = [
  [0, 1, 0.08, 1 / 3],
  [1, 7, 1 / 3, 2 / 3],
  [7, RADAR_DAYS, 2 / 3, 1],
];
const SECTOR_PADDING = 0.12; // share of each source's sector left empty on both sides

/** Distance from the centre (0..1) for a post of this age, or null when too old or invalid. */
export function radarRadius(ageMs) {
  const days = Math.max(0, ageMs) / DAY_MS;
  for (const [from, to, inner, outer] of RADAR_BANDS) {
    if (days <= to) return inner + ((days - from) / (to - from)) * (outer - inner);
  }
  return null;
}

/** A stable number in [0, 1) for a string (FNV-1a), so a post keeps its place between visits. */
export function hashUnit(text) {
  let hash = 0x811c9dc5;
  for (const char of String(text)) {
    hash ^= char.codePointAt(0);
    hash = Math.imul(hash, 0x01000193) >>> 0;
  }
  return hash / 2 ** 32;
}

const round = (value, digits = 3) => Number(value.toFixed(digits)) + 0; // "+ 0" turns -0 into 0

/** Degrees clockwise from north to a point on a circle of radius r around the origin. */
export function polar(r, degrees) {
  const radians = (degrees * Math.PI) / 180;
  return { x: round(r * Math.sin(radians)), y: round(-r * Math.cos(radians)) };
}

/**
 * One blip per post from the last RADAR_DAYS: each source owns an equal sector (in the order of
 * `slugs`), and the distance from the centre is the post's age. x/y are in units of the radius;
 * `bucket` (0-11) is the 30-degree slice the sweep crosses, for the reveal animation.
 */
export function radarBlips(items, slugs, now = new Date()) {
  const span = 360 / Math.max(slugs.length, 1);
  const blips = [];
  for (const item of items) {
    const index = slugs.indexOf(item.source);
    const radius = radarRadius(now.getTime() - new Date(item.publishedAt).getTime());
    if (index < 0 || radius === null) continue; // unknown source, too old or invalid date
    const angle = round(span * (index + SECTOR_PADDING + (1 - 2 * SECTOR_PADDING) * hashUnit(item.url)), 2);
    blips.push({
      source: item.source,
      angle,
      radius: round(radius),
      ...polar(radius, angle),
      bucket: Math.floor(angle / 30) % 12,
    });
  }
  return blips;
}

/** SVG path data for a clockwise arc of radius r from one bearing to another. */
export function arcPath(r, fromDegrees, toDegrees) {
  const sweep = toDegrees - fromDegrees;
  if (sweep >= 360) {
    return `${arcPath(r, fromDegrees, fromDegrees + 180)}${arcPath(r, fromDegrees + 180, fromDegrees + 360)}`;
  }
  const start = polar(r, fromDegrees);
  const end = polar(r, toDegrees);
  return `M${start.x} ${start.y}A${r} ${r} 0 ${sweep > 180 ? 1 : 0} 1 ${end.x} ${end.y}`;
}

/** Text alternative for the radar: how many recent posts each source has. */
export function radarSummary(blips, sources) {
  const counts = new Map(sources.map(({ slug }) => [slug, 0]));
  for (const { source } of blips) counts.set(source, (counts.get(source) ?? 0) + 1);
  const parts = sources.map(({ slug, name }) => {
    const count = counts.get(slug);
    return count ? `${count} from ${name}` : `none from ${name}`;
  });
  return `Posts from the last ${RADAR_DAYS} days: ${parts.join(", ")}.`;
}
