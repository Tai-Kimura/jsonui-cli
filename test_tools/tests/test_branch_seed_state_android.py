"""Android's harness seeds a state key into the data class only when its type
takes the value — measured by RUNNING the emitted runtime.

`BaseBranchHarness.setState` wrote each key to the view model's field and
then handed every key to the `_data` copy() by name, coerced but never
checked. A view model's state and a layout's data can share a name with
different types — a consumer's `nicknameCandidates` is `List<String>` on the
view model and the card collection drawing it in the data — so the List
reached the collection's parameter and the seed threw "argument type
mismatch" after the view model had already taken it. The consumer's harness
wrote that key itself to get past it.

Now each side takes a key only when its type takes the value, and a key
neither side took — when either has a member of that name — fails naming
the key and both types, instead of the reflection exception.

    seed                                   view model   data        outcome
    nicknameCandidates = [a, b]            [a, b]       unchanged   ok
      (List on the VM, a collection in data)
    title = "t"  (String on both)          "t"          "t"         ok (as before)
    count = 5    (data only, Long)         -            5           ok (as before)
    level = "high" (Int on VM, Boolean      -            -           fails naming
      in data)                                                       level / int /
                                                                     Boolean / String

Control: the data check taken out of this runtime — the first row throws the
consumer's "argument type mismatch" again. The runtime needs the pinned jars
of tests/_android_runtime.py, so this file is in no CI job; run-suites.sh's
Android leg owns it.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from jsonui_test_cli import branch_tests as bt
from tests import _android_runtime as android

_PROBE = '''package probe

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.TestDispatcher

/** Stands for the layout's card collection (CollectionDataSource). */
class CardSource(val items: List<Any?>)

data class ProfilingData(
  val nicknameCandidates: CardSource = CardSource(emptyList()),
  val title: String = "",
  val count: Long = 0L,
  val level: Boolean = false,
)

class ProfilingVM {
  var nicknameCandidates: List<String> = emptyList()
  var title: String = ""
  var level: Int = 0
  val _data = MutableStateFlow(ProfilingData())
}

class ProbeHarness(vm: Any, dispatcher: TestDispatcher) : BaseBranchHarness(vm, dispatcher) {
  override fun expectTransition(destination: String) {}
  override fun resolveString(key: String): String = key
}

fun main(args: Array<String>) {
  val vm = ProfilingVM()
  val h = ProbeHarness(vm, StandardTestDispatcher())
  val seed: Map<String, Any?> = when (args[0]) {
    "mismatch" -> mapOf("nicknameCandidates" to listOf("a", "b"))
    "same" -> mapOf("title" to "t")
    "dataonly" -> mapOf("count" to 5)
    else -> mapOf("level" to "high")
  }
  try {
    h.setState(seed)
    println("OUTCOME ok")
  } catch (e: Throwable) {
    val cause = generateSequence(e) { it.cause }.last()
    println("OUTCOME " + cause.javaClass.simpleName + ": " + cause.message)
  }
  val d = vm._data.value
  println("VM " + vm.nicknameCandidates.joinToString(",") + "|" + vm.title + "|" + vm.level)
  println("DATA " + d.nicknameCandidates.items.size + "|" + d.title + "|" + d.count + "|" + d.level)
}
'''


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    return android.build(tmp_path_factory.mktemp("seed-android"), bt.KOTLIN_RUNTIME, _PROBE)


def test_a_key_the_data_cannot_take_goes_to_the_view_model_only(built):
    got = android.run(built, "mismatch")
    assert got["OUTCOME"] == "ok", got
    assert got["VM"] == "a,b||0" and got["DATA"] == "0||0|false", got


def test_control_the_same_type_on_both_sides_goes_to_both(built):
    got = android.run(built, "same")
    assert got["OUTCOME"] == "ok" and got["VM"] == "|t|0" and got["DATA"] == "0|t|0|false", got


def test_control_a_key_only_the_data_declares_goes_in_as_before(built):
    got = android.run(built, "dataonly")
    assert got["OUTCOME"] == "ok" and got["DATA"] == "0||5|false", got


def test_a_key_neither_side_takes_fails_naming_both_types(built):
    got = android.run(built, "neither")
    assert got["OUTCOME"] == ("IllegalStateException: branch-harness: state 'level' could not be "
                              "written — the view model's 'level' is int, the data's is Boolean, "
                              "and the value is String"), got
    assert got["VM"] == "||0" and got["DATA"] == "0||0|false", got


def test_control_without_the_data_check_the_seed_throws_the_reported_mismatch(tmp_path):
    runtime = bt.KOTLIN_RUNTIME
    check = "      if (klass == null || accepts(klass.java, coerced, param.type.isMarkedNullable)) {\n"
    assert runtime.count(check) == 1
    built = android.build(tmp_path / "nocheck", runtime.replace(check, "      if (klass == null || true) {\n"), _PROBE)
    got = android.run(built, "mismatch")
    assert got["OUTCOME"] == "IllegalArgumentException: argument type mismatch", got
