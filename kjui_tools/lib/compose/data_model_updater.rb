# frozen_string_literal: true

require 'json'
require 'fileutils'
require 'set'
require_relative '../core/config_manager'
require_relative '../core/project_finder'
require_relative '../core/type_converter'
require_relative 'helpers/resource_resolver'
require_relative '../core/generated_marker'
require_relative '../core/data_model_updater_core'
require_relative 'style_loader'
require_relative 'include_expander'

module KjuiTools
  module Compose
    # Android profile over the shared Data-model updater body
    # (lib/core/data_model_updater_core.rb — byte-identical mirror of
    # shared/core/data_model_updater_core.rb, pinned by
    # spec/core/shared_core_mirror_spec.rb). Traversal/extraction live in
    # the shared core; this class owns the Android constructor facts and
    # everything that emits Kotlin.
    class DataModelUpdater < ::JsonUIShared::DataModelUpdaterCore
      def initialize
        @config = Core::ConfigManager.load_config
        @source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
        source_directory = @config['source_directory'] || 'src/main'
        @layouts_dir = File.join(@source_path, source_directory, @config['layouts_directory'] || 'assets/Layouts')
        @data_dir = File.join(@source_path, source_directory, @config['data_directory'] || 'kotlin/com/example/kotlinjsonui/sample/data')
        @package_name = @config['package_name'] || Core::ProjectFinder.get_package_name || 'com.example.app'
        @mode = @config['mode'] || 'compose'
      end

      private

      # Data defaults resolve strings, and which sections are "own" depends
      # on the layout being processed — the same per-file announcement the
      # view builder makes (compose_builder). Without it every data-default
      # lookup runs with no namespace context; the sjui data face gained the
      # same announcement in 1.6.3 (data-default context filing).
      def process_json_file(json_file)
        relative = begin
          require 'pathname'
          Pathname.new(json_file).relative_path_from(Pathname.new(@layouts_dir)).to_s
        rescue StandardError
          File.basename(json_file)
        end
        Helpers::ResourceResolver.begin_layout(relative)
        super
      end

      def expand_styles(json_data, _json_file)
        StyleLoader.load_and_merge(json_data)
      end

      def expand_includes(json_data, dir)
        IncludeExpander.process_includes(json_data, dir)
      end

      # kjui also listens to the legacy lowercase 'onclick' (bare method
      # name, XML era). onToggle joined in the W3-2 unification so
      # Switch/Toggle handlers resolve their Event signature via the
      # onValueChange key in type_mapping.json (sjui parity).
      def event_binding_attrs
        %w[onClick onclick onValueChange onToggle onTextChange onChange onLongPress]
      end

      # Legacy convention: lowercase 'onclick' carries the bare callback name
      # — or an array of them to call in order (SSoT: ["string", "array"]).
      # The shared core only puts the returned value in a Set, so the array
      # rides through whole; generate_data_content flattens it. Both ends
      # live in this profile — the core stays untouched. Without this, the
      # array handlers were never declared on the Data class while the view
      # code invokes them, so the layout could not compile.
      def onclick_action_name(node)
        value = node['onclick']
        case value
        when String
          value
        when Array
          names = value.grep(String)
          names.empty? ? nil : names
        end
      end

      def data_platform_filter
        'kotlin'
      end

      def data_mode_filter
        @mode # 'compose' or 'xml'
      end

      def boolean_class
        'Boolean'
      end

      # TypeConverter normalization runs FIRST, then the Event conversion
      # rewrites the normalized signature (kotlin type tables key on the
      # normalized spelling).
      def finalize_data_property(data_item, event_bindings)
        # Normalize type using TypeConverter with mode
        normalized = Core::TypeConverter.normalize_data_property(data_item, @mode)

        # Check if this property is bound to an event and has Event type
        prop_name = normalized['name']
        prop_class = normalized['class'].to_s

        if event_bindings[prop_name] && prop_class.include?('Event')
          # Get event type from type_mapping.json
          binding_info = event_bindings[prop_name]
          event_type = Core::TypeConverter.get_event_type(
            binding_info[:component],
            binding_info[:attribute],
            'compose'
          )

          if event_type
            # Convert Event to platform-specific type in the function signature
            # event_type is an array like ["String", "Boolean"] for compose
            if event_type.is_a?(Array)
              # Convert to Kotlin Pair type or multiple params
              converted_type = event_type.join(', ')
              normalized['class'] = prop_class.gsub('Event', converted_type)
            else
              normalized['class'] = prop_class.gsub('Event', event_type)
            end
          end
        end

        normalized
      end

      def data_file_extension
        'kt'
      end

      def extract_type_name(content)
        if match = content.match(/data\s+class\s+(\w+Data)\s*\(/)
          match[1]
        else
          nil
        end
      end

      def generate_data_content(view_name, data_properties, onclick_actions = [], json_base_name: nil)
        # The other end of onclick_action_name's array ride-through.
        onclick_actions = onclick_actions.flat_map { |a| Array(a) }.uniq
        marker_source = json_base_name ? "Layouts/#{json_base_name}.json" : "#{view_name}Data"
        marker_header = Core::GeneratedMarker.comment_header(
          source: marker_source,
          generator: "kjui build"
        )
        content = <<~KOTLIN
        #{marker_header}

        package #{@package_name}.data

        KOTLIN

        # Data-default string resolution — the sjui data face's canon
        # (1.6.3): resolve best-effort under the layout's OWN sections (plus
        # the fully-qualified and value forms find_string_key already
        # carries), SILENTLY — a defaultValue is not declared display text
        # (sentinel vocabulary like a DateSelectBox's "today" lives here),
        # so nothing warns and an unresolved literal stays literal. Resolved
        # keys emit through KotlinJsonUI.localizedString — the context-free
        # accessor generated Data can call outside composition — with the
        # raw literal as the pre-initialize fallback.
        @resolved_string_defaults = {}
        data_properties.each do |prop|
          next unless prop['class'] == 'String'
          inner = string_default_inner(prop['defaultValue'])
          next if inner.nil? || inner.empty?
          full_key = Helpers::ResourceResolver.resolve_data_default_key(
            inner, @config, @source_path
          )
          @resolved_string_defaults[prop['name']] = full_key if full_key
        end
        if @resolved_string_defaults.any?
          content += "import com.kotlinjsonui.core.KotlinJsonUI\n"
          content += "import #{@package_name}.R\n"
        end

        # Add Color import if any property uses Color type
        has_color = data_properties.any? { |prop| prop['class'] == 'Color' }
        if has_color
          content += "import androidx.compose.ui.graphics.Color\n"
        end

        # Add Painter import if any property uses Image/Painter type
        if data_properties.any? { |prop| prop['class'] == 'Image' || prop['class'] == 'Painter' }
          content += "import androidx.compose.ui.graphics.painter.Painter\n"
          # Check if any Image default value uses painterResource
          needs_painter_resource = data_properties.any? do |prop|
            (prop['class'] == 'Image' || prop['class'] == 'Painter') &&
              prop['defaultValue'].is_a?(String) &&
              prop['defaultValue'].include?('painterResource')
          end
          if needs_painter_resource
            content += "import androidx.compose.ui.res.painterResource\n"
          end
        end

        # Pull in imports for custom domain types registered in the
        # project's .jsonui-type-map.json. Without this, types like
        # `List<ProductListing>` compile-fail because `ProductListing` is unresolved.
        custom_imports = Core::TypeConverter.collect_imports_for_data_properties(data_properties)
        custom_imports.each do |import_path|
          line = "import #{import_path}\n"
          content += line unless content.include?(line)
        end

        content += "\ndata class #{view_name}Data(\n"

        if data_properties.empty?
            content += "    // No data properties defined in JSON\n"
            content += "    val placeholder: String = \"placeholder\"\n"
        else
          # Add each property with correct type and default value
          data_properties.each_with_index do |prop, index|
            name = prop['name']
            class_type = map_to_kotlin_type(prop['class'])
            default_value = prop['defaultValue']

            # If no default value or nil, make it nullable
            if default_value.nil? || default_value == 'nil'
              # Don't add ? if type already ends with ? (already nullable)
              if class_type.end_with?('?')
                content += "    var #{name}: #{class_type} = null"
              else
                content += "    var #{name}: #{class_type}? = null"
              end
            else
              formatted_value = wrap_localized_default(prop, format_default_value(default_value, prop['class']))
              content += "    var #{name}: #{class_type} = #{formatted_value}"
            end

            # Add comma if not last property
            content += "," if index < data_properties.length - 1
            content += "\n"
          end
        end

        content += ") {\n"

        # Add companion object with update function
        content += "    companion object {\n"
        content += "        // Update properties from map\n"

        # Add @Suppress("UNCHECKED_CAST") when any property needs an
        # erasure-unchecked cast: callbacks AND generic List/Map types
        # (their `as? List<...>` / `as? Map<...>` casts are unchecked too).
        has_unchecked_cast = data_properties.any? { |prop|
          class_type = prop['class'].to_s
          class_type.include?('-> Unit') || class_type.include?('-> Void') ||
            class_type.match?(/^(List|Map)<.*>$/)
        }
        if has_unchecked_cast
          content += "        @Suppress(\"UNCHECKED_CAST\")\n"
        end

        content += "        fun fromMap(map: Map<String, Any>): #{view_name}Data {\n"
        content += "            return #{view_name}Data(\n"

        if !data_properties.empty?
          data_properties.each_with_index do |prop, index|
            name = prop['name']
            class_type = prop['class']
            kotlin_type = map_to_kotlin_type(class_type)

            # Generate conversion code based on type
            content += "                #{name} = "

            case class_type
            when 'String'
              content += "map[\"#{name}\"] as? String ?: #{from_map_fallback(prop, class_type, '""')}"
            when 'Int'
              content += "(map[\"#{name}\"] as? Number)?.toInt() ?: #{from_map_fallback(prop, class_type, '0')}"
            when 'Double'
              content += "(map[\"#{name}\"] as? Number)?.toDouble() ?: #{from_map_fallback(prop, class_type, '0.0')}"
            when 'Float'
              content += "(map[\"#{name}\"] as? Number)?.toFloat() ?: #{from_map_fallback(prop, class_type, '0f')}"
            when 'Bool', 'Boolean'
              content += "map[\"#{name}\"] as? Boolean ?: #{from_map_fallback(prop, class_type, 'false')}"
            when 'Color'
              # Runtime String tokens/hex are legal Color-field values (the
              # declared defaults are token strings) — `as? Color` alone
              # silently dropped them while the dynamic path resolved them.
              content += "map[\"#{name}\"] as? Color ?: (map[\"#{name}\"] as? String)?.let { com.kotlinjsonui.generated.ColorManager.compose.colorOrHex(it) } ?: #{from_map_fallback(prop, class_type, 'Color.Unspecified')}"
            when 'CollectionDataSource'
              content += "com.kotlinjsonui.data.CollectionDataSource()"
            when /^List<.*>$/
              content += "map[\"#{name}\"] as? #{kotlin_type} ?: #{from_map_fallback(prop, class_type, 'emptyList()')}"
            when /^Map<.*>$/
              content += "map[\"#{name}\"] as? #{kotlin_type} ?: #{from_map_fallback(prop, class_type, 'emptyMap()')}"
            else
              # For custom types, try to cast directly
              content += "map[\"#{name}\"] as? #{kotlin_type}"
            end

            content += "," if index < data_properties.length - 1
            content += "\n"
          end
        else
          content += "                placeholder = \"placeholder\"\n"
        end

        content += "            )\n"
        content += "        }\n"
        content += "    }\n"

        # Add toMap function
        content += "\n"
        content += "    // Convert properties to map for runtime use\n"
        content += "    fun toMap(): MutableMap<String, Any> {\n"
        content += "        val map = mutableMapOf<String, Any>()\n"

        # Add data properties
        if !data_properties.empty?
          content += "        \n"
          content += "        // Data properties\n"
          data_properties.each do |prop|
            name = prop['name']
            default_value = prop['defaultValue']

            # If it's nullable, check for null
            if default_value.nil? || default_value == 'nil'
              content += "        #{name}?.let { map[\"#{name}\"] = it }\n"
            else
              content += "        map[\"#{name}\"] = #{name}\n"
            end
          end
        end

        if data_properties.empty?
          content += "        // No properties to add\n"
        end

        content += "        \n"
        content += "        return map\n"
        content += "    }\n"
        content += "}\n"
        content += "\n"
        content += Core::GeneratedMarker.comment_footer + "\n"
        content
      end

      def map_to_kotlin_type(json_class)
        case json_class
        when 'String'
          'String'
        when 'Int'
          'Int'
        when 'Double'
          'Double'
        when 'Float'
          'Float'
        when 'Bool', 'Boolean'
          'Boolean'
        when 'CGFloat'
          'Float'
        when 'Color'
          'Color'
        when 'Image', 'Painter'
          'Painter'
        when 'CollectionDataSource'
          # Use the actual CollectionDataSource type
          'com.kotlinjsonui.data.CollectionDataSource'
        when 'Object', 'object', 'Hash', 'hash'
          # Untyped JSON object. Without this the declared spelling was
          # emitted verbatim — `var profile: Object = ...` — and `Object` is
          # not a Kotlin type.
          # `Any?`, not `Any`: JSON permits null, and `mapOf("z" to null)`
          # infers a nullable value type that does not satisfy
          # `Map<String, Any>` ("initializer type mismatch"). Measured with
          # the cached Kotlin compiler.
          'Map<String, Any?>'
        when 'Array', 'array'
          'List<Any?>'
        when /^\(\) -> Unit$/
          # Non-optional callback becomes optional in data class
          '(() -> Unit)?'
        when /^\((.+)\) -> Unit$/
          # Callback with parameters becomes optional
          "((#{$1}) -> Unit)?"
        when /^\(\(\) -> Unit\)\?$/
          # Already optional, keep as is
          '(() -> Unit)?'
        when /^\(\((.+)\) -> Unit\)\?$/
          # Already optional with params, keep as is
          "((#{$1}) -> Unit)?"
        else
          # Return as-is for custom types
          json_class
        end
      end

      # Fallback literal for a `fromMap` field when the map entry is missing or
      # type-mismatched. Prefer the declared `defaultValue` (formatted as a
      # Kotlin literal, exactly as the `var x: T = <default>` field declaration
      # does) so `fromMap` and the field default stay in sync; iOS (sjui) keeps
      # the field default on mismatch, so this restores cross-platform symmetry.
      # Falls back to the bare type zero value only when no `defaultValue` is
      # declared.
      def from_map_fallback(prop, json_class, zero_literal)
        default_value = prop['defaultValue']
        return zero_literal if default_value.nil? || default_value == 'nil'
        wrap_localized_default(prop, format_default_value(default_value, json_class))
      end

      # Resolved string defaults emit through the context-free accessor;
      # the formatted literal rides along as the pre-initialize fallback.
      def wrap_localized_default(prop, formatted)
        full_key = (@resolved_string_defaults || {})[prop['name']]
        return formatted unless full_key
        "KotlinJsonUI.localizedString(R.string.#{full_key}, #{formatted})"
      end

      # The unquoted inner text of a String defaultValue, mirroring
      # format_default_value's quoting rules ('' / 'x' / "x" / bare).
      def string_default_inner(value)
        return nil if value.nil?
        v = value.to_s
        return nil if v == "''"
        if v.length > 1 &&
           ((v.start_with?("'") && v.end_with?("'")) ||
            (v.start_with?('"') && v.end_with?('"')))
          v[1...-1]
        else
          v
        end
      end

      def format_default_value(value, json_class)
        case json_class
        when 'String'
          # Handle string default values (matching SwiftUI implementation)
          value_str = value.to_s
          if value_str == "''"
            # Handle '' as empty string (common shorthand)
            '""'
          elsif value_str.start_with?("'") && value_str.end_with?("'") && value_str.length > 1
            # Handle single-quoted strings like "'gone'" -> "gone"
            inner_content = value_str[1...-1]
            escaped_content = inner_content.gsub('\\', '\\\\').gsub('"', '\\"')
            "\"#{escaped_content}\""
          elsif !value_str.start_with?('"') || !value_str.end_with?('"')
            # Handle unquoted strings like "gone" -> "gone"
            escaped_content = value_str.gsub('\\', '\\\\').gsub('"', '\\"')
            "\"#{escaped_content}\""
          else
            # Already properly quoted
            value_str
          end
        when 'Bool', 'Boolean'
          # Convert to boolean
          if value.is_a?(TrueClass) || value.is_a?(FalseClass)
            value.to_s
          else
            value.to_s.downcase == 'true' ? 'true' : 'false'
          end
        when 'Int'
          # Ensure it's an integer
          value.to_i.to_s
        when 'Double'
          # Ensure it's a double
          "#{value.to_f}"
        when 'Float', 'CGFloat'
          # Ensure it's a float with f suffix
          "#{value.to_f}f"
        when 'Color'
          # Handle color values - type_converter already converts color names to Color(0xFFxxxxxx)
          if value.is_a?(String) && value.start_with?('Color(')
            value # Already converted Color() expression
          elsif value.is_a?(String) && value.start_with?('Color.')
            value # Direct Color reference like Color.Red
          elsif value.is_a?(String) && value.start_with?('#')
            # Hex color - convert to Color()
            hex = value.sub('#', '')
            if hex.length == 6
              "Color(0xFF#{hex.upcase})"
            elsif hex.length == 8
              "Color(0x#{hex.upcase})"
            else
              'Color.Unspecified'
            end
          else
            'Color.Unspecified'
          end
        when 'CollectionDataSource'
          # Materialize the declared defaultValue (INTERACTIVE_HOST_CONTRACT
          # §4 shapes: shorthand cell array / explicit sections object) into
          # a real constructor — this used to always emit an EMPTY
          # CollectionDataSource(), silently dropping declared cells
          # (31 F4 Phase 2).
          collection_data_source_literal(value)
        when 'Object', 'object', 'Hash', 'hash', 'Array', 'array',
             /^List<.*>$/, /^Map<.*>$/
          # Untyped JSON container.
          #
          # Every one of these arms used to return `emptyList()` /
          # `emptyMap()` on all three of its branches — declared contents
          # were dropped silently, the same defect the CollectionDataSource
          # arm above was fixed for. And the class spellings never reached
          # them at all, because `Object` did not map to `Map<String, Any>`,
          # so a declared dictionary was interpolated as a Ruby Hash:
          #
          #     var profile: Object = {"name"=>"Grace", "meta"=>{"age"=>36}}
          #
          # Neither half is Kotlin. sjui had the identical defect (fixed in
          # d2342ecc); the literal spelling is what differs between them.
          #
          # The STRING forms come first: a defaultValue written as `"[]"` or
          # `"{}"` means an empty container, not the two-character string.
          # The old arms handled that and nothing else, and the suite pinned
          # it — an example written before today, which is why it caught this.
          case value
          when '[]' then 'emptyList()'
          when '{}' then 'emptyMap()'
          else kotlin_json_literal(value)
          end
        else
          # For all other cases, use value as-is
          value
        end
      end

      # A declared dictionary / array default as a Kotlin literal.
      #
      # Kotlin spelling differs from Swift's, so the sjui emitter cannot be
      # copied: `mapOf("k" to v)` rather than `["k": v]`, `listOf(...)`
      # rather than `[...]`, and empty forms are `emptyMap()` / `emptyList()`
      # rather than `[:]` / `[]`.
      def kotlin_json_literal(value)
        case value
        when Hash
          return 'emptyMap()' if value.empty?

          pairs = value.map do |k, v|
            "#{kotlin_string_literal(k.to_s)} to #{kotlin_json_literal(v)}"
          end
          "mapOf(#{pairs.join(', ')})"
        when Array
          return 'emptyList()' if value.empty?

          "listOf(#{value.map { |v| kotlin_json_literal(v) }.join(', ')})"
        when String then kotlin_string_literal(value)
        when Numeric, TrueClass, FalseClass then value.to_s
        when NilClass then 'null'
        else kotlin_string_literal(value.to_s)
        end
      end

      # A Kotlin string literal.
      #
      # `$` must be escaped as well as `\` and `"`: Kotlin expands `$name`
      # and `${...}` inside a string, so an unescaped `$` in declared data
      # either fails to compile or silently interpolates something else.
      # Written with block replacements — gsub with a STRING replacement
      # reads a backslash pair as a back-reference and emits one backslash
      # where two were meant.
      def kotlin_string_literal(str)
        escaped = str.to_s.gsub(0x5c.chr) { 0x5c.chr * 2 }
                     .gsub(0x22.chr) { 0x5c.chr + 0x22.chr }
                     .gsub('$') { 0x5c.chr + '$' }
        0x22.chr + escaped + 0x22.chr
      end

      # CollectionDataSource defaultValue → Kotlin constructor literal.
      # Shapes (INTERACTIVE_HOST_CONTRACT.md §4): shorthand `[ {...} ]`
      # (one section holding these cell dicts) or explicit
      # `{"sections": [{"cell": name?, "cells": [ {...} ]}]}`. Cell dicts
      # emit as mapOf(...) with string/number/boolean values only.
      def collection_data_source_literal(value)
        sections =
          if value.is_a?(Array)
            [{ 'cell' => nil, 'cells' => value }]
          elsif value.is_a?(Hash) && value['sections'].is_a?(Array)
            value['sections']
          else
            []
          end
        return 'com.kotlinjsonui.data.CollectionDataSource()' if sections.empty?

        section_literals = sections.map do |section|
          next nil unless section.is_a?(Hash)
          cells = section['cells'].is_a?(Array) ? section['cells'] : []
          cell_maps = cells.select { |c| c.is_a?(Hash) }.map do |cell|
            pairs = cell.map do |k, v|
              literal =
                case v
                when String then v.inspect
                when true, false, Numeric then v.to_s
                end
              literal && "#{k.to_s.inspect} to #{literal}"
            end.compact
            "mapOf(#{pairs.join(', ')})"
          end
          view_name = section['cell'].is_a?(String) ? section['cell'].inspect : '""'
          "com.kotlinjsonui.data.CollectionDataSection(cells = " \
            "com.kotlinjsonui.data.CollectionDataSection.CellData(" \
            "viewName = #{view_name}, data = listOf(#{cell_maps.join(', ')})))"
        end.compact

        "com.kotlinjsonui.data.CollectionDataSource(sections = listOf(#{section_literals.join(', ')}))"
      end
    end
  end
end
