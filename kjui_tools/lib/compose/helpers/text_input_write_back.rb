# frozen_string_literal: true

module KjuiTools
  module Compose
    module Helpers
      # The state -> data half of a bound TextField / TextView, one text for both.
      #
      # The write-back keyed on the value does not run when a view model takes an
      # edit back to the value it held ("12" -> "12a" -> "12"): the flow conflates
      # the raw edit and the correction, composition never sees a different value,
      # and the field keeps "12a" while the data holds "12" (ticket
      # kjui-textfield-corrected-value-not-written-back). So the effect reads the
      # value again once composition has caught up with its writes. Read at once, the
      # value is still the old one and every key is taken back (measured: the cursor
      # and the composing region lost in 15 rows of 80). One frame was enough in every
      # row measured; the second is margin, not a measured need. A frame is the
      # composition's own step, not a length of time.
      #
      # A later edit restarts the effect, which cancels the wait. The field is only
      # written when the data differs from the edit, so an edit the view model took
      # leaves the cursor and the IME's composing region alone.
      #
      # Spelled out in the generated code, so it needs nothing newer from
      # KotlinJsonUI. KotlinJsonUI Dynamic's own form: TextFieldFollowsHeldValue.
      module TextInputWriteBack
        # `calls` is what the edit sets off: `viewModel.updateData(...)`, and the
        # handler when there is one. Returns the generated lines, not indented.
        def self.lines(state_var, value, calls, required_imports)
          required_imports&.add(:remember_updated_state)
          required_imports&.add(:with_frame_nanos)
          held = "#{state_var}_held"
          [
            "val #{held} = rememberUpdatedState(#{value})",
            "LaunchedEffect(#{state_var}.text) { val newValue = #{state_var}.text.toString(); " \
            "if (newValue != #{value}) { #{calls.join('; ')}; withFrameNanos { }; withFrameNanos { }; " \
            "if (#{state_var}.text.toString() == newValue && #{held}.value != newValue) " \
            "#{state_var}.edit { replace(0, length, #{held}.value) } } }"
          ]
        end
      end
    end
  end
end
