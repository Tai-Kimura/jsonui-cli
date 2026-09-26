# frozen_string_literal: true

module JsonUIShared
  # Whether a screen reader is told a tappable is a button — one rule for the
  # sjui and kjui codegen (the Dynamic runtimes of both libraries implement
  # the same rule, and all four run shared/core/tap_accessibility_vectors.json).
  # What counts as a handler (`handler?`) is read by the rjui codegen too.
  #
  # A tappable (onClick / onclick, not statically disabled) is a
  # `.onTapGesture` on iOS and a `.clickable` on Android, neither of which says
  # "button" by itself. Each tappable gets one shape:
  #
  #   button  — it holds no children: it becomes a button as it is
  #             (iOS `.accessibilityAddTraits(.isButton)`, Android
  #             `role = Role.Button`).
  #   combine — it holds children and nothing inside it can be operated on its
  #             own: it becomes ONE button whose name is its content (iOS
  #             `.accessibilityElement(children: .combine)` + `.isButton`, in
  #             place of the `.contain` an id would get; Android `role`).
  #   none    — its own type is a control already (Button, Switch, …), or
  #             something inside it can be operated on its own (an interactive
  #             type, or a descendant with its own tap): left as it was. On iOS
  #             neither measured shape works there — `.isButton` under
  #             `.contain` makes every child a button, and `.combine` turns the
  #             container into the control inside it (XCUITest elementType,
  #             2026-09-25). That is the silence this rule chooses.
  #
  # `userInteractionEnabled` (attribute_definitions.json common) stops the
  # node and everything in it — its own tap and gestures, and every
  # descendant's (the runtimes' hit testing / pointer blocker). The rule reads
  # it as it reads `canTap: false`, and further: `false` makes the node AND
  # every node inside it no tap — no shape, and the emitters attach no tap
  # there (a tap nothing can reach was still announced as a button, the
  # image-alt INFO included). A binding keeps the shape: the emitters gate
  # the tap and its trait on it, on the node and on every tap inside it, the
  # form they use for a bound canTap. annotate! writes both on each tap
  # inside (STOPPED_KEY, GATES_KEY); the node's own flag the emitters read
  # from the node. A control's own operation is not the rule's: a Switch
  # inside still counts as a control, its type says so.
  #
  # Which types are operable is DECLARED, per type, as `interactive` in
  # shared/core/component_metadata.json — every type states it; absence is
  # not read as "not interactive" (Button, Radio and Web declare no two-way
  # binding and are operable). INTERACTIVE_TYPES and KNOWN_TYPES below are
  # that declaration with its aliases, pinned to it by spec. A type the
  # declaration does not know (a custom component) counts as operable: a
  # container that might hold a control is not flattened.
  module TapAccessibility
    module_function

    # component_metadata.json types with `interactive: true`, and their aliases.
    INTERACTIVE_TYPES = %w[
      TextField EditText Input TextView Button Switch Toggle CheckBox Check Checkbox
      Radio SelectBox Segment Slider TabView ScrollView Collection Table TableView
      RecyclerView Web Embed
    ].freeze

    # Every component_metadata.json type, and its aliases.
    KNOWN_TYPES = (INTERACTIVE_TYPES + %w[
      Label Text Image CircleImage CircleImageView ImageView Img NetworkImage View
      SafeAreaView Progress Indicator CircleView GradientView Blur IconLabel
    ]).freeze

    TAP_KEYS = %w[onClick onclick].freeze

    # A handler is a method name that is not blank: a binding's inside
    # (`@{onOpen}`), a bare selector (`onOpen`), or each string of an
    # `onclick` array. `""`, `"   "`, `"@{}"`, `[]` and `[""]` name none, so
    # they are no tap — every codegen and both runtimes read handlers through
    # this, and the calls drop the blank elements of an array. (The codegens
    # used to emit `data.?.invoke()` / `data.?()` / `data.` for them: output
    # that does not compile.)
    def names_a_method?(value)
      return false unless value.is_a?(String)

      # Blank is Unicode white space (a full-width space too), as the Swift and
      # Kotlin copies read it.
      inner = value[/\A@\{(.*)\}\z/m, 1] || value
      !inner.match?(/\A[[:space:]]*\z/)
    end

    # The elements of a handler value that name a method, in the order written.
    def handler_values(value)
      (value.is_a?(Array) ? value : [value]).select { |v| names_a_method?(v) }
    end

    def handler?(value)
      handler_values(value).any?
    end

    # Operable inside a tappable even when its type is not: a long press (a
    # screen-reader action — image_accessibility.rb counts it too), and a
    # Label that carries links of its own (`linkable`, or a partialAttributes
    # range with its own tap). A tappable holding one is not flattened. A
    # tappable whose only handler is a long press is not a tap here: there is
    # nothing to call a button. `canTap` without onClick is not a tap either —
    # it has no handler (both runtimes require onClick; see the canTap ticket).
    LONG_PRESS_KEY = 'onLongPress'
    TEXT_TYPES = %w[Label Text].freeze

    SHAPE_KEY = '_tapShape'

    # On a tap inside a node with `userInteractionEnabled: false`: true.
    STOPPED_KEY = '_tapStopped'

    # On a tap inside nodes with a bound `userInteractionEnabled`: their
    # bindings, outermost first — the gates its tap and trait follow.
    GATES_KEY = '_tapGates'

    INTERACTION_KEY = 'userInteractionEnabled'

    def interactive_type?(type)
      INTERACTIVE_TYPES.include?(type) || !KNOWN_TYPES.include?(type)
    end

    # A tap the codegen emits: a handler, not statically disabled, and not
    # gated shut — `canTap: false` is the SwiftUI / Compose tap gate
    # (attribute_definitions.json common.canTap), so the tap is not there, and
    # `userInteractionEnabled: false` stops the node. Of the node alone: a
    # node inside one that stops is no tap either (`shape`'s `stopped`).
    def tappable?(node)
      node.is_a?(Hash) && node['enabled'] != false && node['canTap'] != false &&
        !stops?(node) && TAP_KEYS.any? { |key| handler?(node[key]) }
    end

    # `userInteractionEnabled: false`: the node and everything in it take no
    # interaction.
    def stops?(node)
      node.is_a?(Hash) && node[INTERACTION_KEY] == false
    end

    # A bound `userInteractionEnabled` (`@{…}`), or nil.
    def interaction_binding(node)
      value = node.is_a?(Hash) ? node[INTERACTION_KEY] : nil
      value.is_a?(String) && value.start_with?('@{') && value.end_with?('}') ? value : nil
    end

    # Whether the tap of `node` is stopped: by its own `userInteractionEnabled:
    # false`, or by a node around it (STOPPED_KEY, which annotate! writes).
    def stopped?(node)
      stops?(node) || (node.is_a?(Hash) && node[STOPPED_KEY] == true)
    end

    # The bound `userInteractionEnabled` values that gate the tap of `node`:
    # those of the nodes around it (GATES_KEY), then its own — each once.
    def interaction_gates(node)
      return [] unless node.is_a?(Hash)

      around = node[GATES_KEY].is_a?(Array) ? node[GATES_KEY] : []
      (around + [interaction_binding(node)].compact).uniq
    end

    def children(node)
      %w[child children].flat_map do |key|
        value = node[key]
        case value
        when Array then value.select { |c| c.is_a?(Hash) }
        when Hash then [value]
        else []
        end
      end
    end

    def present?(value)
      !value.nil? && !(value.respond_to?(:empty?) && value.empty?)
    end

    def linked_text?(node)
      return false unless TEXT_TYPES.include?(node['type'])

      linkable = node['linkable']
      return true if linkable == true || (linkable.is_a?(String) && linkable.start_with?('@{'))

      Array(node['partialAttributes']).any? do |range|
        range.is_a?(Hash) && TAP_KEYS.any? { |key| handler?(range[key]) }
      end
    end

    # A long press a user can perform: a handler, on a view not statically
    # disabled. `canTap` gates the tap, not the long press. A handler is what
    # `handler?` says it is — an empty or blank value names no method, here as
    # for a tap (this read "any value" before: a blank long press counted).
    def long_press?(node)
      node.is_a?(Hash) && node['enabled'] != false && handler?(node[LONG_PRESS_KEY])
    end

    # A node a user can operate on its own, inside a tappable. `stopped`: a
    # node around it has `userInteractionEnabled: false`, so its own tap is
    # none (its type still says whether it is a control) — and so are its
    # links: a Label's links stop with it (the emitters make them no links,
    # jsonui-cli 1.9.0), so they do not count. `stopped` counts the node's
    # own flag where holds_a_control? passes it.
    def operable?(node, stopped = false)
      interactive_type?(node['type']) || (!stopped && tappable?(node)) || long_press?(node) ||
        (!stopped && linked_text?(node))
    end

    # Something inside `node` (not itself) a user can operate on its own.
    def holds_a_control?(node, stopped = false)
      children(node).any? do |c|
        inner = stopped || stops?(c)
        operable?(c, inner) || holds_a_control?(c, inner)
      end
    end

    # The shape of one node, or nil when it is not a tappable. `stopped`: a
    # node around it has `userInteractionEnabled: false`.
    def shape(node, stopped = false)
      return nil if stopped || !tappable?(node)
      return 'none' if interactive_type?(node['type'])
      return 'button' if children(node).empty?
      return 'none' if holds_a_control?(node)

      'combine'
    end

    # Writes SHAPE_KEY on every tappable of an include-expanded tree, and on
    # every tap inside a node that stops or gates interaction, STOPPED_KEY /
    # GATES_KEY — on a Label with links of its own too (linked_text?): its
    # links are taps the flag stops, a range's handler and a link `linkable`
    # detects alike, and the Label may have no onClick for the keys to ride
    # on (4f ruling, jsonui-cli 1.9.0).
    def annotate!(root)
      walk(root) do |node, stopped, gates|
        value = shape(node, stopped)
        node[SHAPE_KEY] = value if value
        next unless TAP_KEYS.any? { |key| handler?(node[key]) } || linked_text?(node)

        node[STOPPED_KEY] = true if stopped
        node[GATES_KEY] = gates unless gates.empty?
      end
      root
    end

    # Yields each node with what the nodes around it (not itself) say:
    # whether one has `userInteractionEnabled: false`, and the bound values,
    # outermost first.
    def walk(node, stopped = false, gates = [], &block)
      return unless node.is_a?(Hash)

      yield node, stopped, gates
      inner_stopped = stopped || stops?(node)
      own = interaction_binding(node)
      inner_gates = own && !gates.include?(own) ? gates + [own] : gates
      children(node).each { |c| walk(c, inner_stopped, inner_gates, &block) }
    end
  end
end
