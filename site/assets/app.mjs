// DOM wiring for the AI News Radar page. All data is untrusted: text goes through
// textContent and links through safeHttpUrl, never innerHTML.
import {
  ALL,
  formatDate,
  isStale,
  relativeTime,
  safeHttpUrl,
  selectItems,
  sourceFromHash,
  unavailableSources,
} from "./lib.mjs?v=dev";

const $ = (id) => document.getElementById(id);
const view = {
  filters: $("filters"),
  list: $("news"),
  status: $("status"),
  summary: $("summary"),
  updated: $("updated"),
  shortcuts: $("shortcuts"),
};
let data = null;
let current = ALL;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

const slugClass = (slug) => String(slug).toLowerCase().replace(/[^a-z0-9-]/g, "");
const names = () => new Map(data.sources.map((source) => [source.slug, source.name]));

function renderItem(item, sourceNames) {
  const url = safeHttpUrl(item.url);
  if (!url) return null;
  const li = element("li", "item");
  const article = element("article");
  const meta = element("p", "item-meta");
  meta.append(element("span", `badge badge--${slugClass(item.source)}`, sourceNames.get(item.source) ?? item.source));
  const time = element("time", "item-date", formatDate(item.publishedAt));
  time.dateTime = item.publishedAt;
  meta.append(time);
  const heading = element("h2", "item-title");
  const link = element("a", null, item.title);
  link.href = url;
  heading.append(link);
  article.append(meta, heading);
  if (item.description) article.append(element("p", "item-desc", item.description));
  li.append(article);
  return li;
}

function renderItems() {
  const sourceNames = names();
  const items = selectItems(data.items, current);
  view.list.replaceChildren(...items.map((item) => renderItem(item, sourceNames)).filter(Boolean));
  view.summary.textContent =
    current === ALL
      ? `Showing the latest ${items.length} items from every company.`
      : `Showing ${items.length} items from ${sourceNames.get(current)}.`;
}

function renderFilters() {
  const buttons = [{ slug: ALL, name: "All" }, ...data.sources].map(({ slug, name }) => {
    const button = element("button", "filter", name);
    button.type = "button";
    button.dataset.source = slug;
    button.setAttribute("aria-pressed", String(slug === current));
    button.addEventListener("click", () => select(slug, { fromUser: true }));
    const li = element("li");
    li.append(button);
    return li;
  });
  view.filters.replaceChildren(...buttons);
}

function select(slug, { fromUser = false } = {}) {
  current = slug;
  for (const button of view.filters.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.source === slug));
  }
  if (fromUser) {
    history.replaceState(null, "", slug === ALL ? location.pathname : `#${slug}`);
  }
  renderItems();
}

function renderUpdated() {
  const when = relativeTime(data.generatedAt);
  view.updated.textContent = when ? `Updated ${when}` : "Update time unknown";
  view.updated.dateTime = data.generatedAt;
  view.updated.classList.toggle("updated--stale", isStale(data.generatedAt));
}

function renderStatus() {
  const down = unavailableSources(data.sources);
  view.status.hidden = down.length === 0;
  view.status.textContent = down.length
    ? `Temporarily unavailable: ${down.map(({ name, error }) => `${name} (${error})`).join(", ")}. ` +
      "Their latest stored posts are still listed."
    : "";
}

function renderShortcuts() {
  view.shortcuts.replaceChildren("Newest post shortcuts: ");
  data.sources.forEach(({ slug, name }, index) => {
    if (index) view.shortcuts.append(" · ");
    const link = element("a", null, name);
    link.href = `/latest/${encodeURIComponent(slug)}`;
    view.shortcuts.append(link);
  });
  view.shortcuts.hidden = false;
}

async function load() {
  try {
    const response = await fetch("/news.json", { cache: "no-cache" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    data = await response.json();
  } catch {
    view.updated.textContent = "News unavailable";
    view.status.hidden = false;
    view.status.textContent = "Could not load the news right now. Please try again in a few minutes.";
    return;
  }
  current = sourceFromHash(location.hash, data.sources.map((source) => source.slug));
  renderFilters();
  renderItems();
  renderUpdated();
  renderStatus();
  renderShortcuts();
  setInterval(renderUpdated, 60_000);
  window.addEventListener("hashchange", () =>
    select(sourceFromHash(location.hash, data.sources.map((source) => source.slug))),
  );
}

load();
