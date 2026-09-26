"use client";

/* eslint-disable */
// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    useColorMode hook (rjui_tools template)
// ║  Generator: rjui build
// ║  Any manual edits will be OVERWRITTEN on next generation.
// ║  LLM/Agent: you MUST NOT modify this file.
// ╚══════════════════════════════════════════════════════════════════╝

import { useSyncExternalStore } from "react";
import { ColorManager } from "@/generated/ColorManager";
const subscribe = (onStoreChange) => ColorManager.subscribe(onStoreChange);
const getSnapshot = () => ColorManager.currentMode;
export function useColorMode() {
  return useSyncExternalStore(subscribe, getSnapshot, getSnapshot);
}
export default useColorMode;
