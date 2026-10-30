# frozen_string_literal: true

require_relative '../core/responsive_resolver'
require_relative 'tailwind_mapper'
require_relative '../core/enum_spelling'
require_relative '../core/type_synonyms'
require_relative '../core/logger'

module RjuiTools
  module React
    # Generates Tailwind CSS responsive classes from JsonUI responsive blocks.
    #
    # Canonical semantics (same as SwiftJsonUI / KotlinJsonUI): base
    # attributes are the default values, and each `responsive.<sizeClass>`
    # block is an override applied ONLY within that size class. Base values
    # are emitted by the converters' normal attribute mapping (unprefixed);
    # this helper emits only the scoped override classes.
    #
    # Size class -> Tailwind breakpoint mapping:
    #   compact            -> max-md:  (below 768px)
    #   medium             -> md:  (768px+)
    #   regular            -> lg:  (1024px+)
    #   landscape          -> requires useMediaQuery hook
    #   compact-landscape  -> requires useMediaQuery hook
    #   medium-landscape   -> requires useMediaQuery hook (+ md: for width)
    #   regular-landscape  -> requires useMediaQuery hook (+ lg: for width)
    #
    module ResponsiveHelper
      # Tailwind breakpoint prefix for each width size class
      #
      # Three disjoint bands, as every other face reads them (a medium window
      # is 768..1023). medium was `md:` until jsonui-cli 1.9.26, which held
      # from 768px up: a medium override stacked on a regular window's
      # (rjui-responsive-medium-classes-hold-on-regular-windows).
      BREAKPOINT_PREFIX = {
        'compact' => 'max-md:',
        'medium' => 'md:max-lg:',
        'regular' => 'lg:'
      }.freeze

      # "Whatever display this component naturally has."
      #
      # Emitted for a responsive `visibility: "visible"`, then UPGRADED to the
      # converter's own display utility (`flex`, `inline-flex`, …) by
      # BaseConverter#finalize_classes, which is the first place that knows it.
      #
      # It is a real Tailwind arbitrary property rather than a placeholder on
      # purpose: `display: revert` is already the correct answer for a
      # component with no display utility of its own (`<img>`, `<input>`,
      # `<select>` are not blocks), so surviving unupgraded is a valid outcome
      # instead of a dead class.
      NATURAL_DISPLAY = '[display:revert]'

      # Attributes that map to specific Tailwind utilities
      # Each entry: attribute_name => lambda(value, prefix) -> class string
      ATTRIBUTE_MAPPERS = {
        'orientation' => ->(v, prefix) {
          case JsonUIShared::EnumSpelling.lowered(v, 'View', 'orientation')
          when 'horizontal' then "#{prefix}flex-row"
          when 'vertical' then "#{prefix}flex-col"
          end
        },
        'spacing' => ->(v, prefix) {
          "#{prefix}gap-#{TailwindMapper.spacing_value(v)}"
        },
        'fontSize' => ->(v, prefix) {
          mapped = TailwindMapper::FONT_SIZE_MAP[v]
          if mapped
            # text-sm -> md:text-sm
            "#{prefix}#{mapped}"
          else
            "#{prefix}text-[#{TailwindMapper.rem(v)}]"
          end
        },
        'padding' => ->(v, prefix) {
          map_responsive_padding(v, prefix)
        },
        'width' => ->(v, prefix) {
          raw = TailwindMapper.map_width(v)
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        'height' => ->(v, prefix) {
          raw = TailwindMapper.map_height(v)
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        'weight' => ->(v, prefix) {
          raw = TailwindMapper.map_flex_grow(v)
          # map_flex_grow can return multiple utilities
          # ("flex-[1.5] min-w-0 min-h-0") — each needs its own prefix.
          raw.empty? ? nil : raw.split(' ').map { |c| "#{prefix}#{c}" }.join(' ')
        },
        # `visible` means "back to this component's natural display", which
        # the mapper cannot know: the converter appends its display utility
        # (Button `inline-flex`, View `flex`, …) after the responsive classes
        # are built. So emit NATURAL_DISPLAY and let finalize_classes upgrade.
        #
        # It used to emit a hard-coded `block`. On a Button that replaced
        # `inline-flex`, and the icon span inside it — sized with `w-[1.25em]`
        # — went back to `inline`, where width/height do not apply: the icon
        # collapsed to 0x0 at exactly the breakpoint that was supposed to
        # reveal it.
        'visibility' => ->(v, prefix) {
          case v
          when 'visible'
            "#{prefix}#{NATURAL_DISPLAY}"
          when 'gone'
            "#{prefix}hidden"
          when 'invisible'
            "#{prefix}invisible"
          end
        },
        'background' => ->(v, prefix) {
          raw = TailwindMapper.map_color(v, 'bg')
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        'fontColor' => ->(v, prefix) {
          raw = TailwindMapper.map_color(v, 'text')
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        'cornerRadius' => ->(v, prefix) {
          raw = TailwindMapper.map_corner_radius(v)
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        'flexWrap' => ->(v, prefix) {
          raw = TailwindMapper.map_flex_wrap(v)
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        'textAlign' => ->(v, prefix, type) {
          raw = TailwindMapper.map_text_align(v, type)
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        # The size bounds, paddings, margins, stacking, clip, hidden, weight
        # and opacity: classes the base converter writes with these same
        # TailwindMapper calls (BaseConverter#build_class_name), each one
        # scoped by the size class's prefix. Until jsonui-cli 2.3.29 a size
        # class dropped them, silently (ticket
        # rjui-responsive-unmapped-attributes-are-dropped-silently).
        'minWidth' => ->(v, prefix) { prefixed(TailwindMapper.map_min_width(v), prefix) },
        'maxWidth' => ->(v, prefix) { prefixed(TailwindMapper.map_max_width(v), prefix) },
        'minHeight' => ->(v, prefix) { prefixed(TailwindMapper.map_min_height(v), prefix) },
        'maxHeight' => ->(v, prefix) { prefixed(TailwindMapper.map_max_height(v), prefix) },
        'paddings' => ->(v, prefix) { map_responsive_padding(v, prefix) },
        'topPadding' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_paddings(v, nil, nil, nil), prefix) },
        'paddingTop' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_paddings(v, nil, nil, nil), prefix) },
        'rightPadding' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_paddings(nil, v, nil, nil), prefix) },
        'paddingRight' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_paddings(nil, v, nil, nil), prefix) },
        'bottomPadding' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_paddings(nil, nil, v, nil), prefix) },
        'paddingBottom' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_paddings(nil, nil, v, nil), prefix) },
        'leftPadding' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_paddings(nil, nil, nil, v), prefix) },
        'paddingLeft' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_paddings(nil, nil, nil, v), prefix) },
        'paddingStart' => ->(v, prefix) { prefixed(TailwindMapper.map_rtl_paddings(v, nil), prefix) },
        'paddingEnd' => ->(v, prefix) { prefixed(TailwindMapper.map_rtl_paddings(nil, v), prefix) },
        'margins' => ->(v, prefix) { prefixed(TailwindMapper.map_margin(v), prefix) },
        'topMargin' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_margins(v, nil, nil, nil), prefix) },
        'rightMargin' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_margins(nil, v, nil, nil), prefix) },
        'bottomMargin' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_margins(nil, nil, v, nil), prefix) },
        'leftMargin' => ->(v, prefix) { prefixed(TailwindMapper.map_individual_margins(nil, nil, nil, v), prefix) },
        'startMargin' => ->(v, prefix) { prefixed(TailwindMapper.map_rtl_margins(v, nil), prefix) },
        'endMargin' => ->(v, prefix) { prefixed(TailwindMapper.map_rtl_margins(nil, v), prefix) },
        'zIndex' => ->(v, prefix) { prefixed(TailwindMapper.map_z_index(v), prefix) },
        # false too: a size class that shows (or stops clipping) what the base
        # hides (or clips) has to say so, or the base class keeps applying.
        'hidden' => ->(v, prefix) { prefixed(v ? 'invisible' : 'visible', prefix) },
        'clipToBounds' => ->(v, prefix) { prefixed(v ? 'overflow-hidden' : 'overflow-visible', prefix) },
        'fontWeight' => ->(v, prefix) { prefixed(TailwindMapper.map_font_weight(v), prefix) },
        # The base writes nothing at 1 (fully opaque), so a size class at 1
        # names opacity-100 to undo a base below it.
        'opacity' => ->(v, prefix) {
          next nil unless v.is_a?(Numeric)

          prefixed(v >= 1 ? 'opacity-100' : TailwindMapper.map_opacity(v), prefix)
        }
      }.freeze

      # The keys of a size class's block that are not drawn by
      # ATTRIBUTE_MAPPERS but elsewhere: gravity by responsive_gravity_classes,
      # the structural keys by nobody.
      HANDLED_ELSEWHERE = %w[gravity type child data responsive].freeze

      # The keys a matchParent width's calc reads (BaseConverter#horizontal_margins).
      WIDTH_CALC_KEYS = %w[width leftMargin rightMargin startMargin endMargin margins].freeze

      # Why an attribute a size class names is not drawn on web, by the shape
      # it has there. Every other key gets the generic reason.
      UNDRAWN_REASONS = {
        %w[offsetX offsetY] => 'the web draws an offset as an inline transform, which no class can replace'
      }.freeze

      class << self
        # Build responsive Tailwind classes for a component.
        #
        # Returns a Hash:
        #   {
        #     classes: "lg:flex-row lg:gap-6 landscape:flex-row",
        #     stripped_keys: Set["orientation", "spacing"]
        #   }
        #
        # `classes` holds only the breakpoint-scoped override classes (a
        # landscape key's under media variants too: landscape_variants); the
        # base (default) value of each attribute is emitted unprefixed by
        # the converters' normal attribute mapping. `stripped_keys` lists
        # the attribute keys that have responsive overrides (informational).
        # A mapper that judges a value by the node's type (textAlign) takes it
        # as a third argument.
        # *raw*'s classes (TailwindMapper's space-separated string), each
        # scoped by *prefix*; nil when there are none.
        def prefixed(raw, prefix)
          tokens = raw.to_s.split
          tokens.empty? ? nil : tokens.map { |c| "#{prefix}#{c}" }.join(' ')
        end

        def bound?(value)
          value.is_a?(String) && value.include?('@{')
        end

        # A size class's key that is not drawn on web is said at build time:
        # the type, the id, the size class, the key and why (ticket rjui-responsive-unmapped-attributes-are-dropped-
        # silently: until jsonui-cli 2.3.29 it was dropped with no word, and
        # the author thought it held). iOS and Android draw a size class by
        # redrawing the node with the block merged in, so on those faces it
        # may well hold — the warning names the web.
        def warn_undrawn(component, size_class, attr, value, why = nil)
          return if HANDLED_ELSEWHERE.include?(attr)

          reason = if bound?(value)
                     'a bound value exists at run time only, and a size class is switched by classes'
                   elsif (known = UNDRAWN_REASONS.find { |keys, _| keys.include?(attr) }&.last)
                     known
                   else
                     why || 'the web switches a size class by classes, and this attribute is not one a class carries'
                   end
          id = component['id'] ? "'#{component['id']}'" : '(no id)'
          RjuiTools::Core::Logger.warn(
            "#{component['type']} #{id}: responsive '#{size_class}' sets '#{attr}', which is not drawn on web — #{reason}"
          )
        end

        def call_mapper(mapper, value, prefix, component)
          mapper.arity == 3 ? mapper.call(value, prefix, component['type']) : mapper.call(value, prefix)
        end

        # *carry*: a callable (BaseConverter#carry_size_class) given the keys
        # of one size class that no mapper draws, answering { tokens:, refused:
        # { key => why } }; without it those keys are said, as before.
        # *width_for*: a callable (BaseConverter#size_class_width) given the
        # width and horizontal-margin keys of one size class, answering the
        # node's width classes with them merged in, or nil when unchanged.
        def build_responsive(component, carry = nil, width_for = nil)
          result = {
            classes: [],
            carried: [],
            carried_outer: [],
            stripped_keys: Set.new
          }

          return result unless JsonUIShared::ResponsiveResolver.responsive?(component)

          overridden = JsonUIShared::ResponsiveResolver.overridden_keys(component)
          return result if overridden.empty?

          size_classes = JsonUIShared::ResponsiveResolver.size_classes(component)
          width_prefixes = width_condition_prefixes(component)
          # A block with a landscape key draws EVERY key where it is the one
          # that wins (landscape_variants): a size class's classes beside a
          # landscape key's both held on a regular landscape window until
          # each was scoped (rjui-responsive-landscape-classes-stack-on-
          # breakpoint-classes).
          runtime = landscape_block?(component)
          present = JsonUIShared::ResponsiveResolver.size_classes(component)

          # For each size class, generate prefixed Tailwind classes
          size_classes.each do |sc|
            parsed = JsonUIShared::ResponsiveResolver.parse_size_class(sc)
            overrides = component.dig('responsive', sc)
            next unless overrides.is_a?(Hash)

            # The variants this key's classes are scoped by. A key of a block
            # with a landscape key: the windows it wins in, as media variants
            # (landscape: / portrait: and the width bands) — a variant's class
            # comes after the base classes in the stylesheet, so it wins over
            # them; the unprefixed classes under a run-time isLandscape this
            # replaced (jsonui-cli 2.3.28) tied with the base classes and the
            # stylesheet's order chose. Otherwise a width breakpoint's prefix,
            # or the band in which a width condition is the one that wins.
            prefixes = if runtime
                         landscape_variants(sc, present)
                       else
                         [width_prefixes[sc] || BREAKPOINT_PREFIX[parsed[:width]] || '']
                       end
            scoped = lambda do |cls|
              cls.to_s.split.flat_map { |token| prefixes.map { |prefix| "#{prefix}#{token}" } }
            end

            pending = {}
            overrides.each do |attr, value|
              next if %w[type child data responsive].include?(attr)

              mapper = ATTRIBUTE_MAPPERS[attr]
              if mapper && !bound?(value)
                result[:classes].concat(scoped.call(call_mapper(mapper, value, '', component)))
              elsif bound?(value) || HANDLED_ELSEWHERE.include?(attr)
                warn_undrawn(component, sc, attr, value)
              else
                pending[attr] = value
              end
            end

            # The keys no mapper carries: the converter's own classes for the
            # node with them merged in, against its classes without them
            # (BaseConverter#carry_size_class) — what iOS and Android draw by
            # redrawing the node with the block merged in. What it cannot
            # carry is said, with why.
            unless pending.empty?
              carried = carry ? carry.call(pending) : { tokens: [], outer: [], refused: pending.keys.to_h { |k| [k, nil] } }
              result[:carried].concat(scoped.call(carried[:tokens].join(' ')))
              result[:carried_outer].concat(scoped.call(carried[:outer].to_a.join(' ')))
              carried[:refused].each { |attr, why| warn_undrawn(component, sc, attr, pending[attr], why) }
            end

            responsive_gravity_classes(component, overrides).each do |cls|
              result[:classes].concat(scoped.call(cls))
            end

            # A matchParent width less its margins is one calc of the width
            # and the margins together: a size class that changes either
            # draws the width the merged node has.
            # Only the classes no mapper has written already: a size class's
            # own width (lg:w-fit) is the width mapper's too, and was written
            # twice from jsonui-cli 2.3.32 (ticket rjui-size-class-width-
            # class-emitted-twice: 238 of 1050 census pairs, every one the
            # width mapper's and this).
            calc_keys = overrides.select { |k, v| WIDTH_CALC_KEYS.include?(k) && !bound?(v) }
            if width_for && !calc_keys.empty? && (width = width_for.call(calc_keys))
              result[:classes].concat(scoped.call(width.join(' ')) - result[:classes])
            end
          end

          # Informational: which attribute keys have responsive overrides.
          # Base values for these keys are emitted by the converters' normal
          # attribute mapping — re-emitting them here would duplicate the
          # unprefixed class (p-5 ... p-5 max-md:p-4) in the className.
          result[:stripped_keys] = overridden

          result
        end

        # minWidth:N / maxWidth:N (jui-responsive-width-threshold-conditions):
        # each key's classes are scoped to the band of viewport widths in
        # which it is the one that wins (the smallest maxWidth that holds,
        # else the largest minWidth), so no other key's classes stack on top
        # of it the way md: does under lg:. Tailwind v4: min-[Npx] is
        # `width >= N`, max-[Npx] is `width < N` — the layout's own meaning.
        #
        # maxWidth M(1) < M(2) < …: M(i) wins in [M(i-1), M(i)).
        # minWidth N(1) > N(2) > …: N(i) wins in [N(i), N(i-1)).
        #
        # { key => prefix } for a block of width conditions, else {}.
        def width_condition_prefixes(component)
          return {} unless JsonUIShared::ResponsiveResolver.width_conditions?(component)

          conditions = JsonUIShared::ResponsiveResolver.width_condition_keys(component)
                                                     .map { |k| [k, JsonUIShared::ResponsiveResolver.width_condition(k)] }
          maxes = conditions.select { |_, c| c[:kind] == :max }.sort_by { |_, c| c[:value] }
          mins = conditions.select { |_, c| c[:kind] == :min }.sort_by { |_, c| -c[:value] }
          prefixes = {}
          maxes.each_with_index do |(key, c), i|
            lower = i.zero? ? nil : maxes[i - 1][1][:value]
            prefixes[key] = "#{lower ? "min-[#{lower}px]:" : ''}max-[#{c[:value]}px]:"
          end
          mins.each_with_index do |(key, c), i|
            upper = i.zero? ? nil : mins[i - 1][1][:value]
            prefixes[key] = "min-[#{c[:value]}px]:#{upper ? "max-[#{upper}px]:" : ''}"
          end
          prefixes
        end

        # Whether a responsive block is drawn at run time: it has a landscape
        # key (and is not a block of width conditions).
        def landscape_block?(component)
          return false unless JsonUIShared::ResponsiveResolver.responsive?(component)
          return false if JsonUIShared::ResponsiveResolver.width_conditions?(component)

          JsonUIShared::ResponsiveResolver.size_classes(component).any? { |sc| sc.include?('landscape') }
        end

        # The windows a run-time block is judged in: the three width bands,
        # each in portrait and landscape.
        BANDS = %w[compact medium regular].freeze

        # Where `key` is the one key of `present` that wins (the first of
        # PRIORITY_ORDER present and holding), as the media variants of those
        # windows: [] where it never wins. The orientation is the one
        # useMediaQuery('(orientation: landscape)') read, and the bands the
        # breakpoint variants every other size class uses (measured in
        # Chromium on 14 windows — square, one wider or taller by a pixel, each
        # band's edge: landscape: / portrait: and max-md: / md: / lg: agreed
        # with the hooks every time).
        def landscape_variants(key, present)
          wins = ->(landscape, band) { winning_key(present, landscape, band) == key }
          in_landscape = BANDS.select { |band| wins.call(true, band) }
          in_portrait = BANDS.select { |band| wins.call(false, band) }
          return BAND_VARIANTS.fetch(in_landscape) if in_landscape == in_portrait

          BAND_VARIANTS.fetch(in_landscape).map { |band| "landscape:#{band}" } +
            BAND_VARIANTS.fetch(in_portrait).map { |band| "portrait:#{band}" }
        end

        def winning_key(present, landscape, band)
          JsonUIShared::ResponsiveResolver::PRIORITY_ORDER.find do |key|
            next false unless present.include?(key)

            parsed = JsonUIShared::ResponsiveResolver.parse_size_class(key)
            (parsed[:width].nil? || parsed[:width] == band) && (!parsed[:landscape] || landscape)
          end
        end

        # A set of width bands as the breakpoint variants that cover it.
        BAND_VARIANTS = {
          %w[compact] => %w[max-md:],
          %w[medium] => %w[md:max-lg:],
          %w[regular] => %w[lg:],
          %w[compact medium] => %w[max-lg:],
          %w[medium regular] => %w[md:],
          %w[compact regular] => %w[max-md: lg:],
          %w[compact medium regular] => [''],
          [] => []
        }.freeze

        private

        # Gravity cannot go through ATTRIBUTE_MAPPERS: its Tailwind classes
        # (items-* / justify-*) depend on the flex direction, so the override
        # must be interpreted against the EFFECTIVE orientation of the same
        # size-class block (its own orientation override, else the base one).
        #
        # Canonical semantics: a responsive `gravity` REPLACES the base
        # gravity wholesale. When the new value doesn't specify an axis that
        # the base classes covered, that axis is reset to the flex default
        # (items-stretch / justify-normal) inside the breakpoint — otherwise
        # the base's unprefixed class survives the override.
        #
        # An `orientation`-only override also re-emits the base gravity:
        # the base classes were computed against the base orientation, so
        # inside the breakpoint they alias the wrong axis (horizontal
        # centerVertical = items-center, but under a vertical override the
        # same intent is justify-center). SwiftJsonUI / KotlinJsonUI resolve
        # merged attributes at runtime, so this is rjui-specific.
        def responsive_gravity_classes(component, overrides)
          has_gravity = overrides.key?('gravity')
          base_gravity = component['gravity']
          # A single-run Label's textAlign is its horizontal too (justify-*,
          # map_label_gravity): a size class's textAlign has to move it as the
          # base one does. Until jsonui-cli 2.3.28 only lg:text-* came, and
          # the text stayed where the base put it (measured in Chromium).
          label_align = label_row?(component) && overrides.key?('textAlign')
          return [] unless has_gravity || (overrides.key?('orientation') && base_gravity) || label_align

          new_gravity = has_gravity ? overrides['gravity'] : base_gravity
          if label_row?(component)
            # A single-run Label is a flex ROW and maps its gravity itself
            # (TailwindMapper.map_label_gravity, with its textAlign): a size
            # class's gravity has to land on the same axes. Until jsonui-cli
            # 1.9.0 this mapped it as a column's, so a regular `right`
            # pushed the text to the bottom inside the breakpoint.
            text_align = overrides.key?('textAlign') ? overrides['textAlign'] : component['textAlign']
            base_classes = TailwindMapper.map_label_gravity(base_gravity, component['textAlign'])
            new_classes = TailwindMapper.map_label_gravity(new_gravity, text_align)
          else
            base_classes = TailwindMapper.map_gravity(base_gravity, component['orientation'])
            effective_orientation = overrides['orientation'] || component['orientation']
            new_classes = TailwindMapper.map_gravity(new_gravity, effective_orientation)
          end

          # Classes identical to the base need no scoped re-emit — the
          # unprefixed base class already applies at every width.
          classes = new_classes - base_classes

          # A View row's cross axis goes back to its start, the default
          # ViewConverter#cross_axis_start_by_default? gives it; anything else
          # to the flex default.
          orientation = overrides['orientation'] || component['orientation']
          row = JsonUIShared::TypeSynonyms.drawn_type(component['type']) == 'View' &&
                JsonUIShared::EnumSpelling.lowered(orientation, 'View', 'orientation') == 'horizontal'
          resets = { 'items' => row ? 'items-start' : 'items-stretch', 'justify' => 'justify-normal' }
          # A Label's lines (label_gravity_text_align): back to the start —
          # unless the size class declares its own textAlign, whose text-*
          # (ATTRIBUTE_MAPPERS) places them; a reset beside it would be a
          # second lg:text-* for the stylesheet's order to pick.
          resets['text'] = 'text-start' if label_row?(component) && !overrides.key?('textAlign')
          resets.each do |axis, reset|
            base_has = base_classes.any? { |c| c.start_with?("#{axis}-") }
            new_has = new_classes.any? { |c| c.start_with?("#{axis}-") }
            classes << reset if base_has && !new_has
          end

          classes
        end

        # A Label or Text: LabelConverter lays a single-run one out as a flex
        # row and maps its gravity itself.
        def label_row?(component)
          %w[Label Text].include?(JsonUIShared::TypeSynonyms.drawn_type(component['type']))
        end

        def map_responsive_padding(value, prefix)
          case value
          when Numeric
            "#{prefix}p-#{TailwindMapper.spacing_value(value)}"
          when Array
            map_responsive_padding_array(value, prefix)
          else
            nil
          end
        end

        def map_responsive_padding_array(arr, prefix)
          case arr.length
          when 1
            "#{prefix}p-#{TailwindMapper.spacing_value(arr[0])}"
          when 2
            "#{prefix}py-#{TailwindMapper.spacing_value(arr[0])} #{prefix}px-#{TailwindMapper.spacing_value(arr[1])}"
          when 4
            [
              "#{prefix}pt-#{TailwindMapper.spacing_value(arr[0])}",
              "#{prefix}pr-#{TailwindMapper.spacing_value(arr[1])}",
              "#{prefix}pb-#{TailwindMapper.spacing_value(arr[2])}",
              "#{prefix}pl-#{TailwindMapper.spacing_value(arr[3])}"
            ].join(' ')
          else
            nil
          end
        end
      end
    end
  end
end
