import type { Locator } from 'playwright';

/**
 * `visible` / `notVisible`, `when: { visible }` and scrollUntilVisible's stop
 * condition: whether an element is in the viewport.
 *
 * In the viewport means: Playwright's isVisible() (a box, not display:none or
 * visibility:hidden), AND at least 1px each way of the element's box inside the
 * window's viewport and inside every ancestor that clips its content (overflow
 * not `visible`). Not "its centre": Android, the baseline (UiAutomator's
 * isVisibleToUser), calls a Label visible when only 5dp of it shows at the
 * bottom of a ScrollView, its centre outside (measured 2026-10-14).
 *
 * Until this, the driver asked isVisible() alone, which does not look at
 * scrolling: a Label at y 580 inside a 200px `overflow: auto` container was
 * `visible`, and scrollUntilVisible stopped before scrolling at all.
 */

/** The smallest side, in CSS px, that counts as shown (iOS: 1pt). */
export const MINIMUM_SIDE = 1;

export interface Rect {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/** `rect` cut by every clip; null when nothing of it is left. */
export function shownPart(rect: Rect, clips: Rect[]): Rect | null {
  let part: Rect = { ...rect };
  for (const clip of clips) {
    part = {
      left: Math.max(part.left, clip.left),
      top: Math.max(part.top, clip.top),
      right: Math.min(part.right, clip.right),
      bottom: Math.min(part.bottom, clip.bottom),
    };
    if (part.right <= part.left || part.bottom <= part.top) return null;
  }
  return part;
}

export function inViewport(rect: Rect, clips: Rect[]): boolean {
  const part = shownPart(rect, clips);
  return part !== null && part.right - part.left >= MINIMUM_SIDE && part.bottom - part.top >= MINIMUM_SIDE;
}

/**
 * The element's box and the rectangles that clip it, read in the page: the
 * window's viewport, and each ancestor whose overflow is not `visible`, up to
 * the first `position: fixed` element (which is positioned against the
 * viewport, not against its ancestors).
 */
export async function geometry(locator: Locator): Promise<{ rect: Rect; clips: Rect[] }> {
  return locator.evaluate((el: Element) => {
    const box = (r: DOMRect) => ({ left: r.left, top: r.top, right: r.right, bottom: r.bottom });
    const clips = [{ left: 0, top: 0, right: window.innerWidth, bottom: window.innerHeight }];
    let fixed = getComputedStyle(el).position === 'fixed';
    for (let a = el.parentElement; a && !fixed; a = a.parentElement) {
      const cs = getComputedStyle(a);
      if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible') clips.push(box(a.getBoundingClientRect()));
      if (cs.position === 'fixed') fixed = true;
    }
    return { rect: box(el.getBoundingClientRect()), clips };
  });
}

/**
 * `hidden` and `when: { hidden }`: not drawn, wherever it is. True when no
 * element matches, or none of those that do is drawn: `checkVisibility` with
 * `visibilityProperty` is false for `display: none` (JsonUI "gone"; the
 * element stays in the DOM, so `count` still finds it) and for `visibility:
 * hidden` (JsonUI "invisible" / `hidden: true`), on the element or an
 * ancestor. It does not look at the viewport, scroll containers, overlays,
 * opacity or size, so an element below the fold, under a dialog, at opacity
 * 0 or 0 x 0 is drawn and `hidden` fails on it. Measured 2026-10-15 (the
 * conformance web host, Chromium): the same answer as iOS (exists) and
 * Android's semantics tree on every shape.
 */
export async function isHidden(locator: Locator): Promise<boolean> {
  if ((await locator.count()) === 0) return true;
  return locator.evaluateAll((els: Element[]) =>
    els.every((el) => !el.checkVisibility({ visibilityProperty: true } as CheckVisibilityOptions))
  );
}

/** Whether the first element the locator matches is in the viewport. */
export async function isInViewport(locator: Locator): Promise<boolean> {
  if ((await locator.count()) === 0) return false;
  const first = locator.first();
  if (!(await first.isVisible())) return false;
  const { rect, clips } = await geometry(first);
  return inViewport(rect, clips);
}
