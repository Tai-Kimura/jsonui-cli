# frozen_string_literal: true

module JsonUIShared
  # The attribute types `<tool> g converter --attributes key:type` understands,
  # and what each becomes on each platform — ONE table for the three
  # generators and for the Dynamic adapter / wrapper that read the value.
  # Canonical copy in shared/core/attribute_types.rb; the per-tool copies under
  # <tool>/lib/core/ stay byte-identical (each tool's shared_core_mirror_spec).
  #
  # Until 1.8.121 each generator kept its own list, and they disagreed: of 26
  # type spellings compiled per generator (2026-09-26), kjui's composable and
  # wrapper compiled for 9 (a Long, a callback or `String?` became
  # `v: Any = null`), sjui's component and adapter disagreed on Float, Color,
  # Integer and Boolean, and rjui compiled everything by turning most of it
  # into `any`. Ticket kjui-sjui-converter-attr-types-do-not-compile.
  #
  # A type is read as:
  #   T?                 nullable T
  #   T!!                sjui's "not optional" mark: a model type outside the
  #                      vocabulary that Swift declares without `?` (forced)
  #   [T] / Array(T)     a list of T
  #   (…) -> …           a callback (closure spellings), as are Callback,
  #                      Action and Event
  #   a vocabulary name  below (case-insensitive, with its aliases)
  #   anything else      outside the vocabulary: kept nullable and named in a
  #                      warning (outside_warning), never refused — faces
  #                      declare their own model types (`[AppRow]`, `Date`)
  module AttributeTypes
    module_function

    # canonical => per-platform type, the value a missing attribute takes,
    # and how the Dynamic side reads it.
    VOCABULARY = {
      'string' => { swift: 'String', swift_default: '""', kotlin: 'String', kotlin_default: '""', ts: 'string' },
      'int' => { swift: 'Int', swift_default: '0', kotlin: 'Int', kotlin_default: '0', ts: 'number' },
      'long' => { swift: 'Int', swift_default: '0', kotlin: 'Long', kotlin_default: '0L', ts: 'number' },
      # Swift keeps Float as Double, as the component always has.
      'float' => { swift: 'Double', swift_default: '0.0', kotlin: 'Float', kotlin_default: '0f', ts: 'number' },
      'double' => { swift: 'Double', swift_default: '0.0', kotlin: 'Double', kotlin_default: '0.0', ts: 'number' },
      'cgfloat' => { swift: 'CGFloat', swift_default: '0', kotlin: 'Float', kotlin_default: '0f', ts: 'number' },
      'bool' => { swift: 'Bool', swift_default: 'false', kotlin: 'Boolean', kotlin_default: 'false', ts: 'boolean' },
      'color' => { swift: 'Color', swift_default: '.clear', kotlin: 'Color', kotlin_default: 'Color.Unspecified', ts: 'string' },
      'collection_data_source' => { swift: 'CollectionDataSource', swift_default: nil, kotlin: 'CollectionDataSource',
                                    kotlin_default: nil, ts: 'any', always_nullable: true },
      # A keyed object (rjui has always scaffolded Object / Hash this way).
      'map' => { swift: '[String: Any]', swift_default: '[:]', kotlin: 'Map<String, Any?>', kotlin_default: 'emptyMap()',
                 ts: 'Record<string, any>' }
    }.freeze

    ALIASES = {
      'text' => 'string', 'integer' => 'int', 'number' => 'double', 'boolean' => 'bool',
      'collectiondatasource' => 'collection_data_source', 'object' => 'map', 'hash' => 'map', 'dictionary' => 'map'
    }.freeze

    CALLBACK_NAMES = %w[callback action event].freeze

    # One parsed attribute type. `kind` is :scalar (a vocabulary name),
    # :callback, :list or :outside. `forced`: an :outside type written with
    # sjui's `!!` — Swift declares it as the name itself (`Row`), not `Row?`.
    # Kotlin and TypeScript have no such mark and keep it nullable (`nullable`
    # stays true: it is what those two declare).
    Type = Struct.new(:raw, :kind, :canonical, :nullable, :element, :closure, :name, :forced,
                      keyword_init: true) do
      def vocabulary?
        kind != :outside && (kind != :list || element.vocabulary?)
      end

      # A bare `Array`'s element: any value, on purpose.
      def any?
        kind == :any
      end

      def entry
        VOCABULARY[canonical]
      end
    end

    def parse(raw)
      text = raw.to_s.strip
      forced = text.end_with?('!!') # sjui's "not optional" mark; the type is what precedes it
      text = text[0..-3] if forced
      nullable = false
      if text.end_with?('?') && !text.match?(/\A\(.*\)\?\z/m)
        nullable = true
        text = text[0..-2].strip
      end
      if text.include?('->')
        closure = text.sub(/\A\((.*)\)\??\z/m, '\1').strip
        return Type.new(raw: raw, kind: :callback, closure: closure, nullable: true)
      end
      return Type.new(raw: raw, kind: :callback, closure: nil, nullable: true) if CALLBACK_NAMES.include?(text.downcase)

      if (inner = text[/\A\[(.+)\]\z/m, 1] || text[/\AArray\((.+)\)\z/mi, 1])
        return Type.new(raw: raw, kind: :list, element: parse(inner), nullable: nullable)
      end
      # A bare `Array`: a list of anything.
      return Type.new(raw: raw, kind: :list, element: Type.new(raw: 'Any', kind: :any), nullable: nullable) if text.casecmp?('array')

      key = text.downcase
      canonical = VOCABULARY.key?(key) ? key : ALIASES[key]
      if canonical
        nullable ||= VOCABULARY[canonical][:always_nullable] == true
        return Type.new(raw: raw, kind: :scalar, canonical: canonical, nullable: nullable)
      end

      Type.new(raw: raw, kind: :outside, name: text, nullable: true, forced: forced)
    end

    # The one sentence every tool prints for a type outside the vocabulary.
    # The types it names are the ones the scaffolds declare (swift_type /
    # kotlin_type / ts_type, which the generators write from). `kept`: the run
    # wrote no scaffold file that declares the type — the existing ones were
    # kept (--skip-existing, "n", a closed stdin) and declare whatever they
    # already did — so it says so, and what a new scaffold would declare.
    #
    # Until 1.8.121 it named `Row?` in Swift for `Row!!` while sjui's
    # scaffold declared `Row`, and said "it is scaffolded as" when nothing
    # was written (ticket converter-attr-types-warning-wording).
    def outside_warning(attribute, type, kept: false)
      t = type.is_a?(Type) ? type : parse(type)
      subject = t.kind == :list ? "the element type of '#{t.raw}'" : "'#{t.raw}'"
      declared = "#{swift_type(t)} in Swift, #{kotlin_type(t)} in Kotlin and #{ts_type(t)} in TypeScript"
      said = if kept
               'the existing scaffold was kept (this run wrote none), so it declares whatever type it already ' \
                 "did; a new scaffold would declare #{declared}"
             else
               "it is scaffolded as #{declared}"
             end
      "Attribute '#{attribute}': #{subject} is not in the attribute type vocabulary " \
        "(String, Int, Long, Float, Double, CGFloat, Bool, Color, CollectionDataSource, Object, a callback, T?, [T]) — " \
        "#{said}. Declare that type in the app, or use a vocabulary type."
    end

    # Every attribute of `attributes` (key => type) outside the vocabulary.
    # (`map` + `compact`, not `filter_map`: consumers run this on the system
    # Ruby 2.6.)
    def outside(attributes)
      (attributes || {}).map do |key, type|
        t = parse(type)
        [key.to_s.delete_prefix('@'), t] unless t.vocabulary?
      end.compact
    end

    # ---- Swift (sjui) ------------------------------------------------------

    def swift_type(t)
      case t.kind
      when :callback then "(#{t.closure || '() -> Void'})?"
      when :list
        element = if t.element.any? then 'Any'
                  elsif t.element.vocabulary? then swift_type(t.element)
                  else t.element.name || t.element.raw.to_s
                  end
        "[#{element}]#{t.nullable ? '?' : ''}"
      when :scalar then "#{t.entry[:swift]}#{t.nullable ? '?' : ''}"
      else t.forced ? t.name : "#{t.name}?"
      end
    end

    # The value an adapter falls back to when the layout does not set it;
    # nil where the Swift type is optional.
    def swift_default(t)
      return nil if t.nullable || t.kind != :scalar && t.kind != :list
      return '[]' if t.kind == :list

      t.entry[:swift_default]
    end

    # ---- Kotlin (kjui) -----------------------------------------------------

    def kotlin_type(t)
      case t.kind
      when :callback then '(() -> Unit)?'
      when :list
        element = t.element.vocabulary? && t.element.kind == :scalar ? kotlin_type(t.element) : 'Any?'
        "List<#{element}>#{t.nullable ? '?' : ''}"
      when :scalar then "#{t.entry[:kotlin]}#{t.nullable ? '?' : ''}"
      else 'Any?'
      end
    end

    def kotlin_default(t)
      return 'null' if t.nullable || t.kind == :callback || t.kind == :outside
      return 'emptyList()' if t.kind == :list

      t.entry[:kotlin_default]
    end

    def kotlin_imports(t)
      t = t.element if t.kind == :list
      case t.canonical
      when 'color' then ['androidx.compose.ui.graphics.Color']
      when 'collection_data_source' then ['com.kotlinjsonui.data.CollectionDataSource']
      else []
      end
    end

    # ---- Literals (sjui / kjui converters) -----------------------------------
    #
    # The expression a converter writes for a literal the layout gives a prop
    # of `type` — read by the same rules as the scaffold (aliases, `T?`, `[T]`),
    # so the value matches the declared type. nil when this cannot be written:
    # a callback, a data source, a type outside the vocabulary, or a value of
    # the wrong kind; the converter then passes nothing, the prop keeps its
    # default, and the converter says so. A JSON null is written only for a
    # type that takes one (takes_null?). `hook` (optional) answers for a
    # scalar first — each converter's own colours and string resources — and
    # nil falls back here.
    #
    # Until 1.8.121 each converter formatted literals from its own spellings:
    # a `String?` or `text` literal went out unquoted, a Kotlin Float as a
    # Double, a list or a map as Ruby's inspect. Ticket
    # converter-literal-props-do-not-compile.

    # Whether a JSON null the layout gives a prop of `type` is written as the
    # language's null: for a type that is optional in the vocabulary — `T?`, a
    # type outside it (a model the app declares, optional), a callback, a data
    # source. Not for `T!!`: sjui's mark makes the model non-optional, and the
    # Swift scaffold declares it so. Every other type is not given a null on
    # any tool — the converter writes nothing and says so, as it always did
    # for `String`. The same answer on the three tools (rjui, whose props are
    # all optional in TypeScript, never writes a null and says so for the
    # same types).
    #
    # Until 1.8.121 this was `nullable`, which a `T!!` model keeps for Kotlin
    # and TypeScript: sjui wrote `nil` into its non-optional `Row` argument
    # (swiftc: "'nil' is not compatible with expected argument type 'Row'")
    # and kjui wrote `null`, neither with a word. Ticket
    # converter-writes-nil-for-a-forced-model-prop.
    def takes_null?(type)
      t = type.is_a?(Type) ? type : parse(type)
      t.nullable == true && !t.forced
    end

    def swift_literal(type, value, &hook)
      t = type.is_a?(Type) ? type : parse(type)
      return takes_null?(t) ? 'nil' : nil if value.nil?

      case t.kind
      when :list
        return nil unless value.is_a?(Array)

        items = value.map { |v| t.element.any? ? swift_any(v) : swift_literal(t.element, v, &hook) }
        items.include?(nil) ? nil : "[#{items.join(', ')}]"
      when :scalar
        (hook && hook.call(t.canonical, value)) || swift_scalar(t.canonical, value)
      end
    end

    def kotlin_literal(type, value, &hook)
      t = type.is_a?(Type) ? type : parse(type)
      return takes_null?(t) ? 'null' : nil if value.nil?

      case t.kind
      when :list
        return nil unless value.is_a?(Array)
        return 'emptyList()' if value.empty?

        items = value.map do |v|
          t.element.vocabulary? && t.element.kind == :scalar ? kotlin_literal(t.element, v, &hook) : kotlin_any(v)
        end
        items.include?(nil) ? nil : "listOf(#{items.join(', ')})"
      when :scalar
        (hook && hook.call(t.canonical, value)) || kotlin_scalar(t.canonical, value)
      end
    end

    def swift_scalar(canonical, value)
      case canonical
      when 'string' then value.is_a?(String) ? swift_string(value) : nil
      when 'int', 'long' then (n = whole(value)) && n.to_s
      when 'float', 'double', 'cgfloat' then value.is_a?(Numeric) ? value.to_s : nil
      when 'bool' then [true, false].include?(value) ? value.to_s : nil
      when 'map' then value.is_a?(Hash) ? swift_map(value) : nil
      end
    end

    def kotlin_scalar(canonical, value)
      case canonical
      when 'string' then value.is_a?(String) ? kotlin_string(value) : nil
      when 'int' then (n = whole(value)) && n.to_s
      when 'long' then (n = whole(value)) && "#{n}L"
      when 'float', 'cgfloat' then value.is_a?(Numeric) ? "#{value}f" : nil
      when 'double' then value.is_a?(Numeric) ? value.to_f.to_s : nil
      when 'bool' then [true, false].include?(value) ? value.to_s : nil
      when 'map' then value.is_a?(Hash) ? kotlin_map(value) : nil
      end
    end

    # An integer, or a float with no fraction; nil otherwise.
    def whole(value)
      return value if value.is_a?(Integer)

      value.to_i if value.is_a?(Float) && value.finite? && value == value.floor
    end

    def swift_string(text)
      escaped = text.gsub('\\') { '\\\\' }.gsub('"') { '\\"' }
                    .gsub("\n") { '\\n' }.gsub("\r") { '\\r' }.gsub("\t") { '\\t' }
      "\"#{escaped}\""
    end

    # `$` too: in Kotlin it opens a template.
    def kotlin_string(text)
      escaped = text.gsub('\\') { '\\\\' }.gsub('"') { '\\"' }.gsub('$') { '\\$' }
                    .gsub("\n") { '\\n' }.gsub("\r") { '\\r' }.gsub("\t") { '\\t' }
      "\"#{escaped}\""
    end

    # A value inside a map or a bare `Array`: JSON as the language's own
    # literal, its collections typed so an empty or mixed one still compiles.
    def swift_any(value)
      case value
      when nil then 'NSNull()'
      when String then swift_string(value)
      when true, false, Numeric then value.to_s
      when Array then value.empty? ? '[Any]()' : "[#{value.map { |v| swift_any(v) }.join(', ')}] as [Any]"
      when Hash then "#{swift_map(value)} as [String: Any]"
      end
    end

    def swift_map(hash)
      return '[:]' if hash.empty?

      "[#{hash.map { |k, v| "#{swift_string(k.to_s)}: #{swift_any(v)}" }.join(', ')}]"
    end

    def kotlin_any(value)
      case value
      when nil then 'null'
      when String then kotlin_string(value)
      when true, false, Integer then value.to_s
      when Float then value.to_s
      when Array then value.empty? ? 'emptyList<Any?>()' : "listOf<Any?>(#{value.map { |v| kotlin_any(v) }.join(', ')})"
      when Hash then kotlin_map(value)
      end
    end

    def kotlin_map(hash)
      return 'emptyMap<String, Any?>()' if hash.empty?

      "mapOf<String, Any?>(#{hash.map { |k, v| "#{kotlin_string(k.to_s)} to #{kotlin_any(v)}" }.join(', ')})"
    end

    # ---- TypeScript (rjui) -------------------------------------------------

    def ts_type(t)
      case t.kind
      when :callback then '(...args: any[]) => void'
      when :list then "#{t.element.vocabulary? && t.element.kind == :scalar ? ts_type(t.element) : 'any'}[]"
      when :scalar then t.entry[:ts]
      else 'any'
      end
    end
  end
end
