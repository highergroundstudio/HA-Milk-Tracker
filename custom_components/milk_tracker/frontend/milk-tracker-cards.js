/*
 * Milk Tracker — Lovelace cards
 *
 *   custom:milk-tracker-card            Stash overview + one-tap logging
 *   custom:milk-tracker-goal-card       Stash goal (vacation / back to work)
 *   custom:milk-tracker-history-card    Daily pumped vs fed chart + full log
 *   custom:milk-tracker-inventory-card  Fridge / freezer batches with expiry
 *
 * Served and auto-loaded by the milk_tracker integration. No build step,
 * no external dependencies — plain web components.
 */

const VERSION = "1.0.0-beta.3";
const DOMAIN = "milk_tracker";

/* ------------------------------------------------------------------ */
/* Helpers                                                            */
/* ------------------------------------------------------------------ */

const esc = (s) =>
  String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);

const fmtAmount = (n, unit) => {
  if (n === null || n === undefined || Number.isNaN(Number(n))) return "–";
  const v = Number(n);
  const digits = unit === "ml" ? 0 : Math.abs(v) < 10 ? 1 : Math.abs(v) < 100 ? 1 : 0;
  return v.toLocaleString(undefined, { maximumFractionDigits: digits, minimumFractionDigits: 0 });
};

const withUnit = (n, unit) => `${fmtAmount(n, unit)} ${unit}`;

const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;

function duration(ms, { short = true } = {}) {
  const abs = Math.abs(ms);
  const m = Math.round(abs / 60000);
  if (m < 1) return short ? "<1m" : "less than a minute";
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  const mm = m % 60;
  if (h < 24) return mm && h < 10 ? `${h}h ${mm}m` : `${h}h`;
  const d = Math.floor(h / 24);
  const hh = h % 24;
  return hh && d < 4 ? `${d}d ${hh}h` : `${d}d`;
}

function ago(iso) {
  if (!iso) return "never";
  const ms = Date.now() - new Date(iso).getTime();
  if (ms < 60000) return "just now";
  return `${duration(ms)} ago`;
}

const sameDay = (a, b) => a.toDateString() === b.toDateString();

function whenLabel(iso, locale) {
  const d = new Date(iso);
  const now = new Date();
  const time = d.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
  if (sameDay(d, now)) return `Today ${time}`;
  const y = new Date(now);
  y.setDate(now.getDate() - 1);
  if (sameDay(d, y)) return `Yesterday ${time}`;
  return `${d.toLocaleDateString(locale, { weekday: "short", month: "short", day: "numeric" })} ${time}`;
}

const dateLabel = (iso, locale, opts = { weekday: "short", month: "short", day: "numeric" }) =>
  new Date(`${iso}T12:00:00`).toLocaleDateString(locale, opts);

const KIND = {
  pump: { icon: "mdi:water-plus", label: "Pumped", cls: "pump" },
  feed: { icon: "mdi:baby-bottle", label: "Fed", cls: "feed" },
  discard: { icon: "mdi:delete-outline", label: "Discarded", cls: "discard" },
  freeze: { icon: "mdi:snowflake", label: "Froze", cls: "freezer" },
  thaw: { icon: "mdi:snowflake-melt", label: "Thawed", cls: "fridge" },
  adjust: { icon: "mdi:pencil", label: "Corrected", cls: "muted" },
  stock: { icon: "mdi:calendar-plus", label: "Added stored", cls: "freezer" },
};

const LOC = {
  fridge: { icon: "mdi:fridge-outline", label: "Fridge" },
  freezer: { icon: "mdi:snowflake", label: "Freezer" },
  auto: { icon: "mdi:auto-fix", label: "Oldest first" },
};

function entryText(e, unit) {
  const k = KIND[e.kind] || { label: e.kind };
  const amt = withUnit(Math.abs(e.amount), unit);
  switch (e.kind) {
    case "pump":
      return `${k.label} ${amt} <span class="sub">→ ${LOC[e.location]?.label ?? e.location}</span>`;
    case "feed": {
      const fresh = e.from_stash !== undefined && e.from_stash + 0.001 < e.amount;
      return `${k.label} ${amt}${fresh ? ` <span class="sub">· ${withUnit(e.amount - e.from_stash, unit)} not from stash</span>` : ""}`;
    }
    case "freeze":
    case "thaw":
      return `${k.label} ${amt}`;
    case "stock":
      return `${k.label} ${amt} <span class="sub">· pumped ${new Date(e.pumped_at).toLocaleDateString(undefined, { month: "short", day: "numeric" })}${e.replaced ? " · dated from stash" : ""}</span>`;
    case "adjust":
      return `${k.label} ${LOC[e.location]?.label ?? ""} ${e.amount > 0 ? "+" : "−"}${amt}`;
    default:
      return `${k.label} ${amt}`;
  }
}

/* ------------------------------------------------------------------ */
/* Shared styles                                                      */
/* ------------------------------------------------------------------ */

const BASE_CSS = `
  :host {
    --mt-pump: var(--milk-tracker-pump-color, #14b8a6);
    --mt-feed: var(--milk-tracker-feed-color, #f59e0b);
    --mt-fridge: var(--milk-tracker-fridge-color, #38bdf8);
    --mt-freezer: var(--milk-tracker-freezer-color, #818cf8);
    --mt-warn: var(--warning-color, #f59e0b);
    --mt-error: var(--error-color, #ef4444);
    --mt-ok: var(--success-color, #22c55e);
    --mt-radius: var(--ha-card-border-radius, 12px);
    --mt-surface: color-mix(in srgb, var(--primary-text-color) 5%, transparent);
    --mt-surface-2: color-mix(in srgb, var(--primary-text-color) 9%, transparent);
    display: block;
  }
  ha-card { padding: 16px; overflow: hidden; height: 100%; box-sizing: border-box; container-type: inline-size; }
  * { box-sizing: border-box; }
  button { font: inherit; color: inherit; }
  .row { display: flex; align-items: center; gap: 8px; }
  .spacer { flex: 1; }
  .muted, .sub { color: var(--secondary-text-color); }
  .sub { font-size: 0.85em; }
  .header { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; }
  .header .title { font-size: 1.05rem; font-weight: 600; line-height: 1.2; }
  .header .subtitle { font-size: 0.85rem; color: var(--secondary-text-color); }
  .badge-icon {
    --mdc-icon-size: 22px;
    width: 40px; height: 40px; border-radius: 50%;
    display: grid; place-items: center; flex: none;
    background: color-mix(in srgb, var(--accent, var(--primary-color)) 18%, transparent);
    color: var(--accent, var(--primary-color));
  }
  .icon-btn {
    --mdc-icon-size: 20px;
    border: none; background: transparent; cursor: pointer; border-radius: 50%;
    width: 36px; height: 36px; display: grid; place-items: center; flex: none;
    color: var(--secondary-text-color); transition: background .15s, color .15s;
  }
  .icon-btn:hover { background: var(--mt-surface-2); color: var(--primary-text-color); }
  .icon-btn.confirm { background: color-mix(in srgb, var(--mt-error) 18%, transparent); color: var(--mt-error); }
  .seg {
    display: grid; grid-auto-flow: column; grid-auto-columns: 1fr; gap: 4px;
    background: var(--mt-surface); padding: 4px; border-radius: 999px;
  }
  .seg button {
    --mdc-icon-size: 18px;
    border: none; background: transparent; border-radius: 999px; padding: 8px 10px;
    cursor: pointer; display: flex; align-items: center; justify-content: center; gap: 6px;
    color: var(--secondary-text-color); font-weight: 500; font-size: 0.9rem;
    transition: background .15s, color .15s; min-height: 36px;
  }
  .seg button.on { background: var(--card-background-color, #fff); color: var(--primary-text-color);
    box-shadow: 0 1px 3px rgba(0,0,0,.15); }
  .seg.small button { padding: 4px 8px; min-height: 28px; font-size: 0.8rem; }
  .pill {
    --mdc-icon-size: 16px;
    display: inline-flex; align-items: center; gap: 4px; padding: 3px 9px; border-radius: 999px;
    font-size: 0.78rem; font-weight: 500; white-space: nowrap;
    background: var(--mt-surface-2); color: var(--secondary-text-color);
  }
  .pill.warn { background: color-mix(in srgb, var(--mt-warn) 18%, transparent); color: var(--mt-warn); }
  .pill.error { background: color-mix(in srgb, var(--mt-error) 16%, transparent); color: var(--mt-error); }
  .pill.ok { background: color-mix(in srgb, var(--mt-ok) 16%, transparent); color: var(--mt-ok); }
  .divider { height: 1px; background: var(--divider-color); margin: 14px -16px; }
  .section-title { font-size: 0.78rem; text-transform: uppercase; letter-spacing: .06em;
    color: var(--secondary-text-color); font-weight: 600; margin: 0 0 8px; display: flex; align-items: center; gap: 6px; }
  .empty { text-align: center; color: var(--secondary-text-color); padding: 18px 8px; font-size: 0.9rem; }
  .empty ha-icon { --mdc-icon-size: 36px; display: block; margin: 0 auto 6px; opacity: .6; }
  .primary-btn {
    --mdc-icon-size: 20px;
    width: 100%; border: none; border-radius: 999px; padding: 12px 16px; min-height: 48px;
    background: var(--accent, var(--primary-color)); color: var(--text-primary-color, #fff);
    font-weight: 600; font-size: 1rem; cursor: pointer; display: flex; align-items: center;
    justify-content: center; gap: 8px; transition: filter .15s, transform .08s;
  }
  .primary-btn:hover { filter: brightness(1.06); }
  .primary-btn:active { transform: scale(.98); }
  .primary-btn[disabled] { opacity: .5; cursor: default; }
  .ghost-btn {
    --mdc-icon-size: 18px;
    border: 1px solid var(--divider-color); background: transparent; border-radius: 999px;
    padding: 6px 12px; cursor: pointer; display: inline-flex; align-items: center; gap: 6px;
    font-size: 0.85rem; font-weight: 500;
  }
  .ghost-btn:hover { background: var(--mt-surface); }
  .field { display: flex; flex-direction: column; gap: 4px; font-size: 0.8rem; color: var(--secondary-text-color); }
  .field input {
    font: inherit; font-size: 1rem; color: var(--primary-text-color);
    background: var(--mt-surface); border: 1px solid var(--divider-color); border-radius: 8px;
    padding: 8px 10px; width: 100%; color-scheme: light dark;
  }
  .field input:focus { outline: 2px solid var(--primary-color); outline-offset: -1px; }
  .error-box { color: var(--mt-error); padding: 8px; font-size: 0.9rem; }
  .list { display: flex; flex-direction: column; }
  .item { display: flex; align-items: center; gap: 10px; padding: 7px 0; min-height: 44px; }
  .item + .item { border-top: 1px solid color-mix(in srgb, var(--divider-color) 60%, transparent); }
  .item .dot {
    --mdc-icon-size: 18px; width: 32px; height: 32px; border-radius: 50%; flex: none;
    display: grid; place-items: center;
  }
  .item .body { flex: 1; min-width: 0; }
  .item .line1 { font-size: 0.92rem; font-weight: 500; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .item .line2 { font-size: 0.78rem; color: var(--secondary-text-color); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
  .c-pump { --c: var(--mt-pump); } .c-feed { --c: var(--mt-feed); }
  .c-fridge { --c: var(--mt-fridge); } .c-freezer { --c: var(--mt-freezer); }
  .c-discard { --c: var(--mt-error); } .c-muted { --c: var(--secondary-text-color); }
  .dot { background: color-mix(in srgb, var(--c) 16%, transparent); color: var(--c); }
`;

