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
    # :callback, :list or :outside.
    Type = Struct.new(:raw, :kind, :canonical, :nullable, :element, :closure, :name, keyword_init: true) do
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
      text = text[0..-3] if text.end_with?('!!') # sjui's "not optional" mark; the type is what follows
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

      Type.new(raw: raw, kind: :outside, name: text, nullable: true)
    end

    # The one sentence every tool prints for a type outside the vocabulary.
    def outside_warning(attribute, type)
      t = type.is_a?(Type) ? type : parse(type)
      subject = t.kind == :list ? "the element type of '#{t.raw}'" : "'#{t.raw}'"
      "Attribute '#{attribute}': #{subject} is not in the attribute type vocabulary " \
        "(String, Int, Long, Float, Double, CGFloat, Bool, Color, CollectionDataSource, Object, a callback, T?, [T]) — " \
        "it is scaffolded as #{swift_type(t)} in Swift, #{kotlin_type(t)} in Kotlin and #{ts_type(t)} in TypeScript. " \
        'Declare that type in the app, or use a vocabulary type.'
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
      else "#{t.name}?"
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
