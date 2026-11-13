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
// picks a row up, it follows the finger, it passes a row when its centre goes strictly beyond that row's centre,
// a locked row is neither picked up nor passed, the list scrolls near its edges, and the release decides the move
// inside the Collection (over its header the first place, over its footer the last) and cancels it outside.
// Pointer events, not HTML5 drag and drop: the latter does not run on a phone's touch. A screen reader and a
// keyboard get a "move up" / "move down" button on every row and hear where the row went.

import React, { createContext, useContext, useEffect, useMemo, useRef, useState } from 'react';

export const JSONUI_REORDER = { band: 48, maxSpeed: 800, longPressMs: 500, slop: 8 } as const;

// ---------------------------------------------------------------- the rule (shared/core/reorder_vectors.json)

export function jsonuiReorderBounds(count: number, locked: readonly number[], start: number): [number, number] {
  let low = 0;
  let high = count - 1;
  for (const i of locked) {
    if (i < start && i + 1 > low) low = i + 1;
    if (i > start && i - 1 < high) high = i - 1;
  }
  return [low, high];
}

export function jsonuiReorderDragTo(heights: readonly number[], start: number, dy: number,
                                    locked: readonly number[] = []): number | null {
  if (locked.includes(start)) return null;
  const centres: number[] = [];
  let top = 0;
  for (const height of heights) {
    centres.push(top + height / 2);
    top += height;
  }
  const dragged = centres[start] + dy;
  let to = start;
  for (let i = start + 1; i < heights.length; i++) if (centres[i] < dragged) to += 1;
  for (let i = 0; i < start; i++) if (centres[i] > dragged) to -= 1;
  const [low, high] = jsonuiReorderBounds(heights.length, locked, start);
  return Math.max(low, Math.min(high, to));
}

export function jsonuiReorderRelease(heights: readonly number[], start: number, grabAt: number, dy: number,
                                     locked: readonly number[] = [], header = 0, footer = 0): number | null {
  const rows = heights.reduce((sum, h) => sum + h, 0);
  let top = 0;
  for (let i = 0; i < start; i++) top += heights[i];
  const finger = header + top + grabAt + dy;
  if (!(finger >= 0 && finger < header + rows + footer)) return null;
  if (locked.includes(start)) return null;
  const [low, high] = jsonuiReorderBounds(heights.length, locked, start);
  if (finger < header) return low;
  if (finger >= header + rows) return high;
  return jsonuiReorderDragTo(heights, start, dy, locked);
}

export function jsonuiReorderAutoScroll(viewport: number, fingerY: number,
                                        band: number = JSONUI_REORDER.band,
                                        maxSpeed: number = JSONUI_REORDER.maxSpeed): number {
  const topDepth = (band - fingerY) / band;
  const bottomDepth = (fingerY - (viewport - band)) / band;
  if (topDepth <= 0 && bottomDepth <= 0) return 0;
  if (topDepth >= bottomDepth) return -maxSpeed * Math.min(1, topDepth);
  return maxSpeed * Math.min(1, bottomDepth);
}

export function jsonuiReorderA11y(count: number, start: number, action: 'up' | 'down',
                                  locked: readonly number[] = []): number | null {
  if (locked.includes(start)) return null;
  const to = action === 'up' ? start - 1 : start + 1;
  const [low, high] = jsonuiReorderBounds(count, locked, start);
  return to >= low && to <= high ? to : null;
}

/** The indices of the rows whose reorderLockedProperty value is true (they are not picked up, nor passed). */
export function jsonuiReorderLocked(rows: readonly unknown[] | null | undefined, property: string): number[] {
  const out: number[] = [];
  (rows ?? []).forEach((row, i) => {
    if (row && typeof row === 'object' && (row as Record<string, unknown>)[property] === true) out.push(i);
  });
  return out;
}

// ---------------------------------------------------------------- the rows

type Words = { up: string; down: string; moved: (place: number) => string };
const EN: Words = { up: 'Move up', down: 'Move down', moved: (place) => `Moved to position ${place}` };
const JA: Words = { up: '上へ移動', down: '下へ移動', moved: (place) => `${place} 番目に移動しました` };

function useWords(): Words {
  // English while rendering on the server, the document's language once mounted (no hydration mismatch)
  const [words, setWords] = useState<Words>(EN);
  useEffect(() => {
    const lang = (document.documentElement.lang || navigator.language || '').toLowerCase();
    setWords(lang.startsWith('ja') ? JA : EN);
  }, []);
  return words;
}

const HIDDEN: React.CSSProperties = {
  position: 'absolute', width: 1, height: 1, padding: 0, margin: -1, overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)', whiteSpace: 'nowrap', border: 0,
};
// a focused move button is shown (a keyboard user sees where focus is), at the row's right edge
const SHOWN: React.CSSProperties = {
  position: 'absolute', right: 4, top: '50%', transform: 'translateY(-50%)', zIndex: 2, padding: '4px 10px',
  fontSize: 13, borderRadius: 6, border: '1px solid #888', background: '#fff', color: '#000',
};

