// DOM wiring for the AI News Radar page. All data is untrusted: text goes through
// textContent and links through safeHttpUrl, never innerHTML.
import {
  ALL,
  arcPath,
  describeOutage,
  groupByDay,
  isStale,
  needsRefresh,
  newestBySource,
  pageLocale,
  polar,
  radarBlips,
  radarSummary,
  relativeTime,
  safeHttpUrl,
  selectItems,
  sourceFromHash,
  unavailableSources,
} from "./lib.mjs?v=dev";

const $ = (id) => document.getElementById(id);
const view = {
  scope: $("scope"),
  scopeFace: $("scope-face"),
  sectors: $("scope-sectors"),
  blips: $("scope-blips"),
  freshness: $("freshness"),
  updated: $("updated"),
  filters: $("filters"),
  status: $("status"),
  summary: $("summary"),
  list: $("news"),
  shortcuts: $("shortcuts"),
};
// Radar geometry in the SVG's viewBox units (-100..100); the rings in index.html use the same.
const PLOT_RADIUS = 87;
const RIM_RADIUS = 94;
const BLIP_RADIUS = 3.2;

let data = null;
let current = ALL;
const ages = new Map(); // slug -> the age <span> inside its filter button

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function svgElement(tag, className, attributes) {
  const node = document.createElementNS(view.blips.namespaceURI, tag);
  node.setAttribute("class", className);
  for (const [name, value] of Object.entries(attributes)) node.setAttribute(name, String(value));
  return node;
}

const slugClass = (slug) => String(slug).toLowerCase().replace(/[^a-z0-9-]/g, "");
const sourceClass = (slug) => `badge--${slugClass(slug)}`;
const slugs = () => data.sources.map((source) => source.slug);
const names = () => new Map(data.sources.map((source) => [source.slug, source.name]));

// --- News list --------------------------------------------------------------------------------

function renderItem(item, sourceNames) {
  const url = safeHttpUrl(item.url);
  if (!url) return null;
  const li = element("li", "entry");
  const article = element("article", "entry-body");
  const source = element("p", "entry-source");
  source.append(element("span", `badge ${sourceClass(item.source)}`, sourceNames.get(item.source) ?? item.source));
  const heading = element("h3", "entry-title");
  const link = element("a", null, item.title);
  link.href = url;
  heading.append(link);
  article.append(source, heading);
  if (item.description) article.append(element("p", "entry-desc", item.description));
  li.append(article);
  return li;
}

function renderDay({ key, label, items }, index, sourceNames) {
  const section = element("section", "day");
  const heading = element("h2", "day-heading");
  const time = element("time", null, label);
  if (key) time.dateTime = key;
  heading.id = `day-${index}`;
  heading.append(time);
  section.setAttribute("aria-labelledby", heading.id);
  const list = element("ol", "entries");
  list.append(...items.map((item) => renderItem(item, sourceNames)).filter(Boolean));
  section.append(heading, list);
  return section;
}

function renderItems() {
  const sourceNames = names();
  const items = selectItems(data.items, current, data.sources);
  const name = sourceNames.get(current);
  if (items.length === 0) {
    view.list.replaceChildren(
      element(
        "p",
        "placeholder",
        current === ALL
          ? "No headlines collected yet. They appear here after the first hourly check."
          : `No posts from ${name} yet. New posts appear here after the next hourly check.`,
      ),
    );
  } else {
    const days = groupByDay(items, { locale: pageLocale(navigator.languages ?? []) });
    view.list.replaceChildren(...days.map((day, index) => renderDay(day, index, sourceNames)));
  }
  view.summary.textContent =
    current === ALL
      ? `Showing the latest ${items.length} posts from every company.`
      : `Showing ${items.length} posts from ${name}.`;
}

// --- Filters (they double as the radar's legend) ------------------------------------------------

function renderFilters() {
  ages.clear();
  const rows = [{ slug: ALL, name: "All" }, ...data.sources].map(({ slug, name }) => {
    const button = element("button", "filter");
    button.type = "button";
    button.dataset.source = slug;
    button.setAttribute("aria-pressed", String(slug === current));
    const dot = element("span", slug === ALL ? "filter-dot filter-dot--all" : `filter-dot ${sourceClass(slug)}`);
    dot.setAttribute("aria-hidden", "true");
    button.append(dot, element("span", "filter-name", name));
    if (slug !== ALL) {
      const age = element("span", "filter-age");
      ages.set(slug, age);
      button.append(age);
    }
    button.addEventListener("click", () => select(slug, { fromUser: true }));
    const li = element("li");
    li.append(button);
    return li;
  });
  view.filters.replaceChildren(...rows);
  renderAges();
}

function renderAges() {
  const newest = newestBySource(data.items);
  for (const source of data.sources) {
    const age = ages.get(source.slug);
    if (!age) continue;
    const when = newest.has(source.slug) ? relativeTime(newest.get(source.slug)) : "";
    age.classList.toggle("filter-age--down", !source.ok);
    age.replaceChildren(
      element("span", "visually-hidden", source.ok ? ", newest post " : ", "),
      source.ok ? when || "no posts yet" : "check failed",
    );
  }
}

function select(slug, { fromUser = false } = {}) {
  current = slug;
  for (const button of view.filters.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.source === slug));
  }
  if (fromUser) {
    history.replaceState(null, "", slug === ALL ? location.pathname : `#${slug}`);
  }
  highlightRadar();
  renderItems();
}

// --- Radar ------------------------------------------------------------------------------------

