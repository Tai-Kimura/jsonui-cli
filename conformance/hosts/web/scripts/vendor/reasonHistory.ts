/**
 * The reasons an auto-waiting assertion gave while it waited, in order.
 *
 * pollUntil used to keep only the last one. When the reason changed while
 * waiting — "not in the viewport" for two seconds, then "does not exist"
 * once the app's own polling removed the element — the failure named only
 * the second, and the reader went looking for an element that was never
 * rendered instead of one that was below the fold.
 *
 * The same block is written by the iOS and Android drivers; only the first
 * line of the message (the last reason, as before) is each face's own.
 */

export interface ReasonSegment {
  /** First line of the reason: the key consecutive observations fold on. */
  reason: string;
  /** Milliseconds since the poll started when this reason was first seen. */
  startMs: number;
}

/** Above this many segments the middle is elided. */
export const MAX_SEGMENTS = 8;
const HEAD = 3;
const TAIL = 4;

export class ReasonHistory {
  private readonly segments: ReasonSegment[] = [];

  /** Record one failed look. Folds into the current segment when the reason
   * is the same as the previous look's; A → B → A stays three segments. */
  observe(reason: string, atMs: number): void {
    const key = firstLine(reason);
    const current = this.segments[this.segments.length - 1];
    if (current && current.reason === key) return;
    this.segments.push({ reason: key, startMs: atMs });
  }

  get all(): readonly ReasonSegment[] {
    return this.segments;
  }

  /**
   * The message thrown at timeout: `last` unchanged, followed by the block
   * only when the reason changed while waiting. With one segment the
   * message is exactly `last` — byte for byte what pollUntil threw before.
   */
  message(last: string, endMs: number): string {
    return this.segments.length < 2 ? last : `${last}\n${renderBlock(this.segments, endMs)}`;
  }
}

/** The block under the first line. Exported for the arms. */
export function renderBlock(segments: readonly ReasonSegment[], endMs: number): string {
  const rows = segments.map((s, i) => {
    const end = i + 1 < segments.length ? segments[i + 1].startMs : endMs;
    return `    ${seconds(s.startMs)}–${seconds(end)}s  ${withoutSubject(s.reason)}`;
  });
  const shown =
    rows.length > MAX_SEGMENTS
      ? [...rows.slice(0, HEAD), `    … ${rows.length - HEAD - TAIL} more`, ...rows.slice(-TAIL)]
      : rows;
  return [`  waited ${seconds(endMs)}s; the reason changed while waiting:`, ...shown].join('\n');
}

function firstLine(reason: string): string {
  const nl = reason.indexOf('\n');
  return nl < 0 ? reason : reason.slice(0, nl);
}

/** The first line already names the element; the rows do not repeat it. */
function withoutSubject(reason: string): string {
  return reason.replace(/^Element '[^']*' /, '');
}

function seconds(ms: number): string {
  return (Math.max(0, ms) / 1000).toFixed(1);
}
