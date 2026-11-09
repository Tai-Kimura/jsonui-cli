"""Android reads a seeded object back in its wire form — EXECUTED.

The Android twin of test_branch_seed_readback_wire_form.py. The seed is the
value's wire JSON; the read-back went by reflection — Kotlin property names
(`inputType`) and the Domain's `dto` — so on 2.5.17 every snake key, a
Domain's unproxied keys and a generated enum's wire name ("in_progress"
against IN_PROGRESS) were false reds. Measured: wire type with snake keys,
nested `sliders[0].min_value`, Domain with snake keys, Optional<Domain>,
[wire type] with snake keys and the generated enum, all red; scalars,
one-word keys and a Domain's proxied keys green.

Now the value goes through its own kotlinx serializer (@SerialName, the
Domain's serializer through its dto, the enum's @SerialName) and a value
with none is read by reflection as before; the failure says which.

The probe's classes are real @Serializable classes, compiled with the
serialization plugin, shaped as jui generates them. The runtime needs the
pinned jars of tests/_android_runtime.py, so this file is in no CI job;
run-suites.sh's Android leg owns it.
"""
from __future__ import annotations

import re
import subprocess

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _android_runtime as android
from tests import _toolchain as tc

_PROBE = '''package probe

import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestDispatcher
import kotlinx.serialization.KSerializer
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.descriptors.SerialDescriptor
import kotlinx.serialization.encoding.Decoder
import kotlinx.serialization.encoding.Encoder

@Serializable
data class SliderDto(val key: String? = null, @SerialName("min_value") val minValue: Int? = null)

@Serializable
data class QuestionDto(
  val text: String? = null,
  @SerialName("input_type") val inputType: String? = null,
  @SerialName("answer_key") val answerKey: String? = null,
  val sliders: List<SliderDto>? = null,
)

/** jui's Domain proxy, with its generated serializer. */
@Serializable(with = QuestionSerializer::class)
class Question(val dto: QuestionDto) {
  val text: String get() = dto.text ?: ""
}
object QuestionSerializer : KSerializer<Question> {
  private val dtoSerializer = QuestionDto.serializer()
  override val descriptor: SerialDescriptor = dtoSerializer.descriptor
  override fun serialize(encoder: Encoder, value: Question) = dtoSerializer.serialize(encoder, value.dto)
  override fun deserialize(decoder: Decoder): Question = Question(dtoSerializer.deserialize(decoder))
}

@Serializable
enum class Status(val wire: String) {
  @SerialName("in_progress") IN_PROGRESS("in_progress"),
  @SerialName("done") DONE("done");
}

/** A hand-written view-model type with no serializer. */
data class PlainQuestion(val text: String, val inputType: String)

class VM {
  val dto = QuestionDto("q", "slider", "k", listOf(SliderDto("a", 1)))
  var count = 5
  var status = Status.IN_PROGRESS
  var missing: Question? = null
  var dtoQ = dto
  var dtoList = listOf(dto)
  var domainQ = Question(dto)
  var optDomainQ: Question? = Question(dto)
  var domainList = listOf(Question(dto))
  var plainQ = PlainQuestion("q", "slider")
}

class ProbeHarness(vm: Any, dispatcher: TestDispatcher) : BaseBranchHarness(vm, dispatcher) {
  override fun setState(state: Map<String, Any?>) {}
  override fun expectTransition(destination: String) {}
  override fun resolveString(key: String): String = key
}

fun row(name: String, field: String, want: Any?) {
  val h = ProbeHarness(VM(), StandardTestDispatcher())
  try {
    seedState(h, mapOf(field to want))
    println("ROW " + name + " PASS")
  } catch (e: Throwable) {
    println("ROW " + name + " FAIL " + e.message)
  }
}

fun main() {
  val snake = mapOf("input_type" to "slider", "answer_key" to "k")
  row("scalar", "count", 5)
  row("wire-snake", "dtoQ", snake)
  row("wire-nested", "dtoQ", mapOf("sliders" to listOf(mapOf("key" to "a", "min_value" to 1))))
  row("wire-list-snake", "dtoList", listOf(snake))
  row("domain-one-word", "domainQ", mapOf("text" to "q"))
  row("domain-snake", "domainQ", snake)
  row("optional-domain", "optDomainQ", snake)
  row("domain-list", "domainList", listOf(snake))
  row("domain-wrong-value", "domainQ", mapOf("answer_key" to "other"))
  row("nil-object", "missing", snake)
  row("enum-generated", "status", "in_progress")
  row("plain-camel", "plainQ", mapOf("inputType" to "slider"))
  row("plain-snake-reflection", "plainQ", mapOf("input_type" to "slider"))
}
'''

# name -> (passes?, a word the failure must carry, or None)
_EXPECTED = {
    "scalar": (True, None),
    "wire-snake": (True, None),
    "wire-nested": (True, None),
    "wire-list-snake": (True, None),
    "domain-one-word": (True, None),
    "domain-snake": (True, None),
    "optional-domain": (True, None),
    "domain-list": (True, None),
    "domain-wrong-value": (False, "(compared in the wire form (Question's serializer))"),
    "nil-object": (False, None),
    "enum-generated": (True, None),
    "plain-camel": (True, None),
    "plain-snake-reflection": (False, "by reflection: PlainQuestion has no kotlinx serializer"),
}


@pytest.fixture(scope="module")
def rows(tmp_path_factory):
    target_cp, out = android.build(tmp_path_factory.mktemp("seed-wire-android"), bt.KOTLIN_RUNTIME, _PROBE,
                                   serializable=True)
    done = subprocess.run([str(tc.JAVA), "-cp", f"{out}:{target_cp}", "probe.ProbeKt"],
                          capture_output=True, text=True, timeout=300)
    assert done.returncode == 0, (done.stdout + done.stderr)[-3000:]
    found = {}
    for line in done.stdout.splitlines():
        m = re.match(r"^ROW (\S+) (PASS|FAIL) ?(.*)$", line)
        if m:
            found[m.group(1)] = (m.group(2) == "PASS", m.group(3))
    return found, done.stdout


def test_a_seeded_object_is_read_back_in_its_wire_form(rows):
    found, stdout = rows
    wrong = []
    for name, (passes, word) in _EXPECTED.items():
        if name not in found:
            wrong.append(f"{name}: not reported")
            continue
        ok, message = found[name]
        if ok != passes or (word and word not in message):
            wrong.append(f"{name}: passed={ok} ({message})")
    assert not wrong, "\n".join(wrong) + "\n\n" + stdout