/* ------------------------------------------------------------------ */
/* Base class: subscription, service calls, toasts, two-tap confirm   */
/* ------------------------------------------------------------------ */

class MilkTrackerBase extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._data = null;
    this._error = null;
    this._unsub = null;
    this._confirm = null;
  }

  static logLimit = 10;

  setConfig(config) {
    if (!config) throw new Error("Invalid configuration");
    const changedEntry = this._config && this._config.entry_id !== config.entry_id;
    this._config = { ...config };
    if (changedEntry) this._resubscribe();
    this._render();
  }

  set hass(hass) {
    const first = !this._hass;
    this._hass = hass;
    if (first || !this._unsub) this._subscribe();
  }

  get hass() {
    return this._hass;
  }

  connectedCallback() {
    if (this._hass && !this._unsub) this._subscribe();
  }

  disconnectedCallback() {
    this._unsubscribe();
  }

  _logLimit() {
    return this.constructor.logLimit;
  }

  async _subscribe() {
    if (!this._hass || this._unsub || this._subscribing || !this.isConnected) return;
    // After a failure, don't retry on every state change — at most every 30 s.
    if (this._error && Date.now() - (this._lastAttempt || 0) < 30000) return;
    this._lastAttempt = Date.now();
    this._subscribing = true;
    try {
      const msg = { type: `${DOMAIN}/subscribe`, log_limit: this._logLimit() };
      if (this._config?.entry_id) msg.entry_id = this._config.entry_id;
      this._unsub = await this._hass.connection.subscribeMessage((data) => {
        this._data = data;
        this._error = null;
        this._render();
      }, msg);
    } catch (err) {
      this._error =
        err?.code === "unknown_command"
          ? "The Milk Tracker integration isn't loaded. Add it under Settings → Devices & services."
          : err?.message || "Milk Tracker is not set up yet.";
      this._render();
    } finally {
      this._subscribing = false;
    }
  }

  _unsubscribe() {
    if (this._unsub) {
      const u = this._unsub;
      this._unsub = null;
      Promise.resolve(u).then((fn) => typeof fn === "function" && fn()).catch(() => {});
    }
  }

  _resubscribe() {
    this._unsubscribe();
    this._data = null;
    this._subscribe();
  }

  get unit() {
    return this._data?.unit || "oz";
  }

  get locale() {
    return this._hass?.locale?.language || navigator.language;
  }

  async _call(service, data = {}, { toast, undo = false } = {}) {
    const payload = { ...data, config_entry_id: this._data?.entry_id };
    try {
      const res = await this._hass.callService(DOMAIN, service, payload, undefined, true, true);
      const entry = res?.response?.entry;
      if (toast) {
        this._toast(toast, undo && entry?.id ? entry.id : null);
      }
      this._haptic("success");
      return res?.response;
    } catch (err) {
      this._haptic("failure");
      this._toast(err?.message || "Something went wrong");
      return null;
    }
  }

  _toast(message, undoEntryId = null) {
    const detail = { message, duration: undoEntryId ? 6000 : 3000 };
    if (undoEntryId) {
      detail.action = {
        text: "Undo",
        action: () => this._call("delete_entry", { entry_id: undoEntryId }, { toast: "Undone" }),
      };
    }
    this.dispatchEvent(new CustomEvent("hass-notification", { detail, bubbles: true, composed: true }));
  }

  _haptic(type) {
    this.dispatchEvent(new CustomEvent("haptic", { detail: type, bubbles: true, composed: true }));
  }

  /** Two-tap confirm for destructive buttons. Returns true on the 2nd tap. */
  _confirmTap(key) {
    if (this._confirm === key) {
      this._confirm = null;
      clearTimeout(this._confirmTimer);
      return true;
    }
    this._confirm = key;
    clearTimeout(this._confirmTimer);
    this._confirmTimer = setTimeout(() => {
      this._confirm = null;
      this._render();
    }, 3000);
    this._render();
    return false;
  }

  _openMoreInfo(entityId) {
    this.dispatchEvent(new CustomEvent("hass-more-info", { detail: { entityId }, bubbles: true, composed: true }));
  }

  _shell(inner, accent) {
    return `<style>${BASE_CSS}${this.constructor.css || ""}</style>
      <ha-card style="${accent ? `--accent:${accent}` : ""}">${inner}</ha-card>`;
  }

  _render() {
    if (!this._config) return;
    if (this._error) {
      this.shadowRoot.innerHTML = this._shell(
        `<div class="empty"><ha-icon icon="mdi:baby-bottle-outline"></ha-icon>${esc(this._error)}</div>`
      );
      return;
    }
    if (!this._data) {
      this.shadowRoot.innerHTML = this._shell(`<div class="empty">Loading…</div>`);
      return;
    }
    // Keep values the user has typed (live updates re-render every minute).
    const typed = {};
    if (!this._resetInputs) {
      for (const el of this.shadowRoot.querySelectorAll("input[id][data-dirty]")) {
        typed[el.id] = el.type === "checkbox" ? el.checked : el.value;
      }
    }
    this._resetInputs = false;
    // Preserve focus/caret in inputs across re-renders.
    const active = this.shadowRoot.activeElement;
    const focusId = active?.id;
    const selStart = active?.selectionStart;
    this.shadowRoot.innerHTML = this._shell(this.renderCard(), this.constructor.accent);
    for (const [id, v] of Object.entries(typed)) {
      const el = this.shadowRoot.getElementById(id);
      if (!el) continue;
      if (el.type === "checkbox") el.checked = v;
      else el.value = v;
      el.dataset.dirty = "1";
    }
    if (focusId) {
      const el = this.shadowRoot.getElementById(focusId);
      if (el) {
        el.focus();
        try { if (selStart != null) el.setSelectionRange(selStart, selStart); } catch (_) { /* date inputs */ }
      }
    }
    this.afterRender?.();
  }

  // Event delegation: elements with data-action="name" call this.on_name(el, ev)
  _bindDelegation() {
    if (this._bound) return;
    this._bound = true;
    this.shadowRoot.addEventListener("click", (ev) => {
      const el = ev.composedPath().find((n) => n?.dataset?.action);
      if (!el || el.disabled) return;
      const fn = this[`on_${el.dataset.action}`];
      if (fn) {
        ev.stopPropagation();
        fn.call(this, el, ev);
      }
    });
    this.shadowRoot.addEventListener("input", (ev) => {
      if (ev.target?.id) ev.target.dataset.dirty = "1";
    });
    this.shadowRoot.addEventListener("change", (ev) => {
      if (ev.target?.id) ev.target.dataset.dirty = "1";
      const el = ev.target;
      const fn = el?.dataset?.change && this[`on_${el.dataset.change}`];
      if (fn) fn.call(this, el, ev);
    });
  }

  getCardSize() {
    return 4;
  }

  static getConfigForm() {
    return {
      schema: [{ name: "entry_id", selector: { config_entry: { integration: DOMAIN } } }],
      computeLabel: (s) => ({ entry_id: "Tracker (leave empty if you only have one)" })[s.name] || s.name,
    };
  }
}

/* ------------------------------------------------------------------ */
/* 1. Main card: stash overview + logging                             */
/* ------------------------------------------------------------------ */

