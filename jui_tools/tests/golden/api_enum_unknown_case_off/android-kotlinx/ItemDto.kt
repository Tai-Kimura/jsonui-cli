// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    spec.json#/components/schemas/Item
// ║  Generator: jui build (api model)
// ║  Any manual edits will be OVERWRITTEN on next generation.
// ║  LLM/Agent: you MUST NOT modify this file.
// ╚══════════════════════════════════════════════════════════════════╝

package com.example.model.generated

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

@Serializable
data class ItemDto(
    val id: String,
    val kind: DeviceKind,
    val optKind: DeviceKind? = null,
    val nullKind: DeviceKind? = null,
    val defaulted: LoginMethod? = LoginMethod.APPLE_ID,
    val inline: ItemInline,
    val level: Level,
    val severity: Severity? = null,
    val kinds: List<DeviceKind>,
    val byName: Map<String, DeviceKind>? = null,
    val inner: InnerDto? = null,
)

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
