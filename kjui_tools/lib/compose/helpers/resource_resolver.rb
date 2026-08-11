# frozen_string_literal: true

require 'rexml/document'
require 'json'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/logger'
require_relative '../../core/string_manager_core'
require_relative 'binding_expression'

module KjuiTools
  module Compose
    module Helpers
      class ResourceResolver
        class << self
          # Android drawable resource names must match [a-z][a-z0-9_.]* with
          # no dots in the generated R reference. Strip common image
          # extensions and sanitize everything else (e.g. iOS SF-Symbol
          # names like "star.fill" -> "star_fill") so the emitted
          # `R.drawable.<name>` always compiles.
          def drawable_name(raw)
            name = raw.to_s.sub(/\.(png|jpg|jpeg|webp)\z/i, '')
            name = name.downcase.gsub(/[^a-z0-9_]/, '_')
            name = "img_#{name}" if name.empty? || name !~ /\A[a-z]/
            name
          end

          # Thread-local storage for data definitions during build
          def data_definitions
            Thread.current[:kjui_data_definitions] || {}
          end

          def data_definitions=(definitions)
            Thread.current[:kjui_data_definitions] = definitions
          end

          # The strings.json sections the layout being generated owns
          # (StringManagerCore#namespace_candidates), kjui's relative-path
          # spelling first. Thread-local per-build state, the same channel
          # data_definitions uses. Empty means "no layout context" and
          # resolution falls back to strings.json order, which is what
          # every caller got before.
          def current_namespaces
            Thread.current[:kjui_string_namespaces] || []
          end

          def current_namespaces=(namespaces)
            Thread.current[:kjui_string_namespaces] = namespaces
          end

          # Announce the layout about to be generated, as a path relative
          # to the layouts directory.
          def begin_layout(relative_path)
            self.current_namespaces = JsonUIShared::StringManagerCore.namespace_candidates(
              relative_path, preferred: :relative
            )
          rescue StandardError
            self.current_namespaces = []
          end

          # Check if a property has a default value (non-optional)
          def has_default_value?(property_name)
            return false unless data_definitions[property_name]
            !data_definitions[property_name]['defaultValue'].nil?
          end

          def get_property_class(property_name)
            return nil unless data_definitions[property_name]
            data_definitions[property_name]['class']
          end

          # Don't cache - just load each time to avoid issues
          def cached_config
            Core::ConfigManager.load_config
          end

          def cached_source_path
            Core::ProjectFinder.get_full_source_path || Dir.pwd
          end
          
          # Process text with data binding and resource resolution
          def process_text(text, required_imports = nil)
            return quote(text) unless text.is_a?(String)

            # Handle data binding expressions — canonical parse + emit
            # (nullability-aware `?:` fallback, real `??` default evaluation)
            # is centralized in BindingExpression.
            if (inner = BindingExpression.extract_inner(text))
              return BindingExpression.interpolated_access(inner)
            end
            
            # Skip resource resolution if we're in the extraction phase
            # (Resources directory doesn't exist yet)
            source_directory = cached_config['source_directory'] || 'src/main'
            layouts_dir = File.join(cached_source_path, source_directory, cached_config['layouts_directory'] || 'assets/Layouts')
            resources_dir = File.join(layouts_dir, 'Resources')
            
            # If Resources directory doesn't exist, we're in extraction phase
            # Just return quoted text
            return quote(text) unless File.exist?(resources_dir)
            
            # Try to resolve as a string resource
            resolved = resolve_string(text, cached_config, cached_source_path)
            if resolved.include?('stringResource')
              required_imports&.add(:string_resource)
              required_imports&.add(:r_class)
            end
            resolved
          end
          
          # Process color with resource resolution
          def process_color(color, required_imports = nil)
            return nil unless color.is_a?(String)

            # Handle data binding expressions - convert to data property access.
            # Canonical parse via BindingExpression so a `?? 'default'` no
            # longer corrupts the property path; a string default feeds the
            # ColorManager name fallback for nullable String properties.
            if color.start_with?('@{') && color.end_with?('}')
              parsed = BindingExpression.parse(color[2..-2])
              variable = parsed.path
              prop_class = get_property_class(variable)

              # String type: resolve color name at runtime via ColorManager
              if prop_class == 'String'
                required_imports&.add(:color_manager)
                if has_default_value?(variable)
                  return "ColorManager.compose.color(data.#{variable}) ?: Color.Unspecified"
                else
                  fallback = parsed.has_default && parsed.default.is_a?(String) ? parsed.default : ''
                  return "ColorManager.compose.color(data.#{variable} ?: #{BindingExpression.quote(fallback)}) ?: Color.Unspecified"
                end
              end

              # Color type: use directly
              if has_default_value?(variable)
                return "data.#{variable}"
              else
                return "data.#{variable} ?: Color.Unspecified"
              end
            end
            
            # Skip resource resolution if we're in the extraction phase
            # (Resources directory doesn't exist yet)
            source_directory = cached_config['source_directory'] || 'src/main'
            layouts_dir = File.join(cached_source_path, source_directory, cached_config['layouts_directory'] || 'assets/Layouts')
            resources_dir = File.join(layouts_dir, 'Resources')
            
            # If Resources directory doesn't exist, we're in extraction phase
            # Just return standard color parsing
            unless File.exist?(resources_dir)
              return "Color(android.graphics.Color.parseColor(#{quote(color)}))"
            end
            
            resolved = resolve_color(color, cached_config, cached_source_path)
            if resolved&.include?('colorResource')
              required_imports&.add(:color_resource)
              required_imports&.add(:r_class)
            end
            resolved
          end
          
          private
          
          # Check if a string resource exists in strings.xml
          def resolve_string(text, config, source_path)
            return quote(text) unless text.is_a?(String)
            
            # Skip if it's a data binding expression
            return quote(text) if text.start_with?('@{') || text.start_with?('${')
            
            # Try to find the string in strings.xml
            string_key = find_string_key(text, config, source_path)
            
            if string_key
              # Return stringResource reference
              "stringResource(R.string.#{string_key})"
            else
              # Return quoted string
              quote(text)
            end
          end
          
          # Check if a color resource exists
          def resolve_color(color, config, source_path)
            return nil unless color.is_a?(String)

            # Skip if it's a data binding expression
            return "Color(android.graphics.Color.parseColor(#{quote(color)}))" if color.start_with?('@{') || color.start_with?('${')

            # Try to find the color in colors.json
            color_key = find_color_key(color, config, source_path)

            if color_key
              # Return colorResource reference
              "colorResource(R.color.#{color_key})"
            else
              # Return Color.parseColor
              "Color(android.graphics.Color.parseColor(#{quote(color)}))"
            end
          end
          
          private
          
          def cached_strings_data
            source_directory = cached_config['source_directory'] || 'src/main'
            layouts_dir = File.join(cached_source_path, source_directory, cached_config['layouts_directory'] || 'assets/Layouts')
            strings_file = File.join(layouts_dir, 'Resources', 'strings.json')
            
            return {} unless File.exist?(strings_file)
            
            begin
              JSON.parse(File.read(strings_file))
            rescue JSON::ParserError
              {}
            end
          end
          
          def cached_colors_data
            source_directory = cached_config['source_directory'] || 'src/main'
            layouts_dir = File.join(cached_source_path, source_directory, cached_config['layouts_directory'] || 'assets/Layouts')
            colors_file = File.join(layouts_dir, 'Resources', 'colors.json')
            
            return {} unless File.exist?(colors_file)
            
            begin
              JSON.parse(File.read(colors_file))
            rescue JSON::ParserError
              {}
            end
          end
          
          def find_string_key(text, config, source_path)
            strings_data = cached_strings_data

            # 1. Check if text matches a key in strings.json (e.g., "welcome_back"
            # matches login.welcome_back) — but ONLY within sections this layout
            # owns. The fully-qualified form below names its section explicitly,
            # so a foreign hit there is a deliberate reference; a BARE key
            # hitting a foreign section is a collision, not a reference (the
            # ruling sjui's key lookup already carries). Scanning every section
            # here resolved a cell's bare key through its screen's section and
            # the two platforms answered differently — kjui showed the right
            # text while sjui shipped the raw key (asymmetric-resolution
            # filing, 2026-08-11).
            current_namespaces.each do |namespace|
              entries = strings_data[namespace]
              next unless entries.is_a?(Hash)

              return "#{namespace}_#{text}" if entries.key?(text)
            end

            # 2. Check if text is already a full resource key (e.g., "login_welcome_back")
            strings_data.each do |file_prefix, file_strings|
              next unless file_strings.is_a?(Hash)

              file_strings.each do |key, _value|
                full_key = "#{file_prefix}_#{key}"
                if full_key == text
                  return text
                end
              end
            end

            # 3. Search by value match (e.g., "Email address" matches the value in strings.json)
            resolved = JsonUIShared::StringManagerCore.resolve_string_reference(
              strings_data, text, current_namespaces
            )
            if resolved
              report_string_namespace(text, resolved)
              return "#{resolved['namespace']}_#{resolved['key']}"
            end

            # 4. Fallback: check strings.xml directly for snake_case/single-word text
            # This handles cases where text is a resource key name not yet in strings.json
            # e.g., "welcome_back" might exist in strings.xml as "login_welcome_back".
            # The prefix scan is own-sections-only for the same reason step 1 is —
            # a cross-section prefix here would re-open the bare-key side door
            # through the XML. The exact match stays global: a full key names
            # its section itself.
            if text.match?(/^[a-zA-Z][a-zA-Z0-9_]*$/)
              strings_xml_path = File.join(source_path, config['source_directory'] || 'src/main', 'res/values/strings.xml')
              if File.exist?(strings_xml_path)
                xml_content = File.read(strings_xml_path)
                current_namespaces.each do |namespace|
                  full_key = "#{namespace}_#{text}"
                  if xml_content.include?("name='#{full_key}'") || xml_content.include?("name=\"#{full_key}\"")
                    return full_key
                  end
                end
                # Also check exact match (e.g., "no_favorites_yet" as-is)
                if xml_content.include?("name='#{text}'") || xml_content.include?("name=\"#{text}\"")
                  return text
                end
              end
            end

            report_foreign_bare_key(text, strings_data)
            nil
          end

          # A bare key declared ONLY under sections this layout does not own
          # is a broken reference under the own-section canon — say so at emit
          # time instead of silently quoting the literal, which puts the raw
          # key on screen. Warning (not error) so `jui build`'s zero-warning
          # invariant gates it, the same channel as report_string_namespace.
          def report_foreign_bare_key(text, strings_data)
            return unless strings_data.is_a?(Hash)
            return unless text.match?(/^[a-z][a-z0-9]*(_[a-z0-9]+)*_?$/)

            own = current_namespaces
            # map + compact, not filter_map — Ruby 2.6 (see section_extractor).
            foreign = strings_data.map do |namespace, entries|
              namespace if entries.is_a?(Hash) && entries.key?(text) && !own.include?(namespace)
            end.compact
            return if foreign.empty?

            Core::Logger.warn(
              "Bare key #{text.inspect} is declared only in foreign strings.json " \
              "section(s) #{foreign.join(', ')} — a bare key resolves within the " \
              "layout's own sections (#{own.join(' / ')}). Use the fully-qualified " \
              "'<section>_<key>' spelling for a deliberate cross-section reference, " \
              "or register the key under the layout's own section (jsonui-localize)."
            )
          end
          
          # Both conditions are SSoT damage rather than build errors, so
          # they warn — `jui build`'s zero-warning invariant makes them
          # gate, and `jui lint-strings` reports the same pair statically.
          def report_string_namespace(text, resolved)
            candidates = resolved['candidates'] || []
            if candidates.length > 1
              Core::Logger.warn(
                "String #{text.inspect} is declared in #{candidates.length} strings.json " \
                "sections (#{candidates.join(', ')}) — resolved to #{resolved['namespace']}. " \
                'Two sections holding one string is a forked SSoT: delete the duplicate so ' \
                'every platform reads the same key.'
              )
            end

            return unless resolved['foreign'] && current_namespaces.any?

            Core::Logger.warn(
              "String #{text.inspect} resolved to section #{resolved['namespace']}, which this " \
              "layout does not own (#{current_namespaces.join(' / ')}) — the SSoT never " \
              "declared it here. Register the string under the layout's own section " \
              '(jsonui-localize).'
            )
          end

          def find_color_key(color, config, source_path)
            colors_data = cached_colors_data
            
            # First check if the color itself is a key in colors.json
            if colors_data.has_key?(color)
              return color
            end
            
            # If it's a hex color, normalize and search by value
            if color.match?(/^#?[A-Fa-f0-9]{6,8}$/)
              normalized_color = normalize_color(color)
              
              # Search through colors by value
              colors_data.each do |key, value|
                if normalize_color(value) == normalized_color
                  return key
                end
              end
            end
            
            # Also check colors.xml for predefined Android colors
            # These are colors that might be defined in colors.xml but not in colors.json
            colors_xml_path = File.join(source_path, config['source_directory'] || 'src/main', 'res/values/colors.xml')
            if File.exist?(colors_xml_path)
              # Quick check - if the color name exists in colors.xml
              # we'll assume it's available (proper check would parse XML)
              xml_content = File.read(colors_xml_path)
              if xml_content.include?("name='#{color}'") || xml_content.include?("name=\"#{color}\"")
                return color
              end
            end
            
            nil
          end
          
          def normalize_color(color)
            return nil unless color.is_a?(String)
            
            # Remove # if present and convert to lowercase
            color.sub(/^#/, '').downcase
          end
          
          def quote(text)
            # Escape special characters properly
            escaped = text.to_s.gsub('\\', '\\\\\\\\')
                              .gsub('"', '\\"')
                              .gsub("\n", '\\n')
                              .gsub("\r", '\\r')
                              .gsub("\t", '\\t')
            "\"#{escaped}\""
          end
        end
      end
    end
  end
end