class MilkTrackerCard extends MilkTrackerBase {
  static accent = "var(--mt-pump)";
  static logLimit = 10;

  static css = `
    .hero { display: flex; align-items: flex-start; gap: 12px; }
    .hero .amount { font-size: 2.6rem; font-weight: 700; line-height: 1; letter-spacing: -0.02em; }
    .hero .amount small { font-size: 1.1rem; font-weight: 500; color: var(--secondary-text-color); margin-left: 2px; }
    .hero .caption { margin-top: 4px; font-size: 0.9rem; color: var(--secondary-text-color); }
    .hero .alerts { display: flex; flex-direction: column; align-items: flex-end; gap: 4px; margin-left: auto; }
    .stack { margin: 14px 0 6px; height: 10px; border-radius: 999px; background: var(--mt-surface-2);
      display: flex; overflow: hidden; gap: 2px; }
    .stack span { display: block; height: 100%; transition: width .4s ease; }
    .stack .f { background: var(--mt-fridge); } .stack .z { background: var(--mt-freezer); }
    .legend { display: flex; gap: 14px; font-size: 0.82rem; color: var(--secondary-text-color); flex-wrap: wrap; }
    .legend b { color: var(--primary-text-color); font-weight: 600; }
    .legend i { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; vertical-align: 1px; }
    .banner { --mdc-icon-size: 20px; display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px;
      margin-top: 12px; font-size: 0.88rem; cursor: pointer; border: none; width: 100%; text-align: left; }
    .banner.warn { background: color-mix(in srgb, var(--mt-warn) 14%, transparent); }
    .banner.warn ha-icon { color: var(--mt-warn); }
    .banner.error { background: color-mix(in srgb, var(--mt-error) 12%, transparent); }
    .banner.error ha-icon { color: var(--mt-error); }
    .banner b { font-weight: 600; }
    .chips { display: grid; grid-template-columns: repeat(auto-fit, minmax(42px, 1fr)); gap: 6px; margin: 12px 0; }
    .chip { border: 1px solid var(--divider-color); background: transparent; border-radius: 12px; padding: 10px 4px;
      font-weight: 600; font-size: 0.95rem; cursor: pointer; transition: all .12s; min-height: 44px; }
    .chip:hover { background: var(--mt-surface); }
    .chips.big .chip { min-height: 64px; font-size: 1.25rem; border-radius: 16px; }
    .chip.on { background: color-mix(in srgb, var(--accent) 16%, transparent); border-color: var(--accent); color: var(--accent); }
    .stepper { display: flex; align-items: center; gap: 8px; }
    .stepper .val { flex: 1; text-align: center; font-size: 1.5rem; font-weight: 700; display: flex; align-items: baseline; justify-content: center; gap: 4px; }
    .stepper .val input { width: 4.5ch; font: inherit; text-align: right; background: transparent; border: none;
      color: inherit; padding: 0; -moz-appearance: textfield; border-bottom: 2px dashed transparent; }
    .stepper .val input:focus { outline: none; border-bottom-color: var(--accent); }
    .stepper .val input::-webkit-inner-spin-button { -webkit-appearance: none; }
    .stepper .val span { font-size: 0.95rem; font-weight: 500; color: var(--secondary-text-color); }
    .round { --mdc-icon-size: 22px; width: 44px; height: 44px; border-radius: 50%; border: none; cursor: pointer;
      background: var(--mt-surface-2); display: grid; place-items: center; }
    .round:hover { background: color-mix(in srgb, var(--accent) 16%, transparent); color: var(--accent); }
    .opts { display: flex; align-items: center; gap: 8px; margin: 12px 0; flex-wrap: wrap; }
    .opts .seg { flex: 1; min-width: 200px; }
    .stats { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; }
    .stat { background: var(--mt-surface); border-radius: 10px; padding: 10px; cursor: default; min-width: 0; }
    .stat .k { font-size: 0.72rem; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; font-weight: 600;
      white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .stat .v { font-size: 1.15rem; font-weight: 700; margin-top: 2px; white-space: nowrap; }
    .stat .s { font-size: 0.75rem; color: var(--secondary-text-color); line-height: 1.3; }
    .more-fields { display: grid; grid-template-columns: 1fr 1.4fr; gap: 8px; margin-bottom: 12px; }
    .icon-btn.on { background: var(--mt-surface-2); color: var(--primary-text-color); }
    @container (max-width: 340px) {
      .stats { grid-template-columns: 1fr 1fr; }
      .stats .stat:last-child { grid-column: 1 / -1; }
      .hero .amount { font-size: 2.2rem; }
      .opts .seg { min-width: 0; }
      .more-fields { grid-template-columns: 1fr; }
    }
    .note-toggle input { flex: 1; }
  `;

  constructor() {
    super();
    this._mode = "pump";
    this._amount = null;
    this._location = null; // null = follow tracker / card default
    this._source = "auto";
    this._noteVal = "";
    this._whenVal = "";
    this._bindDelegation();
  }

