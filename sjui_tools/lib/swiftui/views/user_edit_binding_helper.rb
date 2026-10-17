# frozen_string_literal: true

module SjuiTools
  module SwiftUI
    module Views
      # onTextChange is the USER'S stream: it fires when the person edits the
      # field (typing, paste, the clear button) and never when the bound value
      # is changed from somewhere else — a view model's updateData, the test
      # runner's initialState. kjui codegen compares the field's text with the
      # data before calling (`if (newValue != data.x)`), KotlinJsonUI Dynamic
      # calls it from onValueChange, web from the input's onChange.
      #
      # `.onChange(of: data.x)` cannot tell the two apart — it sees every
      # change of the value, from any source — so through jsonui-cli 1.9.34
      # an iOS screen ran its "the input changed" handler for the view
      # model's own writes and for a test's initialState (ticket
      # sjui-ontextchange-fires-on-programmatic-data-change). The control
      # writes through the binding's SETTER and nothing else does, so the
      # handler is called from there (SwiftJsonUI Dynamic: UserEditBinding).
      #
      # Spelled out inline rather than through a library helper so the
      # generated code needs nothing newer from SwiftJsonUI than it did.
      #
      # The handler runs on the main queue's NEXT turn, not inside the setter.
      # A handler that narrows the value and writes it back (digits only, a
      # length cap) is the reason: written inside the setter, the stored
      # value ends the edit where it began ("12" -> "12a" -> "12"), SwiftUI
      # sees no change, and the field keeps showing "12a" while the data
      # holds "12" (measured on a consumer app's TextField, iOS 27.0, before
      # this was deferred). Deferred, the write-back is a change of its own and the
      # field follows it — the order `.onChange(of:)` had, and the order
      # Compose's LaunchedEffect has.
      #
      # A deferred call that is no longer current is dropped: when it runs,
      # it reads the binding again, and if the value there is not the one
      # this edit wrote, a later edit (or a programmatic change) came first
      # and the call is stale. jsonui-cli 1.9.35 handed every deferred call
      # its own edit's value, so a burst — the runner's `clear` sends six
      # deletes in one typeText, "strin" ... "" — queued six calls, and a
      # handler that writes the value back (`data.x = v`, the common shape)
      # put an intermediate "s" / "str" back into the field after the burst
      # and the next input landed behind it (ticket
      # sjui-ontextchange-deferred-handler-replays-stale-value). Now a burst
      # is one call with the latest value — intermediate values coalesce, as
      # under `.onChange` and LaunchedEffect.
      #
      # Comparing values alone left two holes (ticket sjui-ontextchange-
      # deferred-guard-can-double-call-or-call-without-net-change): within one
      # turn "" -> "a" -> "" -> "a" called the handler twice (the first
      # call's value matched the current one by chance), and "x" -> "xy" ->
      # "x" called it with no net change (Android compares with the data and
      # does not). So each field keeps a generation: every edit takes a new
      # number and only the last number's call runs, and the value held
      # before the burst's first edit is kept, so a burst that ends where it
      # began calls nothing — Android's `newValue != data`.
      #
      # Where the generation lives: one `@State` per field node in the
      # generated view, so each INSTANCE of the view has its own (two cells
      # of one template, two screens of one type). An earlier commit on this
      # branch (ae4ef40b) kept it in the main thread's dictionary under the
      # view's type and the field instead, and two instances edited in one turn
      # shared it: the second's edit took the number and dropped the first's
      # call (independent review, S13). The declarations do not travel the
      # usual way — up through every container — because a project's own
      # container converters (lib/swiftui/views/extensions, from older
      # scaffolding) do not always hand their children's state up, and a
      # field inside one was emitted with a `@State` that was never declared
      # (a consumer build failed). They go to the layout's conversion
      # directly (UserEditBindingHelper.collect, opened by
      # JsonToSwiftUIConverter); outside a conversion (a converter driven on
      # its own) they fall back to the converter's own state. The class is
      # declared in the view, so nothing comes from SwiftJsonUI.
      #
      # The burst's start is the value someone else last wrote: when the
      # field finds a value it did not write (the view model wrote between
      # two edits), that value becomes the start. "string" -> "stringd" ->
      # (view model) "strin" -> "string" is a change from "strin" and calls,
      # as Android's `newValue != data` does (independent review, S17).
      module UserEditBindingHelper
        # Nested in the generated view; one line, so the copies every field
        # adds fold into one declaration.
        GENERATION_CLASS =
          'private final class UserEditGeneration { var number = 0; var start: String?; var last: String? }'

        SINK = :sjui_user_edit_declarations

        # Runs the block with a sink for the generation declarations, and
        # returns them (in order, once each). Nested conversions keep their
        # own sink.
        def self.collect
          previous = Thread.current[SINK]
          Thread.current[SINK] = []
          yield
          Thread.current[SINK].uniq
        ensure
          Thread.current[SINK] = previous
        end

        # Declares this node's generation and returns its name. Named by the
        # node's position, so two nodes sharing an id still get one each.
        def user_edit_generation
          name = position_name('textEdit')
          lines = [GENERATION_CLASS, "@State private var #{name} = UserEditGeneration()"]
          if (sink = Thread.current[SINK])
            sink.concat(lines)
          else
            @state_variables ||= []
            @state_variables.concat(lines)
          end
          name
        end

        # `binding` is a `$`-prefixed Binding<String> expression (`$data.x`
        # or a local `$<id>Text`). `generation`: the node's
        # user_edit_generation. `handler_call` reads the value as
        # `newValue`. `max_length` (an Integer): the handler is handed the
        # edit cut to it — what the field keeps once maxLength's own clamp
        # (apply_max_length) has run, whichever of the two runs first.
        def user_edit_binding(binding, handler_call, generation:, max_length: nil)
          if max_length.is_a?(Integer) && max_length.positive?
            kept = "String(newValue.prefix(#{max_length}))"
            # An edit past the limit that the clamp takes back is no edit.
            changed = "before != #{kept}"
            narrow = "let newValue = #{kept}; "
            # Compared cut, too: maxLength's clamp may have run first.
            current = "String(#{binding}.wrappedValue.prefix(#{max_length}))"
            start = "start.map({ String($0.prefix(#{max_length})) })"
            # `last` is every value the field wrote that moved the storage,
            # the over-the-limit edit included: "123456" -> "1234567" is not
            # an edit (`changed` compares cut) but it IS the field's write,
            # and when the field next writes "123456" over it, that
            # "1234567" must not read as someone else's — it restarted the
            # burst from "1234567" and the call for "1234" -> "123456" was
            # lost (independent review, S18b). A write of the value already
            # stored (an echo) is not counted, so a view model's value the
            # field merely echoes still restarts the burst (S17).
            remember = ''
            remember_after = 'if before != newValue { edit.last = newValue }; '
          else
            changed = 'before != newValue'
            narrow = ''
            current = "#{binding}.wrappedValue"
            start = 'start'
            # Here `changed` is exactly "the write moved the storage".
            remember = 'edit.last = newValue; '
            remember_after = ''
          end
          "SwiftUI.Binding(get: { #{binding}.wrappedValue }, set: { newValue in " \
            "let edit = #{generation}; let before = #{binding}.wrappedValue; " \
            "let changed = #{changed}; " \
            "#{binding}.wrappedValue = newValue; " \
            "if changed { if edit.start == nil || before != edit.last { edit.start = before }; #{remember}" \
            'edit.number += 1; let number = edit.number; ' \
            'DispatchQueue.main.async { guard edit.number == number else { return }; ' \
            "let start = edit.start; edit.start = nil; #{narrow}" \
            "guard #{current} == newValue, newValue != #{start} else { return }; #{handler_call} } }" \
            "#{remember_after.empty? ? ' })' : "; #{remember_after}})"}"
        end
      end
    end
  end
end
