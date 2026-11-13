"use client";

/* eslint-disable */
// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    reorder helper (rjui_tools template)
// ║  Generator: rjui build
// ║  Any manual edits will be OVERWRITTEN on next generation.
// ║  LLM/Agent: you MUST NOT modify this file.
// ╚══════════════════════════════════════════════════════════════════╝

// A reorderable Collection's rows on the web (ticket jui-collection-drag-to-reorder, ruling B 2026-11-13).
// The rule is shared/core/reorder_vectors.json, the same one SwiftJsonUI and KotlinJsonUI drag by: a long press
// picks a row up, it follows the finger, it passes a row when its centre goes strictly beyond that row's edge (the
// row's top below it, its bottom above it — the gap stays under the dragged centre, as iOS 27's standard draws it),
// a locked row is neither picked up nor passed, a fixed row (reorderFixedProperty, or a row whose handle is not
// drawn) is not picked up but is passed, the list scrolls near its edges, and the release decides the move
// inside the Collection (over its header the first place, over its footer the last) and cancels it outside.
// Pointer events, not HTML5 drag and drop: the latter does not run on a phone's touch. A screen reader and a
// keyboard get a "move up" / "move down" button on every row that can move and hear where the row went, in the
// app's words when its strings.json has jsonui.reorder_move_up / reorder_move_down / reorder_moved_to, else in
// Japanese or English.