  static getStubConfig() {
    return {};
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entry_id", selector: { config_entry: { integration: DOMAIN } } },
        { name: "title", selector: { text: {} } },
        { name: "quick_amounts", selector: { text: {} } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "one_tap", selector: { boolean: {} } },
            { name: "show_today", selector: { boolean: {} } },
            { name: "show_recent", selector: { number: { min: 0, max: 10, mode: "box" } } },
            { name: "default_mode", selector: { select: { options: ["pump", "feed"] } } },
            { name: "default_location", selector: { select: { options: ["freezer", "fridge"] } } },
          ],
        },
      ],
      computeLabel: (s) =>
        ({
          entry_id: "Tracker (leave empty if you only have one)",
          title: "Title",
          quick_amounts: "Quick amounts (comma separated)",
          one_tap: "One-tap logging (chips log immediately)",
          show_today: "Show today's stats",
          show_recent: "Recent entries to show",
          default_mode: "Default mode",
          default_location: "Pumped milk goes to (overrides the integration setting)",
        })[s.name],
    };
  }

  setConfig(config) {
    if (config.default_mode && !this._config) this._mode = config.default_mode;
    super.setConfig(config);
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  getCardSize() {
    return 8;
  }

  get quickAmounts() {
    let q = this._config.quick_amounts;
    if (typeof q === "string") q = q.split(/[,\s]+/).filter(Boolean);
    if (Array.isArray(q) && q.length) return q.map(Number).filter((n) => n > 0);
    return this.unit === "ml" ? [60, 90, 120, 150, 180] : [2, 3, 4, 5, 6];
  }

  get amount() {
    if (this._amount === null) {
      const q = this.quickAmounts;
      this._amount = q[Math.min(2, q.length - 1)] ?? 4;
    }
    return this._amount;
  }

  get step() {
    return this.unit === "ml" ? 10 : 0.5;
  }

  /* --- actions --- */
  on_mode(el) {
    this._mode = el.dataset.value;
    this._render();
  }
  get useFridge() {
    return this._data?.use_fridge !== false;
  }

  get location() {
    if (!this.useFridge) return "freezer";
    return this._location || this._config.default_location || this._data?.default_location || "freezer";
  }

  on_loc(el) {
    if (this._mode === "pump") this._location = el.dataset.value;
    else this._source = el.dataset.value;
    this._render();
  }
  on_chip(el) {
    this._amount = Number(el.dataset.value);
    if (this._config.one_tap) this.on_log();
    else this._render();
  }
  on_inc() {
    this._amount = Math.round((this.amount + this.step) * 100) / 100;
    this._render();
  }
  on_dec() {
    this._amount = Math.max(this.step, Math.round((this.amount - this.step) * 100) / 100);
    this._render();
  }
  on_amount_input(el) {
    const v = parseFloat(el.value);
    if (v > 0) this._amount = v;
    this._render();
  }
  on_note() {
    this._showNote = !this._showNote;
    if (!this._showNote) {
      this._noteVal = "";
      this._whenVal = "";
    }
    this._render();
    if (this._showNote) this.shadowRoot.getElementById("note")?.focus();
  }
  async on_log() {
    if (this._busy) return;
    const amount = this.amount;
    const note = this._noteVal.trim() || undefined;
    const timestamp = this._whenVal || undefined;
    const when = timestamp ? ` (${whenLabel(timestamp, this.locale)})` : "";
    this._busy = true;
    this._render();
    let ok;
    if (this._mode === "pump") {
      const location = this.location;
      ok = await this._call(
        "log_pump",
        { amount, location, note, timestamp },
        { toast: `Added ${withUnit(amount, this.unit)} to the ${location}${when}`, undo: true }
      );
    } else {
      ok = await this._call(
        "log_feed",
        { amount, source: this.useFridge ? this._source : "auto", note, timestamp },
        { toast: `Logged a ${withUnit(amount, this.unit)} feed${when}`, undo: true }
      );
    }
    if (ok) {
      this._showNote = false;
      this._noteVal = "";
      this._whenVal = "";
    }
    this._busy = false;
    this._render();
  }
  on_delete(el) {
    const id = el.dataset.id;
    if (!this._confirmTap(`del-${id}`)) return;
    this._call("delete_entry", { entry_id: id }, { toast: "Entry removed" });
  }
  on_discard_expired() {
    if (!this._confirmTap("expired")) return;
    this._call("discard_expired", {}, { toast: "Expired milk discarded" });
  }
  on_feed_oldest() {
    this._mode = "feed";
    this._source = "auto";
    this._render();
  }
  on_pump_now() {
    this._mode = "pump";
    this._render();
  }

  afterRender() {
    const input = this.shadowRoot.getElementById("amount");
    if (input && !input._mt) {
      input._mt = true;
      input.addEventListener("change", () => this.on_amount_input(input));
      input.addEventListener("keydown", (e) => e.key === "Enter" && input.blur());
    }
    const note = this.shadowRoot.getElementById("note");
    if (note && !note._mt) {
      note._mt = true;
      note.addEventListener("input", () => (this._noteVal = note.value));
      note.addEventListener("keydown", (e) => e.key === "Enter" && this.on_log());
    }
    const when = this.shadowRoot.getElementById("when");
    if (when && !when._mt) {
      when._mt = true;
      when.addEventListener("input", () => (this._whenVal = when.value));
      when.addEventListener("change", () => {
        this._whenVal = when.value;
        this._render();
      });
    }
  }

  renderCard() {
    const d = this._data;
    const s = d.summary;
    const u = this.unit;
    const cfg = this._config;
    const total = s.total || 0;
    const fPct = total > 0 ? (s.fridge / total) * 100 : 0;
    const zPct = total > 0 ? (s.freezer / total) * 100 : 0;
    const pump = this._mode === "pump";
    const accent = pump ? "var(--mt-pump)" : "var(--mt-feed)";

    const caption = [];
    if (s.days_of_supply !== null && s.days_of_supply !== undefined) {
      caption.push(`≈ <b>${fmtAmount(s.days_of_supply, "oz")}</b> days of supply`);
    }
    caption.push(s.last_pump ? `last pumped ${ago(s.last_pump)}` : "no pump sessions yet");

    // Alerts
    const banners = [];
    if (s.expired_amount > 0) {
      banners.push(`<button class="banner error" data-action="discard_expired">
        <ha-icon icon="mdi:alert-octagon-outline"></ha-icon>
        <span class="spacer"><b>${withUnit(s.expired_amount, u)}</b> is past its use-by date.</span>
        <span class="pill error">${this._confirm === "expired" ? "Tap again to discard" : "Discard"}</span></button>`);
    } else if (s.expiring_amount > 0 && s.next_expiry) {
      banners.push(`<button class="banner warn" data-action="feed_oldest">
        <ha-icon icon="mdi:timer-sand"></ha-icon>
        <span class="spacer"><b>${withUnit(s.expiring_amount, u)}</b> expires in ${duration(new Date(s.next_expiry) - Date.now())} — feeds use it first.</span></button>`);
    }
    if (s.pump_due) {
      banners.push(`<button class="banner warn" data-action="pump_now">
        <ha-icon icon="mdi:bell-ring-outline"></ha-icon>
        <span class="spacer"><b>Time to pump</b> — it's been ${duration(s.hours_since_pump * 3600000)} since your last session.</span></button>`);
    }

    const fridgeOn = this.useFridge;
    const locOptions = !fridgeOn ? [] : pump ? ["freezer", "fridge"] : ["auto", "fridge", "freezer"];
    const curLoc = pump ? this.location : this._source;
    const pad = (n) => String(n).padStart(2, "0");
    const now = new Date();
    const nowLocal = `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
    const chips = this.quickAmounts
      .map((q) => `<button class="chip ${!cfg.one_tap && q === this.amount ? "on" : ""}" data-action="chip" data-value="${q}">${fmtAmount(q, u)}</button>`)
      .join("");

    const showRecent = cfg.show_recent ?? 3;
    const recent = d.log.slice(0, showRecent);

    return `
      <div class="hero">
        <div>
          <div class="sub" style="font-weight:600;margin-bottom:6px">${esc(cfg.title || d.title || "Milk stash")}</div>
          <div class="amount">${fmtAmount(total, u)}<small>${u}</small></div>
          <div class="caption">${caption.join(" · ")}</div>
        </div>
        <ha-icon class="badge-icon" style="--accent:var(--mt-pump);margin-left:auto" icon="mdi:baby-bottle-outline"></ha-icon>
      </div>
      ${
        fridgeOn || s.fridge > 0
          ? `<div class="stack" role="img" aria-label="Fridge ${withUnit(s.fridge, u)}, freezer ${withUnit(s.freezer, u)}">
        <span class="f" style="width:${fPct}%"></span><span class="z" style="width:${zPct}%"></span>
      </div>
      <div class="legend">
        <span><i style="background:var(--mt-fridge)"></i>Fridge <b>${withUnit(s.fridge, u)}</b></span>
        <span><i style="background:var(--mt-freezer)"></i>Freezer <b>${withUnit(s.freezer, u)}</b></span>
      </div>`
          : ""
      }
      ${banners.join("")}

      <div class="divider"></div>

      <div style="--accent:${accent}">
        <div class="seg" role="tablist">
          <button class="${pump ? "on" : ""}" data-action="mode" data-value="pump" role="tab" aria-selected="${pump}">
            <ha-icon icon="mdi:water-plus" style="color:var(--mt-pump)"></ha-icon>Pumped</button>
          <button class="${!pump ? "on" : ""}" data-action="mode" data-value="feed" role="tab" aria-selected="${!pump}">
            <ha-icon icon="mdi:baby-bottle" style="color:var(--mt-feed)"></ha-icon>Fed</button>
        </div>
        <div class="chips ${cfg.one_tap ? "big" : ""}">${chips}</div>
        ${
          cfg.one_tap
            ? ""
            : `<div class="stepper">
                <button class="round" data-action="dec" aria-label="Less"><ha-icon icon="mdi:minus"></ha-icon></button>
                <label class="val"><input id="amount" type="number" inputmode="decimal" min="0" step="${this.step}" value="${this.amount}" aria-label="Amount"><span>${u}</span></label>
                <button class="round" data-action="inc" aria-label="More"><ha-icon icon="mdi:plus"></ha-icon></button>
              </div>`
        }
        <div class="opts">
          ${
            !locOptions.length
              ? `<span class="pill" style="margin-right:auto"><ha-icon icon="${pump ? "mdi:snowflake" : "mdi:auto-fix"}"></ha-icon>${pump ? "Goes in the freezer" : "Uses the oldest milk first"}</span>`
              : `<div class="seg small">
            ${locOptions
              .map(
                (l) => `<button class="${curLoc === l ? "on" : ""}" data-action="loc" data-value="${l}">
                  <ha-icon icon="${LOC[l].icon}"></ha-icon>${pump ? LOC[l].label : l === "auto" ? "Oldest" : LOC[l].label}</button>`
              )
              .join("")}
          </div>`
          }
          <button class="icon-btn ${this._showNote ? "on" : ""}" data-action="note" title="Add a note or an earlier time" aria-label="Add a note or an earlier time"><ha-icon icon="${this._showNote ? "mdi:close" : "mdi:clock-edit-outline"}"></ha-icon></button>
        </div>
        ${
          this._showNote
            ? `<div class="more-fields">
                <label class="field">When<input id="when" type="datetime-local" max="${nowLocal}" value="${esc(this._whenVal || nowLocal)}"></label>
                <label class="field">Note<input id="note" maxlength="120" placeholder="Optional — e.g. left side" value="${esc(this._noteVal)}"></label>
              </div>`
            : ""
        }
        ${
          cfg.one_tap
            ? ""
            : `<button class="primary-btn" data-action="log" ${this._busy ? "disabled" : ""}>
                <ha-icon icon="${pump ? "mdi:plus" : "mdi:minus"}"></ha-icon>
                ${pump ? `Add ${withUnit(this.amount, u)} to ${LOC[this.location].label.toLowerCase()}` : `Log ${withUnit(this.amount, u)} feed`}${this._whenVal ? ` · ${whenLabel(this._whenVal, this.locale)}` : ""}
              </button>`
        }
      </div>

      ${
        cfg.show_today === false
          ? ""
          : `<div class="divider"></div>
        <div class="stats">
          <div class="stat"><div class="k">Pumped</div><div class="v" style="color:var(--mt-pump)">${withUnit(s.pumped_today, u)}</div>
            <div class="s">today · ${plural(s.sessions_today, "session")}</div></div>
          <div class="stat"><div class="k">Fed</div><div class="v" style="color:var(--mt-feed)">${withUnit(s.fed_today, u)}</div>
            <div class="s">today · ${plural(s.feeds_today, "feed")}</div></div>
          <div class="stat"><div class="k">Average</div><div class="v">${withUnit(s.avg_pumped_per_day, u)}</div>
            <div class="s">pumped / day (7d)</div></div>
        </div>`
      }

      ${
        showRecent > 0
          ? `<div class="divider"></div>
        <div class="section-title"><ha-icon icon="mdi:history" style="--mdc-icon-size:16px"></ha-icon>Recent</div>
        ${recent.length ? `<div class="list">${recent.map((e) => this._entryRow(e)).join("")}</div>` : `<div class="empty" style="padding:6px">Nothing logged yet — tap a chip above to start.</div>`}`
          : ""
      }
    `;
  }

  _entryRow(e) {
    const k = KIND[e.kind] || KIND.adjust;
    const confirming = this._confirm === `del-${e.id}`;
    return `<div class="item">
      <ha-icon class="dot c-${k.cls}" icon="${k.icon}"></ha-icon>
      <div class="body">
        <div class="line1">${entryText(e, this.unit)}</div>
        <div class="line2">${whenLabel(e.ts, this.locale)}${e.note ? ` · ${esc(e.note)}` : ""}</div>
      </div>
      <button class="icon-btn ${confirming ? "confirm" : ""}" data-action="delete" data-id="${esc(e.id)}"
        title="${confirming ? "Tap again to remove" : "Remove"}" aria-label="Remove entry">
        <ha-icon icon="${confirming ? "mdi:check" : "mdi:close"}"></ha-icon></button>
    </div>`;
  }
}

/* ------------------------------------------------------------------ */
/* 2. Goal card                                                       */
/* ------------------------------------------------------------------ */

class MilkTrackerGoalCard extends MilkTrackerBase {
  static accent = "var(--mt-freezer)";
  static logLimit = 0;

  static css = `
    .goal { display: flex; align-items: center; gap: 18px; }
    .ring { position: relative; width: 116px; height: 116px; flex: none; }
    .ring svg { width: 100%; height: 100%; transform: rotate(-90deg); }
    .ring .track { stroke: var(--mt-surface-2); }
    .ring .bar { stroke: var(--accent); transition: stroke-dashoffset .6s ease; stroke-linecap: round; }
    .ring .center { position: absolute; inset: 0; display: grid; place-items: center; text-align: center; }
    .ring .pct { font-size: 1.6rem; font-weight: 700; line-height: 1; }
    .ring .pct small { font-size: .8rem; }
    .ring .lbl { font-size: .7rem; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .05em; }
    .facts { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
    .facts .big { font-size: 1.35rem; font-weight: 700; }
    .facts .big span { font-size: .9rem; font-weight: 500; color: var(--secondary-text-color); }
    .compare { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-top: 14px; }
    .compare > div { background: var(--mt-surface); border-radius: 10px; padding: 10px; }
    .compare .k { font-size: .72rem; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; font-weight: 600; }
    .compare .v { font-size: 1.1rem; font-weight: 700; margin-top: 2px; }
    .form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .form .full { grid-column: 1 / -1; }
    .actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
    .actions .primary-btn { width: auto; min-height: 40px; padding: 8px 18px; font-size: .9rem; }
    .switch-row { display: flex; align-items: center; justify-content: space-between; margin-top: 14px; font-size: .9rem; }
    .celebrate { text-align: center; font-size: 1rem; font-weight: 600; margin-top: 12px; color: var(--mt-ok); }
  `;

  constructor() {
    super();
    this._editing = false;
    this._bindDelegation();
  }

  static getStubConfig() {
    return {};
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  on_edit() {
    this._editing = !this._editing;
    this._render();
  }
  async on_save() {
    const $ = (id) => this.shadowRoot.getElementById(id);
    const amount = parseFloat($("g-amount").value);
    const date = $("g-date").value || null;
    const name = $("g-name").value.trim() || "Goal";
    await this._call(
      "configure",
      { goal_amount: amount > 0 ? amount : 0, goal_date: date, goal_name: name, goal_active: true },
      { toast: "Goal saved" }
    );
    this._editing = false;
    this._render();
  }
  on_toggle() {
    const g = this._data.summary.goal;
    this._call("configure", { goal_active: !g.active });
  }
  on_setup() {
    this._editing = true;
    this._render();
  }

  renderCard() {
    const s = this._data.summary;
    const g = s.goal || {};
    const u = this.unit;
    const title = esc(this._config.title || g.name || "Goal");

    const header = `<div class="header">
      <ha-icon class="badge-icon" icon="${esc(this._config.icon || "mdi:airplane")}"></ha-icon>
      <div class="spacer"><div class="title">${title}</div>
        <div class="subtitle">${g.date ? `${dateLabel(g.date, this.locale, { weekday: "short", month: "short", day: "numeric", year: "numeric" })}` : "Stash goal"}</div></div>
      ${g.active || this._editing ? `<button class="icon-btn" data-action="edit" aria-label="Edit goal"><ha-icon icon="${this._editing ? "mdi:close" : "mdi:pencil-outline"}"></ha-icon></button>` : ""}
    </div>`;

    if (this._editing) {
      return `${header}
        <div class="form">
          <label class="field full">Name<input id="g-name" maxlength="40" value="${esc(g.name && g.name !== "Goal" ? g.name : "")}" placeholder="Vacation, back to work…"></label>
          <label class="field">Amount (${u})<input id="g-amount" type="number" inputmode="decimal" min="0" step="${u === "ml" ? 10 : 1}" value="${g.amount || ""}"></label>
          <label class="field">Needed by<input id="g-date" type="date" value="${esc(g.date || "")}"></label>
        </div>
        <div class="actions">
          <button class="ghost-btn" data-action="edit">Cancel</button>
          <button class="primary-btn" data-action="save"><ha-icon icon="mdi:check"></ha-icon>Save goal</button>
        </div>`;
    }

    if (!g.active || !g.amount) {
      return `${header}
        <div class="empty"><ha-icon icon="mdi:bullseye-arrow"></ha-icon>
          Building a stash for a trip or going back to work?<br>Set a goal and we'll tell you if you're on track.</div>
        <button class="primary-btn" data-action="setup"><ha-icon icon="mdi:plus"></ha-icon>${g.amount ? "Resume goal" : "Set a goal"}</button>`;
    }

    const pct = Math.max(0, Math.min(100, g.progress ?? 0));
    const r = 50;
    const c = 2 * Math.PI * r;
    const offset = c * (1 - pct / 100);
    const daysLeft = g.days_left;
    const status = g.reached
      ? `<span class="pill ok"><ha-icon icon="mdi:party-popper"></ha-icon>Goal reached</span>`
      : daysLeft !== undefined && daysLeft <= 0
        ? `<span class="pill error"><ha-icon icon="mdi:calendar-alert"></ha-icon>Date passed</span>`
        : g.on_track === undefined
          ? `<span class="pill">Set a date to see your pace</span>`
          : g.on_track
            ? `<span class="pill ok"><ha-icon icon="mdi:check-circle-outline"></ha-icon>On track</span>`
            : `<span class="pill warn"><ha-icon icon="mdi:trending-down"></ha-icon>Behind · projected ${withUnit(g.projected, u)}</span>`;

    return `${header}
      <div class="goal">
        <div class="ring">
          <svg viewBox="0 0 120 120"><circle class="track" cx="60" cy="60" r="${r}" fill="none" stroke-width="12"/>
            <circle class="bar" cx="60" cy="60" r="${r}" fill="none" stroke-width="12"
              stroke-dasharray="${c}" stroke-dashoffset="${offset}"/></svg>
          <div class="center"><div><div class="pct">${Math.round(pct)}<small>%</small></div><div class="lbl">saved</div></div></div>
        </div>
        <div class="facts">
          <div class="big">${fmtAmount(s.total, u)} <span>/ ${withUnit(g.amount, u)}</span></div>
          <div class="muted">${g.reached ? "You did it! 🎉" : `<b style="color:var(--primary-text-color)">${withUnit(g.remaining, u)}</b> to go`}</div>
          ${daysLeft !== undefined ? `<div class="muted">${daysLeft > 0 ? `<b style="color:var(--primary-text-color)">${plural(daysLeft, "day")}</b> left` : daysLeft === 0 ? "Today's the day!" : `${plural(-daysLeft, "day")} ago`}</div>` : ""}
          <div>${status}</div>
        </div>
      </div>
      ${
        !g.reached && daysLeft > 0
          ? `<div class="compare">
        <div><div class="k">Need per day</div><div class="v">${withUnit(g.needed_per_day, u)}</div></div>
        <div><div class="k">Your net pace</div><div class="v" style="color:${s.net_per_day >= g.needed_per_day ? "var(--mt-ok)" : "var(--mt-warn)"}">${s.net_per_day > 0 ? "+" : ""}${withUnit(s.net_per_day, u)}</div></div>
      </div>`
          : ""
      }
      <div class="switch-row muted"><span>Net pace = pumped minus milk used from the stash (7-day average).</span></div>
      <div class="actions"><button class="ghost-btn" data-action="toggle"><ha-icon icon="mdi:pause"></ha-icon>Pause goal</button></div>
    `;
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entry_id", selector: { config_entry: { integration: DOMAIN } } },
        { name: "title", selector: { text: {} } },
        { name: "icon", selector: { icon: {} } },
      ],
      computeLabel: (s) => ({ entry_id: "Tracker (leave empty if you only have one)", title: "Title (defaults to goal name)", icon: "Icon" })[s.name],
    };
  }
}

/* ------------------------------------------------------------------ */
/* 3. History card                                                    */
/* ------------------------------------------------------------------ */

class MilkTrackerHistoryCard extends MilkTrackerBase {
  static accent = "var(--mt-pump)";

  static css = `
    .summary { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin: 4px 0 14px; }
    .summary > div { min-width: 0; }
    .summary .k { font-size: .72rem; color: var(--secondary-text-color); text-transform: uppercase; letter-spacing: .04em; font-weight: 600; }
    .summary .v { font-size: 1.1rem; font-weight: 700; white-space: nowrap; }
    .chart { position: relative; }
    .chart svg { width: 100%; height: 180px; display: block; overflow: visible; }
    .chart .grid line { stroke: var(--divider-color); stroke-dasharray: 2 3; }
    .chart .grid text, .chart .x text { fill: var(--secondary-text-color); font-size: 10px; }
    .chart .bar-p { fill: var(--mt-pump); } .chart .bar-f { fill: var(--mt-feed); }
    .chart .col { cursor: pointer; }
    .chart .col .hit { fill: transparent; }
    .chart .col.sel .hit, .chart .col:hover .hit { fill: var(--mt-surface); }
    .chart .avg { stroke: var(--primary-text-color); stroke-width: 1; stroke-dasharray: 4 3; opacity: .5; }
    .legend { display: flex; gap: 14px; font-size: .8rem; color: var(--secondary-text-color); margin-top: 8px; align-items: center; flex-wrap: wrap; }
    .legend i { width: 10px; height: 10px; border-radius: 3px; display: inline-block; margin-right: 6px; vertical-align: -1px; }
    .detail { margin-top: 10px; background: var(--mt-surface); border-radius: 10px; padding: 10px 12px; font-size: .88rem;
      display: flex; gap: 14px; flex-wrap: wrap; align-items: center; }
    .day-head { font-size: .78rem; font-weight: 600; color: var(--secondary-text-color); margin: 12px 0 2px;
      display: flex; justify-content: space-between; }
    .more { display: flex; justify-content: center; margin-top: 8px; }
    @container (max-width: 320px) {
      .header { flex-wrap: wrap; }
      .header .seg { width: 100% !important; order: 3; }
    }
  `;

  constructor() {
    super();
    this._range = null;
    this._sel = null;
    this._expanded = false;
    this._bindDelegation();
  }

  static getStubConfig() {
    return { days: 14, show_log: true };
  }

  static logLimit = 200;

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  get range() {
    return this._range ?? this._config.days ?? 14;
  }

  on_range(el) {
    this._range = Number(el.dataset.value);
    this._sel = null;
    this._render();
  }
  on_day(el) {
    this._sel = this._sel === el.dataset.date ? null : el.dataset.date;
    this._render();
  }
  on_more() {
    this._expanded = !this._expanded;
    this._render();
  }
  on_delete(el) {
    const id = el.dataset.id;
    if (!this._confirmTap(`del-${id}`)) return;
    this._call("delete_entry", { entry_id: id }, { toast: "Entry removed" });
  }

  afterRender() {
    if (!this._ro) {
      this._ro = new ResizeObserver(() => {
        const w = Math.round(this.shadowRoot.querySelector(".chart")?.clientWidth || 0);
        if (w && Math.abs(w - (this._chartW || 0)) > 4) {
          this._chartW = w;
          this._render();
        }
      });
      this._ro.observe(this);
    }
  }

  _chart(days) {
    const W = Math.max(260, this._chartW || this.shadowRoot.querySelector(".chart")?.clientWidth || 340);
    const H = 180;
    const padL = 30;
    const padB = 22;
    const padT = 8;
    const max = Math.max(this.unit === "ml" ? 120 : 4, ...days.map((d) => Math.max(d.pumped, d.fed)));
    const nice = (() => {
      const raw = max / 4;
      const mag = 10 ** Math.floor(Math.log10(raw));
      const step = [1, 2, 2.5, 5, 10].map((m) => m * mag).find((s) => s >= raw) || raw;
      return { step, top: step * 4 };
    })();
    const plotW = W - padL;
    const plotH = H - padB - padT;
    const colW = plotW / days.length;
    const barW = Math.max(2, Math.min(14, colW * 0.32));
    const y = (v) => padT + plotH - (v / nice.top) * plotH;
    const u = this.unit;

    let grid = "";
    for (let i = 0; i <= 4; i++) {
      const v = nice.step * i;
      grid += `<line x1="${padL}" x2="${W}" y1="${y(v)}" y2="${y(v)}"/><text x="${padL - 6}" y="${y(v) + 3}" text-anchor="end">${fmtAmount(v, u)}</text>`;
    }
    const labelEvery = Math.max(1, Math.ceil(days.length / Math.floor(plotW / 44)));
    const cols = days
      .map((d, i) => {
        const x = padL + i * colW;
        const cx = x + colW / 2;
        const sel = this._sel === d.date;
        const label =
          (days.length - 1 - i) % labelEvery === 0
            ? `<text x="${cx}" y="${H - 6}" text-anchor="middle">${i === days.length - 1 ? "Today" : dateLabel(d.date, this.locale, days.length > 7 ? { month: "numeric", day: "numeric" } : { weekday: "short" })}</text>`
            : "";
        const hp = Math.max(d.pumped > 0 ? 2 : 0, y(0) - y(d.pumped));
        const hf = Math.max(d.fed > 0 ? 2 : 0, y(0) - y(d.fed));
        return `<g class="col ${sel ? "sel" : ""}" data-action="day" data-date="${d.date}">
          <rect class="hit" x="${x + 1}" y="${padT}" width="${colW - 2}" height="${plotH}" rx="4"/>
          <rect class="bar-p" x="${cx - barW - 1}" y="${y(0) - hp}" width="${barW}" height="${hp}" rx="${Math.min(3, barW / 2)}"/>
          <rect class="bar-f" x="${cx + 1}" y="${y(0) - hf}" width="${barW}" height="${hf}" rx="${Math.min(3, barW / 2)}"/>
          <g class="x">${label}</g>
          <title>${dateLabel(d.date, this.locale)}: pumped ${withUnit(d.pumped, u)}, fed ${withUnit(d.fed, u)}</title>
        </g>`;
      })
      .join("");
    const avg = days.reduce((a, d) => a + d.pumped, 0) / days.length;
    const avgLine = avg > 0 ? `<line class="avg" x1="${padL}" x2="${W}" y1="${y(avg)}" y2="${y(avg)}"/>` : "";
    return `<svg viewBox="0 0 ${W} ${H}" style="height:${H}px" role="img" aria-label="Pumped and fed per day">
      <g class="grid">${grid}</g>${avgLine}${cols}</svg>`;
  }

  renderCard() {
    const s = this._data.summary;
    const u = this.unit;
    const days = s.history.slice(-this.range);
    const totalP = days.reduce((a, d) => a + d.pumped, 0);
    const totalF = days.reduce((a, d) => a + d.fed, 0);
    const best = days.reduce((b, d) => (d.pumped > (b?.pumped ?? -1) ? d : b), null);
    const sel = this._sel && days.find((d) => d.date === this._sel);

    let log = "";
    if (this._config.show_log !== false) {
      const entries = this._data.log;
      const limit = this._expanded ? entries.length : this._config.log_entries ?? 8;
      const shown = entries.filter((e) => !this._sel || new Date(e.ts).toLocaleDateString("en-CA") === this._sel);
      const groups = [];
      for (const e of shown.slice(0, this._sel ? shown.length : limit)) {
        const day = new Date(e.ts).toLocaleDateString("en-CA");
        let g = groups[groups.length - 1];
        if (!g || g.day !== day) groups.push((g = { day, items: [] }));
        g.items.push(e);
      }
      log = `<div class="divider"></div>
        <div class="section-title"><ha-icon icon="mdi:format-list-bulleted" style="--mdc-icon-size:16px"></ha-icon>Log${sel ? ` · ${dateLabel(this._sel, this.locale)}` : ""}</div>
        ${
          groups.length
            ? groups
                .map(
                  (g) => `<div class="day-head"><span>${dateLabel(g.day, this.locale, { weekday: "long", month: "short", day: "numeric" })}</span></div>
            <div class="list">${g.items.map((e) => MilkTrackerCard.prototype._entryRow.call(this, e)).join("")}</div>`
                )
                .join("")
            : `<div class="empty">No entries${sel ? " on this day" : " yet"}.</div>`
        }
        ${!this._sel && entries.length > (this._config.log_entries ?? 8) ? `<div class="more"><button class="ghost-btn" data-action="more">${this._expanded ? "Show less" : `Show all ${entries.length}`}</button></div>` : ""}`;
    }

    return `
      <div class="header">
        <ha-icon class="badge-icon" icon="mdi:chart-bar"></ha-icon>
        <div class="spacer"><div class="title">${esc(this._config.title || "History")}</div>
          <div class="subtitle">Last ${this.range} days</div></div>
        <div class="seg small" style="width:150px">
          ${[7, 14, 30].map((r) => `<button class="${this.range === r ? "on" : ""}" data-action="range" data-value="${r}">${r}d</button>`).join("")}
        </div>
      </div>
      <div class="summary">
        <div><div class="k">Pumped</div><div class="v" style="color:var(--mt-pump)">${withUnit(totalP, u)}</div><div class="sub">${withUnit(totalP / days.length, u)}/day</div></div>
        <div><div class="k">Fed</div><div class="v" style="color:var(--mt-feed)">${withUnit(totalF, u)}</div><div class="sub">${withUnit(totalF / days.length, u)}/day</div></div>
        <div><div class="k">Best day</div><div class="v">${best && best.pumped > 0 ? withUnit(best.pumped, u) : "–"}</div><div class="sub">${best && best.pumped > 0 ? dateLabel(best.date, this.locale) : "&nbsp;"}</div></div>
      </div>
      <div class="chart">${this._chart(days)}</div>
      <div class="legend">
        <span><i style="background:var(--mt-pump)"></i>Pumped</span>
        <span><i style="background:var(--mt-feed)"></i>Fed</span>
        <span><i style="border-top:1px dashed var(--primary-text-color);height:0;border-radius:0;opacity:.6"></i>Avg pumped</span>
      </div>
      ${
        sel
          ? `<div class="detail"><b>${dateLabel(sel.date, this.locale, { weekday: "long", month: "short", day: "numeric" })}</b>
            <span style="color:var(--mt-pump)">Pumped ${withUnit(sel.pumped, u)} · ${plural(sel.sessions, "session")}</span>
            <span style="color:var(--mt-feed)">Fed ${withUnit(sel.fed, u)} · ${plural(sel.feeds, "feed")}</span>
            ${sel.discarded ? `<span class="muted">Discarded ${withUnit(sel.discarded, u)}</span>` : ""}</div>`
          : ""
      }
      ${log}
    `;
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entry_id", selector: { config_entry: { integration: DOMAIN } } },
        { name: "title", selector: { text: {} } },
        {
          type: "grid",
          name: "",
          schema: [
            { name: "days", selector: { select: { options: ["7", "14", "30"] } } },
            { name: "show_log", selector: { boolean: {} } },
            { name: "log_entries", selector: { number: { min: 1, max: 50, mode: "box" } } },
          ],
        },
      ],
      computeLabel: (s) =>
        ({ entry_id: "Tracker (leave empty if you only have one)", title: "Title", days: "Default range (days)", show_log: "Show log", log_entries: "Log entries before 'show all'" })[s.name],
    };
  }

  setConfig(config) {
    super.setConfig({ ...config, days: config.days ? Number(config.days) : undefined });
  }
}

/* ------------------------------------------------------------------ */
/* 4. Inventory card                                                  */
/* ------------------------------------------------------------------ */

class MilkTrackerInventoryCard extends MilkTrackerBase {
  static accent = "var(--mt-fridge)";
  static logLimit = 0;

  static css = `
    .loc-head { display: flex; align-items: center; gap: 8px; margin: 4px 0 2px; }
    .loc-head .name { font-weight: 600; }
    .loc-head .sub { white-space: nowrap; }
    .loc-head .total { margin-left: auto; font-weight: 700; white-space: nowrap; }
    .item .line2 .pill { max-width: 100%; overflow: hidden; text-overflow: ellipsis; }
    .item .amt { white-space: nowrap; }
    @container (max-width: 360px) {
      .loc-head .sub, .item .bar { display: none; }
      .item .acts .icon-btn { width: 32px; height: 32px; }
      .item .amt { min-width: 0; }
    }
    @container (max-width: 250px) {
      .item { flex-wrap: wrap; row-gap: 2px; }
      .item .body { flex-basis: 100%; }
      .item .amt { text-align: left; flex: 1; }
    }
    .bar { height: 4px; border-radius: 4px; background: var(--mt-surface-2); overflow: hidden; margin-top: 4px; }
    .bar span { display: block; height: 100%; background: var(--c); }
    .item .amt { font-weight: 700; font-size: .95rem; min-width: 52px; text-align: right; }
    .item.expired .line1 { text-decoration: line-through; opacity: .7; }
    .acts { display: flex; }
    .form { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
    .actions { display: flex; gap: 8px; justify-content: flex-end; margin-top: 12px; }
    .actions .primary-btn { width: auto; min-height: 40px; padding: 8px 18px; font-size: .9rem; }
    .loc + .loc { margin-top: 14px; }
    .banner { --mdc-icon-size: 20px; display: flex; align-items: center; gap: 10px; padding: 10px 12px; border-radius: 10px;
      margin-bottom: 12px; font-size: .88rem; cursor: pointer; border: none; width: 100%; text-align: left;
      background: color-mix(in srgb, var(--mt-freezer) 14%, transparent); }
    .banner ha-icon { color: var(--mt-freezer); }
    .check { display: flex; gap: 8px; align-items: flex-start; font-size: .85rem; margin-top: 10px; cursor: pointer; }
    .check input { margin-top: 2px; accent-color: var(--mt-freezer); width: 16px; height: 16px; flex: none; }
    .hint { font-size: .85rem; color: var(--secondary-text-color); margin-bottom: 12px; }
    .seg-wrap { grid-column: 1 / -1; }
    .icon-btn.on { background: var(--mt-surface-2); color: var(--primary-text-color); }
  `;

  constructor() {
    super();
    this._editing = false;
    this._adding = false;
    this._addLoc = null;
    this._lastDate = null;
    this._bindDelegation();
  }

  static getStubConfig() {
    return {};
  }

  getGridOptions() {
    return { columns: 12, min_columns: 6, rows: "auto" };
  }

  get useFridge() {
    return this._data?.use_fridge !== false;
  }

  on_edit() {
    this._editing = !this._editing;
    this._adding = false;
    this._resetInputs = true;
    this._render();
  }
  on_add() {
    this._adding = !this._adding;
    this._editing = false;
    this._resetInputs = true;
    this._render();
    if (this._adding) this.shadowRoot.getElementById("a-amount")?.focus();
  }
  on_add_loc(el) {
    this._addLoc = el.dataset.value;
    this._render();
  }
  async on_add_save() {
    const $ = (id) => this.shadowRoot.getElementById(id);
    const amount = parseFloat($("a-amount").value);
    const date = $("a-date").value;
    if (!(amount > 0) || !date) {
      this._toast("Enter an amount and the date it was pumped");
      return;
    }
    const replace = $("a-replace") ? $("a-replace").checked : false;
    const location = this.useFridge ? this._addLoc || "freezer" : "freezer";
    const note = $("a-note")?.value.trim() || undefined;
    const res = await this._call(
      "add_stored",
      { amount, pumped_at: date, location, replace_undated: replace, note },
      { toast: `Added ${withUnit(amount, this.unit)} pumped ${dateLabel(date, this.locale)}`, undo: true }
    );
    if (res) {
      // Stay open so several bags can be entered in a row; keep the date.
      this._lastDate = date;
      const a = $("a-amount");
      if (a) {
        a.value = "";
        delete a.dataset.dirty;
        a.focus();
      }
      const n = $("a-note");
      if (n) {
        n.value = "";
        delete n.dataset.dirty;
      }
    }
  }
  async on_save() {
    const f = parseFloat(this.shadowRoot.getElementById("i-fridge")?.value);
    const z = parseFloat(this.shadowRoot.getElementById("i-freezer").value);
    const data = {};
    if (!Number.isNaN(f)) data.fridge = Math.max(0, f);
    if (!Number.isNaN(z)) data.freezer = Math.max(0, z);
    await this._call("set_stash", data, { toast: "Stash corrected", undo: true });
    this._editing = false;
    this._render();
  }
  _group(id) {
    return this._groups().find((g) => g.id === id);
  }

  /** Group batches by location + pumped day (+ thawed) so the list stays short. */
  _groups() {
    const s = this._data.summary;
    const rank = { expired: 2, expiring: 1, ok: 0 };
    const map = new Map();
    for (const b of s.batches) {
      const day = new Date(b.pumped_at).toLocaleDateString("en-CA");
      const key = `${b.location}|${b.undated ? "undated" : day}|${b.thawed_at ? "t" : ""}|${b.status}`;
      let g = map.get(key);
      if (!g) {
        g = { id: key, location: b.location, day, undated: !!b.undated, thawed: !!b.thawed_at, status: b.status, batches: [], remaining: 0, expires_at: b.expires_at, notes: new Set() };
        map.set(key, g);
      }
      g.batches.push(b);
      g.remaining += b.remaining;
      if (b.expires_at < g.expires_at) g.expires_at = b.expires_at;
      if (rank[b.status] > rank[g.status]) g.status = b.status;
      if (b.note && b.note !== "Correction" && b.note !== "Starting stash") g.notes.add(b.note);
    }
    return [...map.values()].sort((a, b) => (a.expires_at < b.expires_at ? -1 : 1));
  }

  on_move(el) {
    const g = this._group(el.dataset.id);
    if (!g) return;
    const amt = withUnit(g.remaining, this.unit);
    this._call("move", { batch_id: g.batches.map((b) => b.id) }, {
      toast: g.location === "fridge" ? `Moved ${amt} to the freezer` : `Thawed ${amt} — use within 24 h`,
      undo: true,
    });
  }
  on_discard(el) {
    const id = el.dataset.id;
    if (!this._confirmTap(`dis-${id}`)) return;
    const g = this._group(id);
    if (!g) return;
    this._call("discard", { batch_id: g.batches.map((b) => b.id) }, { toast: `Discarded ${withUnit(g.remaining, this.unit)}`, undo: true });
  }
  on_discard_expired() {
    if (!this._confirmTap("expired")) return;
    this._call("discard_expired", {}, { toast: "Expired milk discarded", undo: true });
  }
  on_toggle_loc(el) {
    this._open = { ...(this._open || {}), [el.dataset.loc]: !this._open?.[el.dataset.loc] };
    this._render();
  }

  _expiryPill(g) {
    const ms = new Date(g.expires_at) - Date.now();
    if (g.status === "expired") return `<span class="pill error">Expired</span>`;
    if (g.undated) return `<span class="pill">No pump date</span>`;
    const txt = g.thawed
      ? `Thawed · use within ${duration(ms)}`
      : ms > 14 * 86400000
        ? `Best by ${new Date(g.expires_at).toLocaleDateString(this.locale, { month: "short", day: "numeric", year: new Date(g.expires_at).getFullYear() !== new Date().getFullYear() ? "numeric" : undefined })}`
        : `Use within ${duration(ms)}`;
    return `<span class="pill ${g.status === "expiring" ? "warn" : ""}">${txt}</span>`;
  }

  renderCard() {
    const s = this._data.summary;
    const u = this.unit;
    const groups = this._groups();
    const header = `<div class="header">
      <ha-icon class="badge-icon" icon="mdi:fridge-outline"></ha-icon>
      <div class="spacer"><div class="title">${esc(this._config.title || "Inventory")}</div>
        <div class="subtitle">Oldest milk is used first</div></div>
      ${s.expired_amount > 0 ? `<button class="icon-btn ${this._confirm === "expired" ? "confirm" : ""}" data-action="discard_expired" title="${this._confirm === "expired" ? "Tap again to discard expired" : "Discard expired"}"><ha-icon icon="mdi:delete-clock-outline"></ha-icon></button>` : ""}
      <button class="icon-btn ${this._adding ? "on" : ""}" data-action="add" title="Add stored milk with its date" aria-label="Add stored milk"><ha-icon icon="${this._adding ? "mdi:close" : "mdi:calendar-plus"}"></ha-icon></button>
      <button class="icon-btn" data-action="edit" title="Correct amounts" aria-label="Correct amounts"><ha-icon icon="${this._editing ? "mdi:close" : "mdi:pencil-outline"}"></ha-icon></button>
    </div>`;
    const fridgeOn = this.useFridge;
    const undatedIn = (loc) =>
      s.batches.filter((b) => b.undated && b.location === loc).reduce((a, b) => a + b.remaining, 0);

    if (this._adding) {
      const loc = fridgeOn ? this._addLoc || "freezer" : "freezer";
      const undated = undatedIn(loc);
      const pad = (n) => String(n).padStart(2, "0");
      const t = new Date();
      const today = `${t.getFullYear()}-${pad(t.getMonth() + 1)}-${pad(t.getDate())}`;
      return `${header}
        <div class="hint">Enter bags that are already stored, with the date each was pumped, so you get accurate best-by dates. This doesn't count as pumping.</div>
        <div class="form">
          ${
            fridgeOn
              ? `<div class="seg small seg-wrap">${["freezer", "fridge"]
                  .map((l) => `<button class="${loc === l ? "on" : ""}" data-action="add_loc" data-value="${l}"><ha-icon icon="${LOC[l].icon}"></ha-icon>${LOC[l].label}</button>`)
                  .join("")}</div>`
              : ""
          }
          <label class="field">Amount (${u})<input id="a-amount" type="number" inputmode="decimal" min="0" step="${u === "ml" ? 10 : 0.5}" placeholder="e.g. ${u === "ml" ? 120 : 4}"></label>
          <label class="field">Pumped on<input id="a-date" type="date" max="${today}" value="${esc(this._lastDate || "")}"></label>
          <label class="field" style="grid-column:1/-1">Note<input id="a-note" maxlength="80" placeholder="Optional — e.g. bag #3"></label>
        </div>
        ${
          undated > 0
            ? `<label class="check"><input id="a-replace" type="checkbox" checked>
                <span>Take it from my undated milk (<b>${withUnit(undated, u)}</b> left) so the total stays the same.<br><span class="muted">Untick to add milk that isn't counted yet.</span></span></label>`
            : ""
        }
        <div class="actions"><button class="ghost-btn" data-action="add">Done</button>
          <button class="primary-btn" data-action="add_save"><ha-icon icon="mdi:plus"></ha-icon>Add bag</button></div>`;
    }

    if (this._editing) {
      return `${header}
        <div class="muted" style="font-size:.88rem;margin-bottom:12px">Counted your bags? Enter the real amounts and the tracker will adjust (oldest milk is removed first).</div>
        <div class="form">
          ${fridgeOn || s.fridge > 0 ? `<label class="field">Fridge (${u})<input id="i-fridge" type="number" inputmode="decimal" min="0" step="0.1" value="${s.fridge}"></label>` : ""}
          <label class="field">Freezer (${u})<input id="i-freezer" type="number" inputmode="decimal" min="0" step="0.1" value="${s.freezer}"></label>
        </div>
        <div class="actions"><button class="ghost-btn" data-action="edit">Cancel</button>
          <button class="primary-btn" data-action="save"><ha-icon icon="mdi:check"></ha-icon>Save</button></div>`;
    }

    const limit = this._config.max_rows ?? 5;
    const max = Math.max(1, ...groups.map((g) => g.remaining));
    const section = (loc) => {
      const all = groups.filter((g) => g.location === loc);
      const open = this._open?.[loc];
      const list = open ? all : all.slice(0, limit);
      const total = loc === "fridge" ? s.fridge : s.freezer;
      const days = loc === "fridge" ? this._data.fridge_days : this._data.freezer_days;
      return `<div class="loc c-${loc}">
        <div class="loc-head"><ha-icon class="dot" style="--mdc-icon-size:16px;width:28px;height:28px;border-radius:50%;display:grid;place-items:center" icon="${LOC[loc].icon}"></ha-icon>
          <span class="name">${LOC[loc].label}</span><span class="sub">keeps ${days >= 30 ? `${Math.round(days / 30)} months` : `${days} days`}</span>
          <span class="total">${withUnit(total, u)}</span></div>
        ${
          list.length
            ? `<div class="list">${list
                .map((g) => {
                  const conf = this._confirm === `dis-${g.id}`;
                  const n = g.batches.length;
                  return `<div class="item ${g.status}">
                    <div class="body">
                      <div class="line1">${
                        g.undated
                          ? `Undated milk <span class="sub">· added ${dateLabel(g.day, this.locale, { month: "short", day: "numeric" })}</span>`
                          : `${dateLabel(g.day, this.locale)} <span class="sub">· ${n > 1 ? plural(n, "bag") : g.batches[0].date_only ? "stored" : new Date(g.batches[0].pumped_at).toLocaleTimeString(this.locale, { hour: "numeric", minute: "2-digit" })}</span>`
                      }</div>
                      <div class="line2">${this._expiryPill(g)}${g.notes.size ? ` · ${esc([...g.notes].join(", "))}` : ""}</div>
                      <div class="bar"><span style="width:${(g.remaining / max) * 100}%"></span></div>
                    </div>
                    <div class="amt">${withUnit(g.remaining, u)}</div>
                    <div class="acts">
                      ${g.status !== "expired" && !g.thawed && fridgeOn ? `<button class="icon-btn" data-action="move" data-id="${esc(g.id)}" title="${loc === "fridge" ? "Move to freezer" : "Thaw (move to fridge)"}" aria-label="${loc === "fridge" ? "Freeze" : "Thaw"}"><ha-icon icon="${loc === "fridge" ? "mdi:snowflake" : "mdi:snowflake-melt"}"></ha-icon></button>` : ""}
                      <button class="icon-btn ${conf ? "confirm" : ""}" data-action="discard" data-id="${esc(g.id)}" title="${conf ? "Tap again to discard" : "Discard"}" aria-label="Discard"><ha-icon icon="${conf ? "mdi:check" : "mdi:delete-outline"}"></ha-icon></button>
                    </div>
                  </div>`;
                })
                .join("")}</div>
              ${all.length > limit ? `<div style="display:flex;justify-content:center;margin-top:6px"><button class="ghost-btn" data-action="toggle_loc" data-loc="${loc}">${open ? "Show less" : `Show ${all.length - limit} more`}</button></div>` : ""}`
            : `<div class="sub" style="padding:8px 0 4px 36px">Empty</div>`
        }
      </div>`;
    };

    const undatedTotal = s.undated_amount || 0;
    const banner =
      undatedTotal > 0
        ? `<button class="banner" data-action="add"><ha-icon icon="mdi:calendar-question"></ha-icon>
            <span class="spacer"><b>${withUnit(undatedTotal, u)}</b> has no pump date. Add dates bag by bag for accurate best-by dates.</span>
            <ha-icon icon="mdi:chevron-right" style="color:var(--secondary-text-color)"></ha-icon></button>`
        : "";
    const sections = fridgeOn || s.fridge > 0 ? section("fridge") + section("freezer") : section("freezer");
    return `${header}${banner}${sections}`;
  }

  static getConfigForm() {
    return {
      schema: [
        { name: "entry_id", selector: { config_entry: { integration: DOMAIN } } },
        { name: "title", selector: { text: {} } },
        { name: "max_rows", selector: { number: { min: 1, max: 30, mode: "box" } } },
      ],
      computeLabel: (s) => ({ entry_id: "Tracker (leave empty if you only have one)", title: "Title", max_rows: "Rows per location before 'show more'" })[s.name],
    };
  }
}

/* ------------------------------------------------------------------ */
/* Registration                                                       */
/* ------------------------------------------------------------------ */

const CARDS = [
  ["milk-tracker-card", MilkTrackerCard, "Milk Tracker", "Your stash at a glance with quick pump & feed logging."],
  ["milk-tracker-goal-card", MilkTrackerGoalCard, "Milk Tracker · Goal", "Progress toward a stash goal, with pace and projection."],
  ["milk-tracker-history-card", MilkTrackerHistoryCard, "Milk Tracker · History", "Daily pumped vs fed chart and the full log."],
  ["milk-tracker-inventory-card", MilkTrackerInventoryCard, "Milk Tracker · Inventory", "Fridge and freezer batches with expiry countdowns."],
];

window.customCards = window.customCards || [];
for (const [tag, cls, name, description] of CARDS) {
  if (!customElements.get(tag)) customElements.define(tag, cls);
  if (!window.customCards.some((c) => c.type === tag)) {
    window.customCards.push({ type: tag, name, description, preview: true, documentationURL: "https://github.com/highergroundstudio/HA-Milk-Tracker" });
  }
}

console.info(`%c 🍼 MILK-TRACKER %c v${VERSION} `, "background:#14b8a6;color:#fff;border-radius:3px 0 0 3px;padding:2px 4px", "background:#334155;color:#fff;border-radius:0 3px 3px 0;padding:2px 4px");
