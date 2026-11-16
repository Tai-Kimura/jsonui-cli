// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    spec.json#/components/schemas/Item
// ║  Generator: jui build (api model)
// ║  Any manual edits will be OVERWRITTEN on next generation.
// ║  LLM/Agent: you MUST NOT modify this file.
// ╚══════════════════════════════════════════════════════════════════╝

import type { DeviceKind } from "./DeviceKind";
import type { InnerDto } from "./InnerDto";
import type { ItemInline } from "./ItemInline";
import type { Level } from "./Level";
import type { LoginMethod } from "./LoginMethod";
import type { Severity } from "./Severity";

export interface ItemDto {
  id: string;
  kind: DeviceKind;
  optKind?: DeviceKind;
  nullKind?: DeviceKind | null;
  defaulted?: LoginMethod;
  inline: ItemInline;
  level: Level;
  severity?: Severity;
  kinds: DeviceKind[];
  byName?: Record<string, DeviceKind>;
  inner?: InnerDto;
}

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
