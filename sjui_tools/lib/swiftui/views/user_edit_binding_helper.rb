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
      # Compose's LaunchedEffect has. The value handed over is the one the
      # edit wrote, so two quick edits are two calls with their own values.
      module UserEditBindingHelper
        # `binding` is a `$`-prefixed Binding<String> expression (`$data.x`
        # or a local `$<id>Text`). `handler_call` reads the value as
        # `newValue`. `max_length` (an Integer): the handler is handed the
        # edit cut to it — what the field keeps once maxLength's own clamp
        # (apply_max_length) has run, whichever of the two runs first.
        def user_edit_binding(binding, handler_call, max_length: nil)
          if max_length.is_a?(Integer) && max_length.positive?
            kept = "String(newValue.prefix(#{max_length}))"
            # An edit past the limit that the clamp takes back is no edit.
            changed = "#{binding}.wrappedValue != #{kept}"
            narrow = "let newValue = #{kept}; "
          else
            changed = "#{binding}.wrappedValue != newValue"
            narrow = ''
          end
          "SwiftUI.Binding(get: { #{binding}.wrappedValue }, set: { newValue in " \
            "let changed = #{changed}; " \
            "#{binding}.wrappedValue = newValue; " \
            "if changed { DispatchQueue.main.async { #{narrow}#{handler_call} } } })"
        end
      end
    end
  end
end
