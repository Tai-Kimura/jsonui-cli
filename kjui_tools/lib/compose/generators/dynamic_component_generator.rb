# frozen_string_literal: true

require 'fileutils'
require_relative '../../core/logger'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'

module KjuiTools
  module Compose
    module Generators
      class DynamicComponentGenerator
        def initialize(name, options = {})
          @name = name
          @component_name = name  # PascalCase name
          @class_name = "Dynamic#{name}Component"
          @options = options
          @logger = Core::Logger
        end

        def generate
          create_dynamic_component_file
          update_dynamic_registry
        end

        private

        def create_dynamic_component_file
          config = Core::ConfigManager.load_config

          # Use config directory if available (where kjui.config.json was found)
          base_path = config['_config_dir'] || Dir.pwd
          source_directory = config['source_directory'] || 'src/main'
          package_name = config['package_name'] || Core::ProjectFinder.get_package_name || 'com.example.kotlinjsonui.sample'

          # Create dynamic components directory in debug source set
          dynamic_dir = File.join(
            base_path,
            source_directory.gsub('main', 'debug'),  # Replace main with debug
            'kotlin',
            package_name.gsub('.', '/'),
            'dynamic/components/extensions'
          )
          FileUtils.mkdir_p(dynamic_dir)

          file_path = File.join(dynamic_dir, "#{@class_name}.kt")

          if File.exist?(file_path)
            @logger.warn "Dynamic component file already exists: #{file_path}"
            print "Overwrite? (y/n): "
            response = gets.chomp.downcase
            return unless response == 'y'
          end

          File.write(file_path, dynamic_template)
          @logger.info "Created dynamic component file: #{file_path}"
        end

        def update_dynamic_registry
          config = Core::ConfigManager.load_config

          # Use config directory if available (where kjui.config.json was found)
          base_path = config['_config_dir'] || Dir.pwd
          source_directory = config['source_directory'] || 'src/main'
          package_name = config['package_name'] || Core::ProjectFinder.get_package_name || 'com.example.kotlinjsonui.sample'

          registry_file = File.join(
            base_path,
            source_directory.gsub('main', 'debug'),  # Replace main with debug
            'kotlin',
            package_name.gsub('.', '/'),
            'dynamic/DynamicComponentRegistry.kt'
          )

          if !File.exist?(registry_file)
            create_initial_registry
            return
          end

          # Read existing registry
          content = File.read(registry_file)

          # Check if component already registered
          if content.include?("\"#{@component_name}\"")
            @logger.warn "Component '#{@component_name}' already registered in DynamicComponentRegistry"
            return
          end

          # Add new registration with proper indentation
          new_registration = <<-REGISTRATION.chomp
            "#{@component_name}" -> {
                #{@class_name}.create(json, data)
                true
            }
          REGISTRATION

          # Insert before the else statement in when block
          content.sub!(/(when \(type\) \{.*?)(\n            else)/m) do
            existing = $1
            else_clause = $2
            "#{existing}\n#{new_registration}#{else_clause}"
          end

          # Add import if not present
          config = Core::ConfigManager.load_config
          package_name = config['package_name'] || 'com.example.kotlinjsonui.sample'
          import_line = "import #{package_name}.dynamic.components.extensions.#{@class_name}"
          unless content.include?(import_line)
            # Add import after the last import line
            content.sub!(/(import .+\n)(\n)/) do
              "#{$1}#{import_line}\n#{$2}"
            end
          end

          File.write(registry_file, content)
          @logger.info "Updated DynamicComponentRegistry with new component"
        end

        def create_initial_registry
          config = Core::ConfigManager.load_config

          # Use config directory if available (where kjui.config.json was found)
          base_path = config['_config_dir'] || Dir.pwd
          source_directory = config['source_directory'] || 'src/main'
          package_name = config['package_name'] || Core::ProjectFinder.get_package_name || 'com.example.kotlinjsonui.sample'

          registry_dir = File.join(
            base_path,
            source_directory.gsub('main', 'debug'),  # Replace main with debug
            'kotlin',
            package_name.gsub('.', '/'),
            'dynamic'
          )
          FileUtils.mkdir_p(registry_dir)

          registry_file = File.join(registry_dir, 'DynamicComponentRegistry.kt')

          config = Core::ConfigManager.load_config
          package_name = config['package_name'] || 'com.example.kotlinjsonui.sample'

          content = <<~KOTLIN
            package #{package_name}.dynamic

            import androidx.compose.runtime.Composable
            import com.google.gson.JsonObject
            import #{package_name}.dynamic.components.extensions.#{@class_name}

            /**
             * Registry for dynamic custom components
             * Auto-generated by kjui converter generator
             */
            object DynamicComponentRegistry {
                @Composable
                fun createCustomComponent(
                    type: String,
                    json: JsonObject,
                    data: Map<String, Any>
                ): Boolean {
                    return when (type) {
                        "#{@component_name}" -> {
                            #{@class_name}.create(json, data)
                            true
                        }
                        else -> false
                    }
                }
            }
          KOTLIN

          File.write(registry_file, content)
          @logger.info "Created DynamicComponentRegistry with initial component"
        end

        def dynamic_template
          config = Core::ConfigManager.load_config
          package_name = config['package_name'] || 'com.example.kotlinjsonui.sample'

          # Determine if this is a container component
          is_container = @options[:is_container]

          imports = generate_dynamic_imports(package_name)
          parsing = generate_dynamic_parameter_parsing
          params = generate_component_parameters
          helpers = generate_helper_methods

          <<~KOTLIN
            package #{package_name}.dynamic.components.extensions

            import androidx.compose.runtime.Composable
            import androidx.compose.ui.platform.LocalContext
            import com.google.gson.JsonObject
            #{imports}
            import com.kotlinjsonui.dynamic.helpers.ModifierBuilder
            import #{package_name}.extensions.#{@component_name}

            /**
             * Dynamic wrapper for #{@component_name} component
             */
            object #{@class_name} {
                @Composable
                fun create(
                    json: JsonObject,
                    data: Map<String, Any> = emptyMap()
                ) {
                    val context = LocalContext.current

            #{parsing}
                    // Build modifier
                    val modifier = ModifierBuilder.buildModifier(json, data, context = context)

                    #{if is_container
                        "#{@component_name}(\n" +
                        params +
                        "            modifier = modifier\n" +
                        "        ) {\n" +
                        "            // Process children\n" +
                        "            val children = json.get(\"child\")?.asJsonArray ?: json.get(\"children\")?.asJsonArray\n" +
                        "            children?.forEach { childJson ->\n" +
                        "                if (childJson.isJsonObject) {\n" +
                        "                    com.kotlinjsonui.dynamic.DynamicView(\n" +
                        "                        json = childJson.asJsonObject,\n" +
                        "                        data = data\n" +
                        "                    )\n" +
                        "                }\n" +
                        "            }\n" +
                        "        }"
                      else
                        "#{@component_name}(\n" +
                        params +
                        "            modifier = modifier\n" +
                        "        )"
                      end}
                }
            #{helpers}
            }
          KOTLIN
        end

        # -------------------------------------------------------------------
        # Import generation
        # -------------------------------------------------------------------

        def generate_dynamic_imports(package_name)
          return "" if !@options[:attributes] || @options[:attributes].empty?

          imports = Set.new

          has_string_or_text = false
          has_color = false
          has_callback = false
          has_collection_data_source = false

          @options[:attributes].each do |key, type|
            normalized = normalize_type(type)
            case normalized
            when :string, :text
              has_string_or_text = true
            when :color
              has_color = true
            when :callback
              has_callback = true
            when :collection_data_source
              has_collection_data_source = true
            end
          end

          imports << "import com.kotlinjsonui.dynamic.helpers.ResourceResolver" if has_string_or_text
          imports << "import com.kotlinjsonui.dynamic.helpers.ColorParser" if has_color
          imports << "import androidx.compose.ui.graphics.Color" if has_color
          imports << "import com.kotlinjsonui.data.CollectionDataSource" if has_collection_data_source

          imports.to_a.sort.join("\n")
        end

        # -------------------------------------------------------------------
        # Parameter parsing generation (using library APIs)
        # -------------------------------------------------------------------

        def generate_dynamic_parameter_parsing
          return "" if !@options[:attributes] || @options[:attributes].empty?

          lines = []
          lines << "        // Parse attributes from JSON with binding support"

          @options[:attributes].each do |key, type|
            actual_key = key.start_with?('@') ? key[1..-1] : key
            normalized = normalize_type(type)

            case normalized
            when :string, :text
              lines << "        val #{actual_key} = ResourceResolver.resolveText(json, \"#{actual_key}\", data, context)"
            when :int
              default = get_default_value(normalized)
              lines << "        val #{actual_key} = resolveInt(json, \"#{actual_key}\", data, #{default})"
            when :float
              default = get_default_value(normalized)
              lines << "        val #{actual_key} = resolveFloat(json, \"#{actual_key}\", data, #{default})"
            when :double
              default = get_default_value(normalized)
              lines << "        val #{actual_key} = resolveDouble(json, \"#{actual_key}\", data, #{default})"
            when :bool
              default = get_default_value(normalized)
              lines << "        val #{actual_key} = resolveBool(json, \"#{actual_key}\", data, #{default})"
            when :color
              lines << "        val #{actual_key} = ColorParser.parseColorWithBinding(json, \"#{actual_key}\", data, context)"
            when :callback
              lines << "        val #{actual_key} = resolveCallback(json.get(\"#{actual_key}\")?.asString, data)"
            when :collection_data_source
              lines << "        val #{actual_key} = resolveCollectionDataSource(json, \"#{actual_key}\", data)"
            else
              # Unknown type: try to resolve as string
              lines << "        val #{actual_key} = ResourceResolver.resolveText(json, \"#{actual_key}\", data, context)"
            end
          end

          lines << ""
          lines.join("\n")
        end

        # -------------------------------------------------------------------
        # Component parameter generation
        # -------------------------------------------------------------------

        def generate_component_parameters
          return "" if !@options[:attributes] || @options[:attributes].empty?

          lines = []
          @options[:attributes].each do |key, type|
            actual_key = key.start_with?('@') ? key[1..-1] : key
            normalized = normalize_type(type)

            case normalized
            when :color
              # Color is nullable from ColorParser, provide default or pass as-is
              lines << "            #{actual_key} = #{actual_key} ?: Color.Unspecified,"
            when :callback, :collection_data_source
              # Nullable, pass directly
              lines << "            #{actual_key} = #{actual_key},"
            else
              # Non-null types: already have defaults from parsing
              lines << "            #{actual_key} = #{actual_key},"
            end
          end

          lines.join("\n") + "\n"
        end

        # -------------------------------------------------------------------
        # Helper method generation
        # -------------------------------------------------------------------

        def generate_helper_methods
          return "" if !@options[:attributes] || @options[:attributes].empty?

          needed = Set.new
          @options[:attributes].each do |_, type|
            needed << normalize_type(type)
          end

          methods = []
          methods << int_helper_method if needed.include?(:int)
          methods << float_helper_method if needed.include?(:float)
          methods << double_helper_method if needed.include?(:double)
          methods << bool_helper_method if needed.include?(:bool)
          methods << callback_helper_method if needed.include?(:callback)
          methods << collection_data_source_helper_method if needed.include?(:collection_data_source)

          return "" if methods.empty?
          "\n" + methods.join("\n\n")
        end

        def int_helper_method
          <<~KOTLIN.gsub(/^/, '    ')
            private fun resolveInt(json: JsonObject, key: String, data: Map<String, Any>, default: Int = 0): Int {
                val element = json.get(key) ?: return default
                if (element.isJsonPrimitive) {
                    val prim = element.asJsonPrimitive
                    if (prim.isNumber) return prim.asInt
                    if (prim.isString) {
                        val str = prim.asString
                        if (ModifierBuilder.isBinding(str)) {
                            val prop = ModifierBuilder.extractBindingProperty(str) ?: return default
                            return (data[prop] as? Number)?.toInt() ?: default
                        }
                        return str.toIntOrNull() ?: default
                    }
                }
                return default
            }
          KOTLIN
        end

        def float_helper_method
          <<~KOTLIN.gsub(/^/, '    ')
            private fun resolveFloat(json: JsonObject, key: String, data: Map<String, Any>, default: Float = 0f): Float {
                val element = json.get(key) ?: return default
                if (element.isJsonPrimitive) {
                    val prim = element.asJsonPrimitive
                    if (prim.isNumber) return prim.asFloat
                    if (prim.isString) {
                        val str = prim.asString
                        if (ModifierBuilder.isBinding(str)) {
                            val prop = ModifierBuilder.extractBindingProperty(str) ?: return default
                            return (data[prop] as? Number)?.toFloat() ?: default
                        }
                        return str.toFloatOrNull() ?: default
                    }
                }
                return default
            }
          KOTLIN
        end

        def double_helper_method
          <<~KOTLIN.gsub(/^/, '    ')
            private fun resolveDouble(json: JsonObject, key: String, data: Map<String, Any>, default: Double = 0.0): Double {
                val element = json.get(key) ?: return default
                if (element.isJsonPrimitive) {
                    val prim = element.asJsonPrimitive
                    if (prim.isNumber) return prim.asDouble
                    if (prim.isString) {
                        val str = prim.asString
                        if (ModifierBuilder.isBinding(str)) {
                            val prop = ModifierBuilder.extractBindingProperty(str) ?: return default
                            return (data[prop] as? Number)?.toDouble() ?: default
                        }
                        return str.toDoubleOrNull() ?: default
                    }
                }
                return default
            }
          KOTLIN
        end

        def bool_helper_method
          <<~KOTLIN.gsub(/^/, '    ')
            private fun resolveBool(json: JsonObject, key: String, data: Map<String, Any>, default: Boolean = false): Boolean {
                val element = json.get(key) ?: return default
                if (element.isJsonPrimitive) {
                    val prim = element.asJsonPrimitive
                    if (prim.isBoolean) return prim.asBoolean
                    if (prim.isString) {
                        val str = prim.asString
                        if (ModifierBuilder.isBinding(str)) {
                            val prop = ModifierBuilder.extractBindingProperty(str) ?: return default
                            return data[prop] as? Boolean ?: default
                        }
                        return str.toBooleanStrictOrNull() ?: default
                    }
                }
                return default
            }
          KOTLIN
        end

        def callback_helper_method
          <<~KOTLIN.gsub(/^/, '    ')
            private fun resolveCallback(raw: String?, data: Map<String, Any>): (() -> Unit)? {
                if (raw == null) return null
                val key = if (ModifierBuilder.isBinding(raw)) ModifierBuilder.extractBindingProperty(raw) ?: raw else raw
                @Suppress("UNCHECKED_CAST")
                return data[key] as? (() -> Unit)
            }
          KOTLIN
        end

        def collection_data_source_helper_method
          <<~KOTLIN.gsub(/^/, '    ')
            private fun resolveCollectionDataSource(json: JsonObject, key: String, data: Map<String, Any>): CollectionDataSource? {
                val raw = json.get(key)?.asString ?: return null
                if (ModifierBuilder.isBinding(raw)) {
                    val prop = ModifierBuilder.extractBindingProperty(raw) ?: return null
                    return data[prop] as? CollectionDataSource
                }
                return null
            }
          KOTLIN
        end

        # -------------------------------------------------------------------
        # Type normalization
        # -------------------------------------------------------------------

        def normalize_type(type)
          stripped = type.strip.downcase

          # Check for callback patterns first (before stripping special chars)
          # Matches: (() -> Void)?, (() -> Unit)?, Callback, Action, Event
          # Also matches: ((String) -> Void)?, ((String, String) -> Void)? etc.
          return :callback if stripped.match?(/^\(.*->.*\)\??$/)
          return :callback if %w[callback action event].include?(stripped)

          # Check for CollectionDataSource
          return :collection_data_source if stripped.gsub(/[^a-z]/, '') == 'collectiondatasource'

          # Simple types
          normalized = stripped.gsub(/[^a-z]/, '')
          case normalized
          when 'string', 'text'
            :string
          when 'int', 'integer'
            :int
          when 'float'
            :float
          when 'double'
            :double
          when 'bool', 'boolean'
            :bool
          when 'color'
            :color
          else
            :string
          end
        end

        def get_default_value(normalized_type)
          # Accept either a symbol (:int) or a string ('int'); tests pass the raw
          # attribute type string, the internal callers pass the normalize_type symbol.
          if normalized_type.is_a?(Symbol)
            sym = normalized_type
          else
            raw = normalized_type.to_s.strip.downcase.gsub(/[^a-z]/, '')
            case raw
            when 'string', 'text' then sym = :string
            when 'int', 'integer' then sym = :int
            when 'float' then sym = :float
            when 'double' then sym = :double
            when 'bool', 'boolean' then sym = :bool
            when 'color' then sym = :color
            else sym = :unknown
            end
          end

          case sym
          when :string, :text
            '""'
          when :int
            '0'
          when :float
            '0.0'
          when :double
            '0.0'
          when :bool
            'false'
          when :color
            'Color.Unspecified'
          else
            'null'
          end
        end

        # Returns the parser method name for a given raw attribute type.
        # Used by callers/tests that only want the name (e.g. 'parseInt') rather than
        # the full helper Kotlin method body.
        def get_parser_method_name(type)
          sym = normalize_type(type.to_s)
          case sym
          when :string, :text
            'parseString'
          when :int
            'parseInt'
          when :float
            'parseFloat'
          when :double
            'parseDouble'
          when :bool
            'parseBoolean'
          when :color
            'parseColor'
          else
            'parseString'
          end
        end

        # Generates attribute documentation block used inside the Kotlin
        # KDoc comment at the top of the dynamic component file.
        def generate_attribute_docs
          attrs = @options[:attributes]
          if attrs.nil? || attrs.empty?
            return " * - child/children: Child composable(s)"
          end

          lines = []
          attrs.each do |key, type|
            if key.start_with?('@')
              name = key[1..-1]
              lines << " * - #{name} (#{type}, binding): Dynamically bound attribute"
            else
              lines << " * - #{key} (#{type}): Attribute"
            end
          end
          lines.join("\n")
        end
      end
    end
  end
end
