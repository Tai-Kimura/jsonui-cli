# frozen_string_literal: true

module KjuiTools
  module Compose
    module Helpers
      # A control written with a static value starts there, and the user
      # changes it: the value is the seed of the control's own state, as a
      # static `checked` is on the web and as sjui's codegen and both Dynamic
      # runtimes already had it (ticket
      # static-valued-controls-do-not-change-on-a-users-tap — measured: a static
      # Switch, CheckBox, Radio, Segment, Slider or SelectBox was emitted with
      # the fixed value and a `{ }` callback, and a tap did nothing).
      #
      # The state lives in a `run { }` of its own:
      #
      #   run {
      #       var seeded by remember { mutableStateOf(<seed>) }
      #       <the control, reading `seeded` and writing it on a change>
      #   }
      #
      # so the name can never meet another control's (two id-less controls of a
      # kind — sjui-codegen-state-declarations-collide-by-name), and the section
      # extractor, which lifts whole statements, never parts a control from its
      # state. A bound value is not seeded: the view model owns it.
      module StaticSeed
        STATE = 'seeded'

        # The block generates the control at the depth it is given, with the
        # state's name; the result is the control wrapped as above at `depth`.
        def self.wrap(seed_expr, depth, required_imports)
          required_imports&.add(:remember_state)
          inner = yield(depth + 1, STATE)
          pad = '    ' * depth
          "#{pad}run {\n#{pad}    var #{STATE} by remember { mutableStateOf(#{seed_expr}) }\n#{inner}\n#{pad}}"
        end
      end
    end
  end
end
