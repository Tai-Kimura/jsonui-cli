# frozen_string_literal: true

require 'set'

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
    # `userInteractionEnabled: false` stops it as it stops a tap — on the
    # node, or on a node around it (`stopped`): the runtimes stop the long
    # press, the pan and the pinch with the tap. A binding keeps it: the gate
    # opens at run time, where the emitters gate the gesture on it.
    def long_press?(node, stopped = false)
      node.is_a?(Hash) && !stopped && !stops?(node) && node['enabled'] != false && handler?(node[LONG_PRESS_KEY])
    end

    # A node a user can operate on its own, inside a tappable. `stopped`: a
    # node around it has `userInteractionEnabled: false`, so its own tap and
    # long press are none (its type still says whether it is a control).
    def operable?(node, stopped = false)
      interactive_type?(node['type']) || (!stopped && tappable?(node)) || long_press?(node, stopped) ||
        linked_text?(node)
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

    # The handlers a stop around a node takes away with its tap: a long
    # press, a pan, a pinch (the runtimes stop them with the tap).
    GESTURE_KEYS = %w[onLongPress onPan onPinch].freeze

    # Writes SHAPE_KEY on every tappable of an include-expanded tree, and on
    # every node with a tap or a gesture inside a node that stops or gates
    # interaction, STOPPED_KEY / GATES_KEY.
    def annotate!(root)
      walk(root) do |node, stopped, gates|
        value = shape(node, stopped)
        node[SHAPE_KEY] = value if value
        next unless (TAP_KEYS + GESTURE_KEYS).any? { |key| handler?(node[key]) }

        node[STOPPED_KEY] = true if stopped
        node[GATES_KEY] = gates unless gates.empty?
      end
      root
    end

    # Layouts a node draws in a view of their own, where annotate! does not
    # reach: a Collection's cells, headers and footers, an Embed's screen, a
    # TabView tab's view. A stop around them reaches them at run time instead
    # — the stopping node hands it down (SwiftUI's environment, Compose's
    # CompositionLocal) and the drawn view's taps read it.
    COLLECTION_TYPES = %w[collection table].freeze
    REFERENCE_KEYS = %w[cell header footer].freeze
    REFERENCE_LIST_KEYS = %w[cellClasses headerClasses footerClasses].freeze

    # The names of the layouts `node` itself draws elsewhere.
    def drawn_elsewhere(node)
      return [] unless node.is_a?(Hash)

      refs = []
      type = node['type'].to_s.downcase
      if COLLECTION_TYPES.include?(type)
        ([node] + Array(node['sections']).select { |s| s.is_a?(Hash) }).each do |holder|
          REFERENCE_KEYS.each { |key| refs << holder[key] }
        end
        REFERENCE_LIST_KEYS.each do |key|
          Array(node[key]).each { |item| refs << (item.is_a?(Hash) ? item['className'] : item) }
        end
      elsif type == 'embed'
        refs << node['screen']
      elsif type == 'tabview'
        Array(node['tabs']).each { |tab| refs << tab['view'] if tab.is_a?(Hash) }
      end
      refs.select { |r| r.is_a?(String) && !r.empty? && !r.start_with?('@{') }.uniq
    end

    # Whether `node` or a node inside it draws a layout elsewhere.
    def draws_elsewhere?(node)
      return false unless node.is_a?(Hash)

      drawn_elsewhere(node).any? || children(node).any? { |c| draws_elsewhere?(c) }
    end

    # Whether `node` hands a stop down to what it draws elsewhere: its
    # `userInteractionEnabled` is false or a binding, and something inside
    # it (itself included) is drawn in a view of its own.
    def hands_stop_down?(node)
      (stops?(node) || !interaction_binding(node).nil?) && draws_elsewhere?(node)
    end

    # The layouts a stop can reach: those drawn elsewhere by a node inside
    # (or at) a node whose `userInteractionEnabled` is false or bound, in any
    # of `trees` ({ key => layout tree }), and — the whole layout being under
    # the stop — every layout those draw, and so on. The block maps a
    # reference name to a key of `trees` (the tool's screen id for it).
    def stoppable_layouts(trees, &key_of)
      key_of ||= ->(name) { name }
      reached = Set.new
      pending = []
      trees.each_value do |tree|
        walk(tree) do |node, stopped, gates|
          inside = stopped || !gates.empty? || stops?(node) || !interaction_binding(node).nil?
          drawn_elsewhere(node).each { |ref| pending << key_of.call(ref) } if inside
        end
      end
      until pending.empty?
        key = pending.shift
        next if reached.include?(key)

        reached << key
        walk(trees[key]) { |node| drawn_elsewhere(node).each { |ref| pending << key_of.call(ref) } } if trees[key]
      end
      reached
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
