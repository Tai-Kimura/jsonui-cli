# frozen_string_literal: true

module KjuiTools
  module Compose
    module Helpers
      # Both halves of a bound TextField / TextView's sync, one text for both.
      #
      # The value and the handler are the passed `data`'s, the one this composition
      # drew: a screen may hand a sheet the data its own view model holds, with the
      # sheet's view model beside it (`XGeneratedView(data = parentData, viewModel =
      # sheetVm)`). Reading `viewModel.data` there took the sheet's handler, null,
      # and the edit never reached the screen ("Email is required"; ticket
      # kjui-textfield-writeback-reads-handler-from-own-viewmodel). When data and
      # view model are one pair, the same value and the same handler are read.
      #
      # What composition holds is behind while keys are arriving, so neither half
      # takes it for what the field last said. The field remembers what it sent:
      #
      # - value -> field: a value this field sent is its own echo and is not written
      #   back. Writing it put an older value over a newer key ("spr" became "sp", and
      #   the next effect sent "sp" to the view model), a key lost with no error
      #   (ticket 2026-11-07-kjui-textfield-stale-value-overwrites-newer-key). A value
      #   it did not send is the data's word: the field takes it, and it is what the
      #   field said last.
      # - an edit is sent when it differs from what the field said last (the newest
      #   value it sent, else the data's value): "s" -> "sp" -> "s" sends the second
      #   "s" though composition may still hold the first.
      # - field -> value: after sending, wait for the value of the view model the edit
      #   was written to (`viewModel.data`, which a generated updateData has written
      #   when it returns) to differ from the edit, and write it to the field. That is
      #   the correction composition cannot see when a view model takes an edit back
      #   to what it held: "12" -> "12a" -> "12" conflates in the flow and the value
      #   never changes (ticket kjui-textfield-corrected-value-not-written-back). It
      #   waits on the value, not on time, so a correction from another thread arrives
      #   by the same road; an edit the view model took never resumes it, so the
      #   cursor and the IME are left alone. The next key restarts the effect, which
      #   cancels the wait. A screen that holds the value itself corrects through the
      #   data it passes, the first half.
      #
      # The field's changes are read from the field (snapshotFlow), not from a key
      # composition saw: "s" -> "sp" -> "s" between two compositions moves no key, and
      # an effect keyed on it had sent "sp" and was left holding it. `data` in the
      # block is the latest one passed (rememberUpdatedState), for the same reason.
      #
      # The correction goes into `sent` too: it may reach composition after a newer
      # key has arrived, and it is the field's own answer by then, not a new word.
      #
      # An earlier form read composition's value two frames after sending. Under key
      # bursts composition was still behind, and it wrote "s" over "spr".
      #
      # Spelled out in the generated code, so it needs nothing newer from KotlinJsonUI.
      module TextInputWriteBack
        # `value` is `data.<path>`. `calls` is what the edit sets off:
        # `viewModel.updateData(...)`, and the handler when there is one.
        # Returns the generated lines, not indented.
        def self.lines(state_var, value, calls, required_imports)
          required_imports&.add(:remember)
          required_imports&.add(:remember_updated_state)
          required_imports&.add(:flow_first)
          required_imports&.add(:snapshot_flow)
          required_imports&.add(:flow_collect_latest)
          path = value.delete_prefix('data.')
          sent = "#{state_var}_sent"
          passed = "#{state_var}_data"
          [
            "val #{sent} = remember { ArrayDeque<String>() }",
            "val #{passed} = rememberUpdatedState(data)",
            "LaunchedEffect(#{value}) { val held = #{value}; val echo = #{sent}.indexOf(held); " \
            "if (echo >= 0) repeat(echo + 1) { #{sent}.removeFirst() } " \
            "else if (#{state_var}.text.toString() != held) { #{sent}.clear(); #{sent}.addLast(held); " \
            "#{state_var}.edit { replace(0, length, held) } } }",
            "LaunchedEffect(#{state_var}) { snapshotFlow { #{state_var}.text.toString() }.collectLatest { newValue -> " \
            "val data = #{passed}.value; " \
            "if (newValue != (#{sent}.lastOrNull() ?: #{value})) { #{sent}.addLast(newValue); #{calls.join('; ')}; " \
            "val held = viewModel.data.first { it.#{path} != newValue }.#{path}; #{sent}.clear(); #{sent}.addLast(held); " \
            "if (#{state_var}.text.toString() == newValue) #{state_var}.edit { replace(0, length, held) } } } }"
          ]
        end
      end
    end
  end
end
