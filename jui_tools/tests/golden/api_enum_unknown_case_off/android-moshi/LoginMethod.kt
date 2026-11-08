// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    spec.json#/components/schemas/LoginMethod
// ║  Generator: jui build (api model)
// ║  Any manual edits will be OVERWRITTEN on next generation.
// ║  LLM/Agent: you MUST NOT modify this file.
// ╚══════════════════════════════════════════════════════════════════╝

package com.example.model.generated

import com.squareup.moshi.Json

enum class LoginMethod(val wire: String) {
    @Json(name = "email_link") EMAIL_LINK("email_link"),
    @Json(name = "apple-id") APPLE_ID("apple-id"),
    @Json(name = "Google") GOOGLE("Google");
}

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
