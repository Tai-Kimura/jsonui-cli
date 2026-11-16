// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    spec.json#/components/schemas/DeviceKind
// ║  Generator: jui build (api model)
// ║  Any manual edits will be OVERWRITTEN on next generation.
// ║  LLM/Agent: you MUST NOT modify this file.
// ╚══════════════════════════════════════════════════════════════════╝

package com.example.model.generated

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable

/** What the session runs on. */
@Serializable
enum class DeviceKind(val wire: String) {
    @SerialName("phone") PHONE("phone"),
    @SerialName("tablet") TABLET("tablet"),
    @SerialName("desktop") DESKTOP("desktop");
}

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
