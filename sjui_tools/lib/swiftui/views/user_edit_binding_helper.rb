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
      # Where the generation lives. Not in a declaration in the generated
      # view: a declaration reaches the view only through every container on
      # the way propagating its children's state, and a project's own
      # container converters (lib/swiftui/views/extensions, written from
      # older scaffolding) do not always — a TextView inside such a container
      # was emitted with a reference to a `@State` that never got declared,
      # and the consumer's build failed (measured on a consumer's chat
      # screen). Not in SwiftJsonUI either, so the generated code needs
      # nothing newer from the library than it did. It is kept in the main
      # thread's dictionary under "sjui.userEdit.<the generated view's
      # type>.<field>", an NSMutableDictionary with the number and the start.
      # Every instance of one view type shares the entry (cells of one
      # template); only edits in the same turn interact, and one turn's edits
      # come from the one focused field.
      module UserEditBindingHelper
        # The field's key in the main thread's dictionary (Swift string
        # literal with the view's type interpolated at run time).
        def user_edit_generation(base)
          "\"sjui.userEdit.\\(Self.self).#{base}\""
        end

        # `binding` is a `$`-prefixed Binding<String> expression (`$data.x`
        # or a local `$<id>Text`). `generation`: the field's
        # user_edit_generation key. `handler_call` reads the value as
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
          else
            changed = 'before != newValue'
            narrow = ''
            current = "#{binding}.wrappedValue"
            start = 'start'
          end
          "SwiftUI.Binding(get: { #{binding}.wrappedValue }, set: { newValue in " \
            "let key = #{generation}; " \
            'let edit = (Thread.main.threadDictionary[key] as? NSMutableDictionary) ?? NSMutableDictionary(); ' \
            'Thread.main.threadDictionary[key] = edit; ' \
            "let before = #{binding}.wrappedValue; " \
            "let changed = #{changed}; " \
            "#{binding}.wrappedValue = newValue; " \
            'if changed { if edit["start"] == nil { edit["start"] = before }; ' \
            'let number = (edit["number"] as? Int ?? 0) + 1; edit["number"] = number; ' \
            'DispatchQueue.main.async { guard edit["number"] as? Int == number else { return }; ' \
            "let start = edit[\"start\"] as? String; edit[\"start\"] = nil; #{narrow}" \
            "guard #{current} == newValue, newValue != #{start} else { return }; #{handler_call} } } })"
        end
      end
    end
  end
end
