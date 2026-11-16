// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    spec.json#/components/schemas/Level
// ║  Generator: jui build (api model)
// ║  Any manual edits will be OVERWRITTEN on next generation.
// ║  LLM/Agent: you MUST NOT modify this file.
// ╚══════════════════════════════════════════════════════════════════╝

package com.example.model.generated

import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerializationException
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.PrimitiveKind
import kotlinx.serialization.descriptors.PrimitiveSerialDescriptor
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder

@Serializable(with = LevelSerializer::class)
enum class Level(val wire: Int) {
    VALUE_MINUS_1(-1),
    VALUE_0(0),
    VALUE_2(2);
}

object LevelSerializer : KSerializer<Level> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("com.example.model.generated.Level", PrimitiveKind.INT)

    override fun serialize(encoder: Encoder, value: Level) = encoder.encodeInt(value.wire)

    override fun deserialize(decoder: Decoder): Level {
        val wire = decoder.decodeInt()
        return Level.entries.firstOrNull { it.wire == wire } ?: throw SerializationException("Level: no case for $wire")
    }
}

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