import { createContext, useContext, useEffect, useMemo, useRef, useState } from "react";
export const JSONUI_REORDER = { band: 48, maxSpeed: 800, longPressMs: 500, slop: 8 };
export function jsonuiReorderBounds(count, locked, start) {
  let low = 0;
  let high = count - 1;
  for (const i of locked) {
    if (i < start && i + 1 > low) low = i + 1;
    if (i > start && i - 1 < high) high = i - 1;
  }
  return [low, high];
}
export function jsonuiReorderDragTo(heights, start, dy, locked = [], fixed = []) {
  if (locked.includes(start) || fixed.includes(start)) return null;
  const tops = [];
  let top = 0;
  for (const height of heights) {
    tops.push(top);
    top += height;
  }
  const dragged = tops[start] + heights[start] / 2 + dy;
  let to = start;
  for (let i = start + 1; i < heights.length; i++) if (tops[i] < dragged) to += 1;
  for (let i = 0; i < start; i++) if (tops[i] + heights[i] > dragged) to -= 1;
  const [low, high] = jsonuiReorderBounds(heights.length, locked, start);
  return Math.max(low, Math.min(high, to));
}
export function jsonuiReorderRelease(heights, start, grabAt, dy, locked = [], header = 0, footer = 0, fixed = []) {
  const rows = heights.reduce((sum, h) => sum + h, 0);
  let top = 0;
  for (let i = 0; i < start; i++) top += heights[i];
  const finger = header + top + grabAt + dy;
  if (!(finger >= 0 && finger < header + rows + footer)) return null;
  if (locked.includes(start) || fixed.includes(start)) return null;
  const [low, high] = jsonuiReorderBounds(heights.length, locked, start);
  if (finger < header) return low;
  if (finger >= header + rows) return high;
  return jsonuiReorderDragTo(heights, start, dy, locked);
}
export function jsonuiReorderAutoScroll(viewport, fingerY, band = JSONUI_REORDER.band, maxSpeed = JSONUI_REORDER.maxSpeed) {
  const topDepth = (band - fingerY) / band;
  const bottomDepth = (fingerY - (viewport - band)) / band;
  if (topDepth <= 0 && bottomDepth <= 0) return 0;
  if (topDepth >= bottomDepth) return -maxSpeed * Math.min(1, topDepth);
  return maxSpeed * Math.min(1, bottomDepth);
}
export function jsonuiReorderA11y(count, start, action, locked = [], fixed = []) {
  if (locked.includes(start) || fixed.includes(start)) return null;
  const to = action === "up" ? start - 1 : start + 1;
  const [low, high] = jsonuiReorderBounds(count, locked, start);
  return to >= low && to <= high ? to : null;
}
export function jsonuiReorderItemsChanged(start, now) {
  const same = (a, b) => {
    const x = [...a].sort((p, q) => p - q);
    const y = [...b].sort((p, q) => p - q);
    return x.length === y.length && x.every((v, i) => v === y[i]);
  };
  return start.ids.length !== now.ids.length || start.ids.some((id, i) => id !== now.ids[i]) || !same(start.locked, now.locked) || !same(start.fixed, now.fixed);
}
function jsonuiHandleDrawn(row, handleId) {
  const grip = row?.querySelector(`[id="${handleId.replace(/"/g, '\\"')}"]`);
  return !!grip && grip.getClientRects().length > 0 && getComputedStyle(grip).visibility !== "hidden";
}
export function jsonuiReorderLocked(rows, property) {
  const out = [];
  (rows ?? []).forEach((row, i) => {
    if (row && typeof row === "object" && row[property] === true) out.push(i);
  });
  return out;
}
const EN = { up: "Move up", down: "Move down", moved: (place) => `Moved to position ${place}` };
const JA = { up: "上へ移動", down: "下へ移動", moved: (place) => `${place} 番目に移動しました` };
function appWord(key) {
  const strings = globalThis.__jsonuiStrings;
  const value = strings?.getString(key);
  return value && value !== key ? value : void 0;
}
export function jsonuiReorderWords() {
  const strings = globalThis.__jsonuiStrings;
  const lang = (strings?.language || document.documentElement.lang || navigator.language || "").toLowerCase();
  const ours = lang.startsWith("ja") ? JA : EN;
  const up = appWord("jsonui_reorder_move_up");
  const down = appWord("jsonui_reorder_move_down");
  const moved = appWord("jsonui_reorder_moved_to");
  return {
    up: up ?? ours.up,
    down: down ?? ours.down,
    moved: moved ? (place) => moved.replace(/\{count\}/g, String(place)) : ours.moved
  };
}
function useWords() {
  const [words, setWords] = useState(EN);
  useEffect(() => {
    const update = () => setWords(jsonuiReorderWords());
    update();
    window.addEventListener("jsonui:languagechange", update);
    return () => window.removeEventListener("jsonui:languagechange", update);
  }, []);
  return words;
}
const HIDDEN = {
  position: "absolute",
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: "hidden",
  clip: "rect(0, 0, 0, 0)",
  whiteSpace: "nowrap",
  border: 0
};
const SHOWN = {
  position: "absolute",
  right: 4,
  top: "50%",
  transform: "translateY(-50%)",
  zIndex: 2,
  padding: "4px 10px",
  fontSize: 13,
  borderRadius: 6,
  border: "1px solid #888",
  background: "#fff",
  color: "#000"
};
function MoveButton({ label, onPress }) {
  const [focused, setFocused] = useState(false);
  return <button
    type="button"
    style={focused ? SHOWN : HIDDEN}
    onFocus={() => setFocused(true)}
    onBlur={() => setFocused(false)}
    onClick={onPress}
  >{label}</button>;
}
const SectionContext = createContext(null);
function scrollerOf(el) {
  for (let node = el.parentElement; node; node = node.parentElement) {
    const overflow = getComputedStyle(node).overflowY;
    if ((overflow === "auto" || overflow === "scroll") && node.scrollHeight > node.clientHeight) return node;
  }
  return document.scrollingElement || document.documentElement;
}
export function JsonuiReorderSection(props) {
  const { section, count, enabled = true, onReorder, handleId, locked = [], fixed = [], children } = props;
  const words = useWords();
  const rows = useRef(/* @__PURE__ */ new Map());
  const latest = useRef(props);
  latest.current = props;
  const [said, setSaid] = useState("");
  const suppressClickUntil = useRef(0);
  const value = useMemo(() => {
    const call = (from, to) => {
      latest.current.onReorder?.(latest.current.section, from, to);
      setSaid(words.moved(to + 1));
    };
    const begin = (index) => latest.current.onReorderStart?.(latest.current.section, index);
    const over = () => latest.current.onReorderEnd?.(latest.current.section);
    const pointerDown = (event, index) => {
      const { enabled: on = true, count: n, locked: fixed2 = [], fixed: still = [], handleId: handle } = latest.current;
      if (!on || fixed2.includes(index) || still.includes(index) || event.pointerType === "mouse" && event.button !== 0) return;
      const found = rows.current.get(index);
      if (!found) return;
      const row = found;
      if (handle) {
        const grip = event.target?.closest?.(`[id="${handle.replace(/"/g, '\\"')}"]`);
        if (!grip || !row.contains(grip)) return;
      }
      const pointerId = event.pointerId;
      const x0 = event.clientX;
      const y0 = event.clientY;
      let lastY = y0;
      let active = false;
      let heights = [];
      let els = [];
      let header = 0;
      let footer = 0;
      let grabAt = 0;
      let scroller = document.documentElement;
      let started = null;
      let begun = false;
      const end = () => {
        if (begun) {
          begun = false;
          over();
        }
      };
      const rowsNow = () => {
        const { count: c, locked: l = [], fixed: f = [], handleId: h } = latest.current;
        const ids = [];
        for (let i = 0; i < c; i++) {
          const el = rows.current.get(i);
          if (el) ids.push(el);
        }
        const still2 = h ? [...f, ...ids.map((el, i) => jsonuiHandleDrawn(el, h) ? -1 : i).filter((i) => i >= 0)] : [...f];
        return { ids, locked: [...l], fixed: [...new Set(still2)] };
      };
      let scroll0 = 0;
      let frame = 0;
      let lastFrame = 0;
      const dy = () => lastY - y0 + (scroller.scrollTop - scroll0);
      const place = () => {
        const d = dy();
        const to = jsonuiReorderDragTo(heights, index, d, fixed2) ?? index;
        els.forEach((el, i) => {
          if (i === index) {
            el.style.transform = `translateY(${d}px)`;
            return;
          }
          const shift = index < i && i <= to ? -heights[index] : to <= i && i < index ? heights[index] : 0;
          el.style.transform = shift ? `translateY(${shift}px)` : "";
        });
      };
      const scrollStep = (now) => {
        const dt = lastFrame ? Math.min(0.05, (now - lastFrame) / 1e3) : 0;
        lastFrame = now;
        const page = scroller === document.scrollingElement || scroller === document.documentElement;
        const top = page ? 0 : scroller.getBoundingClientRect().top;
        const viewport = page ? window.innerHeight : scroller.clientHeight;
        const speed = jsonuiReorderAutoScroll(viewport, lastY - top);
        if (speed && dt) {
          scroller.scrollTop += speed * dt;
          place();
        }
        frame = requestAnimationFrame(scrollStep);
      };
      const noTouchScroll = (e) => {
        if (active) e.preventDefault();
      };
      const noMenu = (e) => e.preventDefault();
      const activate = () => {
        els = [];
        for (let i = 0; i < n; i++) {
          const el = rows.current.get(i);
          if (!el) return finish(false);
          els.push(el);
        }
        const rects = els.map((el) => el.getBoundingClientRect());
        heights = rects.map((r, i) => i < rects.length - 1 ? rects[i + 1].top - r.top : r.height);
        const box = row.closest("[data-jsonui-reorder]") ?? row.parentElement ?? row;
        const outer = box.getBoundingClientRect();
        header = rects[0].top - outer.top;
        footer = outer.bottom - (rects[rects.length - 1].top + heights[heights.length - 1]);
        grabAt = y0 - rects[index].top;
        scroller = scrollerOf(box);
        scroll0 = scroller.scrollTop;
        started = rowsNow();
        active = true;
        begun = true;
        begin(index);
        els.forEach((el, i) => {
          el.style.transition = i === index ? "none" : "transform 150ms ease";
          if (i === index) {
            el.style.zIndex = "1";
            el.style.boxShadow = "0 4px 12px rgba(0,0,0,0.18)";
          }
        });
        try {
          row.setPointerCapture(pointerId);
        } catch {
        }
        frame = requestAnimationFrame(scrollStep);
      };
      const timer = window.setTimeout(activate, JSONUI_REORDER.longPressMs);
      const move = (e) => {
        if (e.pointerId !== pointerId) return;
        if (!active) {
          if (Math.hypot(e.clientX - x0, e.clientY - y0) > JSONUI_REORDER.slop) finish(false);
          return;
        }
        lastY = e.clientY;
        place();
      };
      const up = (e) => {
        if (e.pointerId !== pointerId) return;
        if (!active) return finish(false);
        lastY = e.clientY;
        const to = jsonuiReorderRelease(heights, index, grabAt, dy(), fixed2, header, footer);
        const changed = started !== null && jsonuiReorderItemsChanged(started, rowsNow());
        finish(true);
        if (!changed && to !== null && to !== index) call(index, to);
        end();
      };
      const cancel = (e) => {
        if (e.pointerId === pointerId) {
          finish(active);
          end();
        }
      };
      function finish(dragged) {
        window.clearTimeout(timer);
        cancelAnimationFrame(frame);
        window.removeEventListener("pointermove", move, true);
        window.removeEventListener("pointerup", up, true);
        window.removeEventListener("pointercancel", cancel, true);
        document.removeEventListener("touchmove", noTouchScroll);
        row.removeEventListener("contextmenu", noMenu);
        els.forEach((el) => {
          el.style.transition = "";
          el.style.transform = "";
          el.style.zIndex = "";
          el.style.boxShadow = "";
        });
        try {
          row.releasePointerCapture(pointerId);
        } catch {
        }
        active = false;
        if (dragged) suppressClickUntil.current = performance.now() + 400;
      }
      window.addEventListener("pointermove", move, true);
      window.addEventListener("pointerup", up, true);
      window.addEventListener("pointercancel", cancel, true);
      document.addEventListener("touchmove", noTouchScroll, { passive: false });
      row.addEventListener("contextmenu", noMenu);
    };
    const clickCapture = (event) => {
      if (event.detail === 0 || performance.now() > suppressClickUntil.current) return;
      suppressClickUntil.current = 0;
      event.preventDefault();
      event.stopPropagation();
    };
    const step = (index, action) => {
      const { count: n, locked: fixed2 = [], fixed: still = [] } = latest.current;
      const to = jsonuiReorderA11y(n, index, action, fixed2, still);
      if (to !== null) {
        begin(index);
        call(index, to);
        over();
      }
    };
    const register = (index, el) => {
      if (el) rows.current.set(index, el);
      else rows.current.delete(index);
    };
    return {
      section,
      count,
      enabled: enabled !== false && enabled !== null,
      locked,
      fixed,
      handleId,
      words,
      register,
      pointerDown,
      clickCapture,
      step
    };
  }, [section, count, enabled, locked, fixed, handleId, words]);
  return <SectionContext.Provider value={value}>
      {children}
      <span role="status" aria-live="polite" style={HIDDEN}>{said}</span>
    </SectionContext.Provider>;
}
export function JsonuiReorderItem({ index, children }) {
  const ctx = useContext(SectionContext);
  const ref = useRef(null);
  const [handleDrawn, setHandleDrawn] = useState(true);
  useEffect(() => {
    if (!ctx) return;
    ctx.register(index, ref.current);
    return () => ctx.register(index, null);
  }, [ctx, index]);
  useEffect(() => {
    if (!ctx?.handleId || !ref.current) return;
    const drawn = jsonuiHandleDrawn(ref.current, ctx.handleId);
    if (drawn !== handleDrawn) setHandleDrawn(drawn);
  });
  if (!ctx) return <>{children}</>;
  const still = ctx.handleId && !handleDrawn ? [...ctx.fixed, index] : ctx.fixed;
  const up = ctx.enabled ? jsonuiReorderA11y(ctx.count, index, "up", ctx.locked, still) : null;
  const down = ctx.enabled ? jsonuiReorderA11y(ctx.count, index, "down", ctx.locked, still) : null;
  return <div
    ref={ref}
    data-jsonui-reorder-index={index}
    onPointerDown={(e) => ctx.pointerDown(e, index)}
    onClickCapture={ctx.clickCapture}
    style={{ position: "relative", WebkitTouchCallout: "none", userSelect: ctx.enabled ? "none" : void 0 }}
  >
      {children}
      {up !== null && <MoveButton label={ctx.words.up} onPress={() => ctx.step(index, "up")} />}
      {down !== null && <MoveButton label={ctx.words.down} onPress={() => ctx.step(index, "down")} />}
    </div>;
}

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
