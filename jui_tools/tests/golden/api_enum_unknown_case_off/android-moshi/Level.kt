// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    spec.json#/components/schemas/Level
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
enum class Level(val wire: Int) {
    VALUE_MINUS_1(-1),
    VALUE_0(0),
    VALUE_2(2);
}

class LevelJsonAdapter : JsonAdapter<Level>() {
    override fun fromJson(reader: JsonReader): Level? {
        val wire = reader.nextInt()
        return Level.entries.firstOrNull { it.wire == wire } ?: throw JsonDataException("Level: no case for $wire at ${reader.path}")
    }

    override fun toJson(writer: JsonWriter, value: Level?) {
        writer.value(value?.wire)
    }
}

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