function MoveButton({ label, onPress }: { label: string; onPress: () => void }) {
  const [focused, setFocused] = useState(false);
  return (
    <button type="button" style={focused ? SHOWN : HIDDEN} onFocus={() => setFocused(true)}
            onBlur={() => setFocused(false)} onClick={onPress}>{label}</button>
  );
}

type Section = {
  section: number;
  count: number;
  enabled: boolean;
  locked: readonly number[];
  words: Words;
  register: (index: number, el: HTMLElement | null) => void;
  pointerDown: (event: React.PointerEvent<HTMLElement>, index: number) => void;
  clickCapture: (event: React.MouseEvent<HTMLElement>) => void;
  step: (index: number, action: 'up' | 'down') => void;
};

const SectionContext = createContext<Section | null>(null);

export interface JsonuiReorderSectionProps {
  section: number;
  count: number;
  enabled?: boolean | null;
  onReorder?: ((section: number, from: number, to: number) => void) | null;
  handleId?: string;
  locked?: readonly number[];
  children?: React.ReactNode;
}

function scrollerOf(el: HTMLElement): HTMLElement {
  for (let node: HTMLElement | null = el.parentElement; node; node = node.parentElement) {
    const overflow = getComputedStyle(node).overflowY;
    if ((overflow === 'auto' || overflow === 'scroll') && node.scrollHeight > node.clientHeight) return node;
  }
  return (document.scrollingElement as HTMLElement) || document.documentElement;
}

