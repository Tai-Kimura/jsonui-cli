# frozen_string_literal: true

require 'set'
require_relative 'type_synonyms'

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
  # container that might hold a control is not flattened. So a tap on an
  # app's own component gets no role (shape `none`): JsonUI does not know
  # what the component holds, and a role could hide a control inside it from
  # a screen reader. The component carries its own role (4f's ruling, 1.9.0).
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

    # Asked of the type the node is drawn as (type_synonyms.rb): an HStack is
    # a View, and a Textarea a TextView. Read as written, a synonym the lists
    # do not hold counted as a custom component (operable), so the tappable
    # around it was not flattened where the same layout spelled canonically
    # was. An app's own spelling stays as written (TypeSynonyms.app_types).
    def interactive_type?(type)
      drawn = JsonUIShared::TypeSynonyms.drawn_type(type)
      INTERACTIVE_TYPES.include?(drawn) || !KNOWN_TYPES.include?(drawn)
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

    # A control: a declared interactive type that is operated where it is —
    # its value, its selection, its text, its action — not a container
    # (STOP_CONTAINER_TYPES). A stop takes its operation without a tap on it:
    # a hit-test stop keeps a touch out, and a screen reader's activation, a
    # keyboard, an accessibility service's click still reach it (measured:
    # VoiceOver switched a Switch inside `userInteractionEnabled: false`,
    # jsonui-cli 1.9.0). So annotate! marks it as it marks a tap, and the
    # codegen stops its operation and its reading as a control.
    #
    # Asked of the type the node is drawn as (TypeSynonyms.drawn_type), as
    # interactive_type? is (4f's ruling, jsonui-cli 1.9.0): a Picker is drawn
    # as a SelectBox and a SegmentedControl as a Segment — controls — and a
    # Table, a List or a RecyclerView as a Collection, a container. As
    # written, a synonym spelling was no control inside a stop while the
    # Dynamic runtimes, which ask the drawn type, stopped it. An app's own
    # component is none, whatever its spelling (TypeSynonyms.app_types): it
    # carries its own role — a spelling INTERACTIVE_TYPES lists as written
    # (Toggle, Table) is drawn as written when the app registers it.
    def control?(node)
      return false unless node.is_a?(Hash)
      return false if JsonUIShared::TypeSynonyms.app_types.include?(node['type'])

      drawn = JsonUIShared::TypeSynonyms.drawn_type(node['type'])
      INTERACTIVE_TYPES.include?(drawn) && !STOP_CONTAINER_TYPES.include?(drawn)
    end

    # The interactive types, as drawn, that hold the operated things rather
    # than being one: a stop on them reaches what they hold.
    STOP_CONTAINER_TYPES = %w[TabView ScrollView Collection Web Embed].freeze

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

    # A partialAttributes range's handler, as [:binding, value] or
    # [:selector, value], or nil. `onClick` is the canonical spelling and
    # `onclick` its alias (attribute_definitions.json, the range's `onClick`
    # `aliases`): the normalizer folds `onclick` into `onClick`, so onClick
    # holds either a binding or — folded — a method name, a selector. A raw
    # layout's `onclick` is read too, onClick first (4f ruling, jsonui-cli
    # 1.9.0; the Dynamic runtimes read the same).
    def range_handler(range)
      return nil unless range.is_a?(Hash)

      %w[onClick onclick].each do |key|
        value = range[key]
        next unless handler?(value)

        names = handler_values(value)
        return [:binding, value] if value.is_a?(String) && value.match?(/\A@\{.*\}\z/m)
        return [:selector, value] if names.none? { |v| v.start_with?('@{') }
      end
      nil
    end

    def linked_text?(node)
      return false unless TEXT_TYPES.include?(JsonUIShared::TypeSynonyms.drawn_type(node['type']))

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
    # node around it has `userInteractionEnabled: false`, so its own tap, its
    # long press and its links are none — the flag on the node itself too, for
    # the links: a stopped Label's link spans do not open (the Linkable Label
    # ticket). Its type still says whether it is a control.
    def operable?(node, stopped = false)
      interactive_type?(node['type']) || (!stopped && tappable?(node)) || long_press?(node, stopped) ||
        (!stopped && !stops?(node) && linked_text?(node))
    end

    # The children a node draws: a data-only element — `data` the only key the
    # layout wrote (a position stamp or the rule's own marks are not keys it
    # wrote; WRITTEN_STAMPS) — declares the data and draws nothing, so the
    # shapes do not count it. It was read as a child of unknown type — a
    # control — and a Label with onClick whose only child declared its data
    # was no button (4f's ruling, jsonui-cli 1.9.0).
    def drawn_children(node)
      children(node).reject { |c| data_only?(c) }
    end

    def data_only?(node)
      node.is_a?(Hash) && (node.keys - WRITTEN_STAMPS) == ['data']
    end

    # The keys the tools write on a layout node that the layout did not: the
    # position stamp (JsonUIShared::LayoutPath::KEY) and this rule's own marks.
    WRITTEN_STAMPS = ['_layoutPath', SHAPE_KEY, STOPPED_KEY, GATES_KEY].freeze

    # Something inside `node` (not itself) a user can operate on its own.
    def holds_a_control?(node, stopped = false)
      drawn_children(node).any? do |c|
        inner = stopped || stops?(c)
        operable?(c, inner) || holds_a_control?(c, inner)
      end
    end

    # The shape of one node, or nil when it is not a tappable. `stopped`: a
    # node around it has `userInteractionEnabled: false`.
    def shape(node, stopped = false)
      return nil if stopped || !tappable?(node)
      return 'none' if interactive_type?(node['type'])
      return 'button' if drawn_children(node).empty?
      return 'none' if holds_a_control?(node)

      'combine'
    end

    # The handlers a stop around a node takes away with its tap: a long
    # press, a pan, a pinch (the runtimes stop them with the tap).
    GESTURE_KEYS = %w[onLongPress onPan onPinch].freeze

    # Writes SHAPE_KEY on every tappable of an include-expanded tree, and on
    # every node with a tap or a gesture, and every control, inside a node
    # that stops or gates interaction, STOPPED_KEY / GATES_KEY — on a Label
    # with links of its own too (linked_text?): its links are taps the flag
    # stops, a range's handler and a link `linkable` detects alike, and the
    # Label may have no onClick for the keys to ride on (4f ruling, jsonui-cli 1.9.0).
    def annotate!(root)
      walk(root) do |node, stopped, gates|
        value = shape(node, stopped)
        node[SHAPE_KEY] = value if value
        next unless (TAP_KEYS + GESTURE_KEYS).any? { |key| handler?(node[key]) } || linked_text?(node) || control?(node)

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
    REFERENCE_KEYS = %w[cell header footer].freeze
    REFERENCE_LIST_KEYS = %w[cellClasses headerClasses footerClasses].freeze

    # The names of the layouts `node` itself draws elsewhere. The type is the
    # one the node is drawn as (type_synonyms.rb): a TableView, a List or a
    # RecyclerView is drawn as a Collection and draws its cells elsewhere.
    # Type names are case-sensitive, as the codegen dispatches them: a
    # lowercase `collection` is drawn as nothing and draws nothing elsewhere.
    def drawn_elsewhere(node)
      return [] unless node.is_a?(Hash)

      refs = []
      type = JsonUIShared::TypeSynonyms.drawn_type(node['type'].to_s)
      if type == 'Collection'
        ([node] + Array(node['sections']).select { |s| s.is_a?(Hash) }).each do |holder|
          REFERENCE_KEYS.each { |key| refs << holder[key] }
        end
        REFERENCE_LIST_KEYS.each do |key|
          Array(node[key]).each { |item| refs << (item.is_a?(Hash) ? item['className'] : item) }
        end
      elsif type == 'Embed'
        refs << node['screen']
      elsif type == 'TabView'
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
