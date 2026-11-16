// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    spec.json#/components/schemas/Item
// ║  Generator: jui build (api model)
// ║  Any manual edits will be OVERWRITTEN on next generation.
// ║  LLM/Agent: you MUST NOT modify this file.
// ╚══════════════════════════════════════════════════════════════════╝

package com.example.model.generated

import com.squareup.moshi.Json
import com.squareup.moshi.JsonClass

@JsonClass(generateAdapter = true)
data class ItemDto(
    @Json(name = "id") val id: String,
    @Json(name = "kind") val kind: DeviceKind,
    @Json(name = "optKind") val optKind: DeviceKind? = null,
    @Json(name = "nullKind") val nullKind: DeviceKind? = null,
    @Json(name = "defaulted") val defaulted: LoginMethod? = LoginMethod.APPLE_ID,
    @Json(name = "inline") val inline: ItemInline,
    @Json(name = "level") val level: Level,
    @Json(name = "severity") val severity: Severity? = null,
    @Json(name = "kinds") val kinds: List<DeviceKind>,
    @Json(name = "byName") val byName: Map<String, DeviceKind>? = null,
    @Json(name = "inner") val inner: InnerDto? = null,
)

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
