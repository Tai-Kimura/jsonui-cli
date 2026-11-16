// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    spec.json#/components/schemas/DeviceKind
// ║  Generator: jui build (api model)
// ║  Any manual edits will be OVERWRITTEN on next generation.
// ║  LLM/Agent: you MUST NOT modify this file.
// ╚══════════════════════════════════════════════════════════════════╝

package com.example.model.generated

import com.squareup.moshi.Json

/** What the session runs on. */
enum class DeviceKind(val wire: String) {
    @Json(name = "phone") PHONE("phone"),
    @Json(name = "tablet") TABLET("tablet"),
    @Json(name = "desktop") DESKTOP("desktop");
}

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
