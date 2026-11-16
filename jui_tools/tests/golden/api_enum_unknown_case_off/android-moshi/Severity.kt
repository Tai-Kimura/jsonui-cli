// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    spec.json#/components/schemas/Severity
// ║  Generator: jui build (api model)
// ║  Any manual edits will be OVERWRITTEN on next generation.
// ║  LLM/Agent: you MUST NOT modify this file.
// ╚══════════════════════════════════════════════════════════════════╝

package com.example.model.generated

import com.squareup.moshi.JsonAdapter
import com.squareup.moshi.JsonClass
import com.squareup.moshi.JsonDataException
import com.squareup.moshi.JsonReader
import com.squareup.moshi.JsonWriter

@JsonClass(generateAdapter = true, generator = "jui")
enum class Severity(val wire: Int) {
    LOW(1),
    HIGH(5);
}

class SeverityJsonAdapter : JsonAdapter<Severity>() {
    override fun fromJson(reader: JsonReader): Severity? {
        val wire = reader.nextInt()
        return Severity.entries.firstOrNull { it.wire == wire } ?: throw JsonDataException("Severity: no case for $wire at ${reader.path}")
    }

    override fun toJson(writer: JsonWriter, value: Severity?) {
        writer.value(value?.wire)
    }
}

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