/** One section of a reorderable Collection: its rows (JsonuiReorderItem) are dragged within it. */
export function JsonuiReorderSection(props: JsonuiReorderSectionProps) {
  const { section, count, enabled = true, onReorder, handleId, locked = [], children } = props;
  const words = useWords();
  const rows = useRef(new Map<number, HTMLElement>());
  const latest = useRef(props);
  latest.current = props;
  const [said, setSaid] = useState('');
  const suppressClickUntil = useRef(0);   // the click a drag's release makes comes within this window

  const value = useMemo<Section>(() => {
    const call = (from: number, to: number) => {
      latest.current.onReorder?.(latest.current.section, from, to);
      setSaid(words.moved(to + 1));
    };

    const pointerDown = (event: React.PointerEvent<HTMLElement>, index: number) => {
      const { enabled: on = true, count: n, locked: fixed = [], handleId: handle } = latest.current;
      if (!on || fixed.includes(index) || (event.pointerType === 'mouse' && event.button !== 0)) return;
      const found = rows.current.get(index);
      if (!found) return;
      const row: HTMLElement = found;
      if (handle) {
        const grip = (event.target as Element | null)?.closest?.(`[id="${handle.replace(/"/g, '\\"')}"]`);
        if (!grip || !row.contains(grip)) return;
      }
      const pointerId = event.pointerId;
      const x0 = event.clientX;
      const y0 = event.clientY;
      let lastY = y0;
      let active = false;
      let heights: number[] = [];
      let els: HTMLElement[] = [];
      let header = 0;
      let footer = 0;
      let grabAt = 0;
      let scroller: HTMLElement = document.documentElement;
      let scroll0 = 0;
      let frame = 0;
      let lastFrame = 0;

      const dy = () => (lastY - y0) + (scroller.scrollTop - scroll0);
      const place = () => {
        const d = dy();
        const to = jsonuiReorderDragTo(heights, index, d, fixed) ?? index;
        els.forEach((el, i) => {
          if (i === index) {
            el.style.transform = `translateY(${d}px)`;
            return;
          }
          const shift = index < i && i <= to ? -heights[index] : to <= i && i < index ? heights[index] : 0;
          el.style.transform = shift ? `translateY(${shift}px)` : '';
        });
      };
      const scrollStep = (now: number) => {
        const dt = lastFrame ? Math.min(0.05, (now - lastFrame) / 1000) : 0;
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
      const noTouchScroll = (e: TouchEvent) => { if (active) e.preventDefault(); };
      const noMenu = (e: Event) => e.preventDefault();

      const activate = () => {
        els = [];
        for (let i = 0; i < n; i++) {
          const el = rows.current.get(i);
          if (!el) return finish(false);
          els.push(el);
        }
        const rects = els.map((el) => el.getBoundingClientRect());
        heights = rects.map((r, i) => (i < rects.length - 1 ? rects[i + 1].top - r.top : r.height));
        const box = (row.closest('[data-jsonui-reorder]') as HTMLElement | null) ?? row.parentElement ?? row;
        const outer = box.getBoundingClientRect();
        header = rects[0].top - outer.top;
        footer = outer.bottom - (rects[rects.length - 1].top + heights[heights.length - 1]);
        grabAt = y0 - rects[index].top;
        scroller = scrollerOf(box);
        scroll0 = scroller.scrollTop;
        active = true;
        els.forEach((el, i) => {
          el.style.transition = i === index ? 'none' : 'transform 150ms ease';
          if (i === index) {
            el.style.zIndex = '1';
            el.style.boxShadow = '0 4px 12px rgba(0,0,0,0.18)';
          }
        });
        try { row.setPointerCapture(pointerId); } catch { /* the pointer may be gone */ }
        frame = requestAnimationFrame(scrollStep);
      };
      const timer = window.setTimeout(activate, JSONUI_REORDER.longPressMs);

      const move = (e: PointerEvent) => {
        if (e.pointerId !== pointerId) return;
        if (!active) {
          if (Math.hypot(e.clientX - x0, e.clientY - y0) > JSONUI_REORDER.slop) finish(false);
          return;
        }
        lastY = e.clientY;
        place();
      };
      const up = (e: PointerEvent) => {
        if (e.pointerId !== pointerId) return;
        if (!active) return finish(false);
        lastY = e.clientY;
        const to = jsonuiReorderRelease(heights, index, grabAt, dy(), fixed, header, footer);
        finish(true);
        if (to !== null && to !== index) call(index, to);
      };
      const cancel = (e: PointerEvent) => { if (e.pointerId === pointerId) finish(active); };
      function finish(dragged: boolean) {
        window.clearTimeout(timer);
        cancelAnimationFrame(frame);
        window.removeEventListener('pointermove', move, true);
        window.removeEventListener('pointerup', up, true);
        window.removeEventListener('pointercancel', cancel, true);
        document.removeEventListener('touchmove', noTouchScroll);
        row.removeEventListener('contextmenu', noMenu);
        els.forEach((el) => {
          el.style.transition = '';
          el.style.transform = '';
          el.style.zIndex = '';
          el.style.boxShadow = '';
        });
        try { row.releasePointerCapture(pointerId); } catch { /* not captured */ }
        active = false;
        if (dragged) suppressClickUntil.current = performance.now() + 400;
      }
      window.addEventListener('pointermove', move, true);
      window.addEventListener('pointerup', up, true);
      window.addEventListener('pointercancel', cancel, true);
      // a long press is a drag, not a scroll, a text selection or a context menu
      document.addEventListener('touchmove', noTouchScroll, { passive: false });
      row.addEventListener('contextmenu', noMenu);
    };

    const clickCapture = (event: React.MouseEvent<HTMLElement>) => {
      // a keyboard's click (detail 0: Enter / Space on a move button) is never a drag's release
      if (event.detail === 0 || performance.now() > suppressClickUntil.current) return;
      suppressClickUntil.current = 0;   // the click a drag's release makes is not the row's tap (a later one is)
      event.preventDefault();
      event.stopPropagation();
    };

    const step = (index: number, action: 'up' | 'down') => {
      const { count: n, locked: fixed = [] } = latest.current;
      const to = jsonuiReorderA11y(n, index, action, fixed);
      if (to !== null) call(index, to);
    };

    const register = (index: number, el: HTMLElement | null) => {
      if (el) rows.current.set(index, el);
      else rows.current.delete(index);
    };

    return { section, count, enabled: enabled !== false && enabled !== null, locked, words, register, pointerDown,
             clickCapture, step };
  }, [section, count, enabled, locked, words]);

  return (
    <SectionContext.Provider value={value}>
      {children}
      <span role="status" aria-live="polite" style={HIDDEN}>{said}</span>
    </SectionContext.Provider>
  );
}

/** One row of a reorderable section: long-press it (or its handle) and drag. */
export function JsonuiReorderItem({ index, children }: { index: number; children?: React.ReactNode }) {
  const ctx = useContext(SectionContext);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ctx) return;
    ctx.register(index, ref.current);
    return () => ctx.register(index, null);
  }, [ctx, index]);
  if (!ctx) return <>{children}</>;
  const up = ctx.enabled ? jsonuiReorderA11y(ctx.count, index, 'up', ctx.locked) : null;
  const down = ctx.enabled ? jsonuiReorderA11y(ctx.count, index, 'down', ctx.locked) : null;
  return (
    <div ref={ref} data-jsonui-reorder-index={index} onPointerDown={(e) => ctx.pointerDown(e, index)}
         onClickCapture={ctx.clickCapture}
         style={{ position: 'relative', WebkitTouchCallout: 'none', userSelect: ctx.enabled ? 'none' : undefined }}>
      {children}
      {up !== null && <MoveButton label={ctx.words.up} onPress={() => ctx.step(index, 'up')} />}
      {down !== null && <MoveButton label={ctx.words.down} onPress={() => ctx.step(index, 'down')} />}
    </div>
  );
}