function renderRadar() {
  const span = 360 / Math.max(data.sources.length, 1);
  const sectors = data.sources.flatMap(({ slug }, index) => {
    const start = span * index;
    const edge = polar(PLOT_RADIUS, start);
    return [
      svgElement("line", "scope-spoke", { x1: 0, y1: 0, x2: edge.x, y2: edge.y }),
      svgElement("path", `scope-rim ${sourceClass(slug)}`, {
        d: arcPath(RIM_RADIUS, start + 4, start + span - 4),
        "data-source": slug,
      }),
    ];
  });
  view.sectors.replaceChildren(...sectors);

  const blips = radarBlips(data.items, slugs());
  view.blips.replaceChildren(
    ...blips.map((blip) =>
      svgElement("circle", `blip ${sourceClass(blip.source)}`, {
        cx: (blip.x * PLOT_RADIUS).toFixed(1),
        cy: (blip.y * PLOT_RADIUS).toFixed(1),
        r: BLIP_RADIUS,
        "data-source": blip.source,
        "data-bucket": blip.bucket,
      }),
    ),
  );
  view.scopeFace.setAttribute("aria-label", radarSummary(blips, data.sources));
  highlightRadar();
  view.scope.dataset.state = "ready"; // starts the one-off sweep (unless reduced motion)
}

function highlightRadar() {
  for (const mark of view.scope.querySelectorAll("[data-source]")) {
    mark.classList.toggle("is-dimmed", current !== ALL && mark.dataset.source !== current);
  }
}

// --- Header status and notices ------------------------------------------------------------------

function renderUpdated() {
  const when = relativeTime(data.generatedAt);
  const stale = isStale(data.generatedAt);
  view.updated.textContent = !when
    ? "Update time unknown"
    : stale
      ? `Updated ${when}, later than the usual hourly check`
      : `Updated ${when}`;
  view.updated.dateTime = data.generatedAt;
  view.freshness.dataset.state = stale ? "stale" : "fresh";
}

function renderStatus() {
  const down = unavailableSources(data.sources);
  view.status.hidden = down.length === 0;
  if (!down.length) {
    view.status.replaceChildren();
    return;
  }
  const one = down.length === 1;
  const list = element("ul", "notice-list");
  list.append(...down.map((source) => element("li", null, describeOutage(source))));
  view.status.replaceChildren(
    element(
      "p",
      "notice-title",
      one
        ? `${down[0].name} was not reachable on the last check.`
        : `${down.length} sources were not reachable on the last check.`,
    ),
    list,
    element(
      "p",
      "notice-note",
      `${one ? "Its" : "Their"} posts below are from the last successful check.`,
    ),
  );
}

function renderShortcuts() {
  const list = element("ul", "shortcut-list");
  for (const { slug, name } of data.sources) {
    const link = element("a", null, name);
    link.href = `/latest/${encodeURIComponent(slug)}`;
    const li = element("li");
    li.append(link);
    list.append(li);
  }
  view.shortcuts.replaceChildren(element("p", "shortcuts-label", "Open the newest post from"), list);
  view.shortcuts.hidden = false;
}

function renderLoadError(reason) {
  view.updated.textContent = "News unavailable";
  view.freshness.dataset.state = "down";
  view.scope.dataset.state = "down";
  view.scopeFace.setAttribute("aria-label", "Radar of recent posts, unavailable");
  const reload = element("button", "notice-action", "Reload the page");
  reload.type = "button";
  reload.addEventListener("click", () => location.reload());
  view.status.replaceChildren(
    element("p", "notice-title", `The news list did not load (${reason}).`),
    element(
      "p",
      "notice-note",
      "The list is rebuilt every hour, so reload in a few minutes. The RSS feed has the same headlines.",
    ),
    reload,
  );
  view.status.hidden = false;
  view.list.replaceChildren();
}

// --- Loading ------------------------------------------------------------------------------------

let fetchedAt = null; // when news.json last loaded successfully
let loading = false;

function renderClock() {
  if (!data) return;
  renderUpdated();
  renderAges();
}

// Runs at start-up and whenever the page comes back into view: an app on the home screen stays
// in memory for days and has no reload button, so it must fetch fresh news by itself.
async function load() {
  if (loading || !needsRefresh(fetchedAt)) return;
  loading = true;
  let next;
  try {
    const response = await fetch("/news.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    next = await response.json();
    if (!Array.isArray(next?.sources) || !Array.isArray(next?.items)) throw new Error("unexpected data");
  } catch (error) {
    // A failed refresh keeps the list on screen; "Updated X ago" already shows its age.
    if (!data) {
      const reason =
        error instanceof TypeError ? "network error" : error instanceof SyntaxError ? "unreadable data" : error.message;
      renderLoadError(reason);
    }
    return;
  } finally {
    loading = false;
  }
  fetchedAt = new Date();
  if (data && next.generatedAt === data.generatedAt) return; // no new run since the last fetch
  data = next;
  current = sourceFromHash(location.hash, slugs());
  renderFilters();
  renderItems();
  renderUpdated();
  renderStatus();
  renderShortcuts();
  renderRadar();
}

setInterval(renderClock, 60_000);
window.addEventListener("hashchange", () => {
  if (data) select(sourceFromHash(location.hash, slugs()));
});
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState !== "visible") return;
  renderClock(); // timers do not run in the background
  load();
});
window.addEventListener("pageshow", (event) => {
  if (event.persisted) load(); // restored from the back/forward cache
});

load();
