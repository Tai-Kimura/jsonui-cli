// ╔══════════════════════════════════════════════════════════════════╗
// ║  @generated AUTO-GENERATED FILE — DO NOT EDIT
// ║  Source:    spec.json#/components/schemas/Severity
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

@Serializable(with = SeveritySerializer::class)
enum class Severity(val wire: Int) {
    LOW(1),
    HIGH(5);
}

object SeveritySerializer : KSerializer<Severity> {
    override val descriptor: SerialDescriptor = PrimitiveSerialDescriptor("com.example.model.generated.Severity", PrimitiveKind.INT)

    override fun serialize(encoder: Encoder, value: Severity) = encoder.encodeInt(value.wire)

    override fun deserialize(decoder: Decoder): Severity {
        val wire = decoder.decodeInt()
        return Severity.entries.firstOrNull { it.wire == wire } ?: throw SerializationException("Severity: no case for $wire")
    }
}

// ══ END AUTO-GENERATED — DO NOT APPEND BELOW THIS LINE ══
