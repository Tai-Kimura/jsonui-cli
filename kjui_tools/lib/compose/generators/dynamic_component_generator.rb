# frozen_string_literal: true

require 'fileutils'
require_relative '../../core/logger'
require_relative '../../core/converter_generator_core'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/attribute_types'

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

          # Through the converter core's one overwrite decision, so
          # --force / --skip-existing / JUI_SKIP_EXISTING reach this
          # file too, and a closed stdin reads as "n" instead of raising;
          # it says Created or Overwrote.
          JsonUIShared::ConverterGeneratorCore.write_scaffold(
            file_path, @options, @logger,
            noun: 'dynamic component file', label: 'dynamic component file', exists_label: 'Dynamic component file'
          ) { dynamic_template }
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
            @logger.info "Unchanged #{registry_file}: it already registers '#{@component_name}'"
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
          added = content.sub!(/(when \(type\) \{.*?)(\n            else)/m) do
            existing = $1
            else_clause = $2
            "#{existing}\n#{new_registration}#{else_clause}"
          end
          # Said: until 1.8.121 a registry without this `when` was written
          # back unchanged and reported as updated.
          unless added
            @logger.warn "Could not register '#{@component_name}' in #{registry_file}: it has no " \
                         '`when (type) { … else …` to add it to — add it by hand'
            return
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
          @logger.info "Updated #{registry_file}: registered '#{@component_name}'"
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
          @logger.info "Created #{registry_file} registering '#{@component_name}'"
        end

        def dynamic_template
          config = Core::ConfigManager.load_config
          package_name = config['package_name'] || 'com.example.kotlinjsonui.sample'

          # The default mode is a container, as its composable is (it takes a
          # content lambda): until 1.8.121 this read the default's nil as "no
          # content" and called a composable that requires one — the Debug
          # build did not compile (ticket
          # kjui-converter-scaffolds-disagree-on-content).
          is_container = @options[:is_container] != false

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
                        # A leaf: children in the layout are refused here the
                        # way the build refuses them — an error in their place,
                        # not a component drawn without them. Written into the
                        # wrapper rather than called from the library, so it
                        # compiles against any KotlinJsonUI (a library helper
                        # broke a 2.41.1 face's Debug build, measured).
                        "leafRejection(json)?.let { message ->\n" +
                        "            android.util.Log.w(\"DynamicView\", message)\n" +
                        "            androidx.compose.material3.Text(text = \"⚠️ $message\", color = androidx.compose.ui.graphics.Color.Red)\n" +
                        "            return\n" +
                        "        }\n" +
                        "        #{@component_name}(\n" +
                        params +
                        "            modifier = modifier\n" +
                        "        )"
                      end}
                }
            #{helpers}#{leaf_rejection_helper}
            }
          KOTLIN
        end

        # The sentence a leaf shows in Dynamic when a layout gives it children —
        # the same as SwiftJsonUI's LeafChildren.rejection, bound by jsonui-cli
        # shared/core/leaf_children_vectors.json
        # (spec/compose/generators/leaf_wrapper_message_spec.rb runs this
        # function against it).
        def leaf_rejection_helper
          return '' unless @options[:is_container] == false

          <<~KOTLIN.gsub(/^/, '    ')

            /** What a layout that gives this leaf children is told (null: it gives none). */
            private fun leafRejection(json: JsonObject): String? {
                val key = if (json.has("child")) "child" else "children"
                val value = json.get(key) ?: return null
                fun isNode(e: com.google.gson.JsonElement) = e.isJsonObject && (e.asJsonObject.has("type") || e.asJsonObject.has("include"))
                fun idOf(o: JsonObject) = o.get("id")?.takeIf { it.isJsonPrimitive }?.let { " (id=" + it.asString + ")" } ?: ""
                val dropped = when {
                    value.isJsonArray -> value.asJsonArray.mapIndexedNotNull { i, e -> if (isNode(e)) "$key[$i]" + idOf(e.asJsonObject) else null }
                    isNode(value) -> listOf(key + idOf(value.asJsonObject))
                    else -> emptyList()
                }
                if (dropped.isEmpty()) return null
                return "'#{@component_name}'" + idOf(json) + " takes no children — it is declared a leaf, so " +
                    dropped.joinToString(", ") + (if (dropped.size == 1) " is" else " are") +
                    " not drawn. Remove the children, or regenerate the component with --container."
            }
          KOTLIN
        end

        # -------------------------------------------------------------------
        # Import generation
        # -------------------------------------------------------------------

        def generate_dynamic_imports(package_name)
          return "" if !@options[:attributes] || @options[:attributes].empty?

          kinds = @options[:attributes].values.map { |type| normalize_type(type) }
          imports = Set.new
          imports << "import com.kotlinjsonui.dynamic.helpers.ResourceResolver" if kinds.include?(:string)
          if kinds.include?(:color)
            imports << "import com.kotlinjsonui.dynamic.helpers.ColorParser"
            imports << "import androidx.compose.ui.graphics.Color"
          end
          imports << "import com.kotlinjsonui.data.CollectionDataSource" if kinds.include?(:collection_data_source)
          imports.to_a.sort.join("\n")
        end

        # -------------------------------------------------------------------
        # Parameter parsing generation (using library APIs)
        # -------------------------------------------------------------------

        # One reader per attribute, chosen by the shared vocabulary
        # (lib/core/attribute_types.rb) — the same table the composable's
        # parameter types come from, so the two agree for every type.
        def generate_dynamic_parameter_parsing
          return "" if !@options[:attributes] || @options[:attributes].empty?

          lines = []
          lines << "        // Parse attributes from JSON with binding support"

          @options[:attributes].each do |key, type|
            k = key.start_with?('@') ? key[1..-1] : key
            t = JsonUIShared::AttributeTypes.parse(type)
            read = case normalize_type(type)
                   when :string then "ResourceResolver.resolveText(json, \"#{k}\", data, context)"
                   when :int then "resolveInt(json, \"#{k}\", data, #{t.entry[:kotlin_default]})"
                   when :long then "resolveLong(json, \"#{k}\", data, #{t.entry[:kotlin_default]})"
                   when :float then "resolveFloat(json, \"#{k}\", data, #{t.entry[:kotlin_default]})"
                   when :double then "resolveDouble(json, \"#{k}\", data, #{t.entry[:kotlin_default]})"
                   when :bool then "resolveBool(json, \"#{k}\", data, #{t.entry[:kotlin_default]})"
                   when :color then "ColorParser.parseColorWithBinding(json, \"#{k}\", data, context)"
                   when :callback then "resolveCallback(json.get(\"#{k}\")?.asString, data)"
                   when :collection_data_source then "resolveCollectionDataSource(json, \"#{k}\", data)"
                   when :map then "resolveMap(json, \"#{k}\", data)"
                   when :list
                     element = JsonUIShared::AttributeTypes.kotlin_type(t)[/\AList<(.+)>\??\z/, 1]
                     "resolveList<#{element}>(json, \"#{k}\", data)"
                   else "resolveAny(json, \"#{k}\", data)"
                   end
            lines << "        val #{k} = #{read}"
          end

          lines << ""
          lines.join("\n")
        end

        # -------------------------------------------------------------------
        # Component parameter generation
        # -------------------------------------------------------------------

        def generate_component_parameters
          return "" if !@options[:attributes] || @options[:attributes].empty?

          lines = @options[:attributes].map do |key, type|
            k = key.start_with?('@') ? key[1..-1] : key
            t = JsonUIShared::AttributeTypes.parse(type)
            # ColorParser answers Color?; a Color parameter takes the default.
            if normalize_type(type) == :color && !t.nullable
              "            #{k} = #{k} ?: Color.Unspecified,"
            else
              "            #{k} = #{k},"
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
          methods << long_helper_method if needed.include?(:long)
          methods << float_helper_method if needed.include?(:float)
          methods << double_helper_method if needed.include?(:double)
          methods << bool_helper_method if needed.include?(:bool)
          methods << callback_helper_method if needed.include?(:callback)
          methods << collection_data_source_helper_method if needed.include?(:collection_data_source)
          methods << list_helper_method if needed.include?(:list)
          methods << map_helper_method if needed.include?(:map)
          methods << any_helper_method if needed.include?(:outside)

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

        def long_helper_method
          <<~KOTLIN.gsub(/^/, '    ')
            private fun resolveLong(json: JsonObject, key: String, data: Map<String, Any>, default: Long = 0L): Long {
                val element = json.get(key) ?: return default
                if (element.isJsonPrimitive) {
                    val prim = element.asJsonPrimitive
                    if (prim.isNumber) return prim.asLong
                    if (prim.isString) {
                        val str = prim.asString
                        if (ModifierBuilder.isBinding(str)) {
                            val prop = ModifierBuilder.extractBindingProperty(str) ?: return default
                            return (data[prop] as? Number)?.toLong() ?: default
                        }
                        return str.toLongOrNull() ?: default
                    }
                }
                return default
            }
          KOTLIN
        end

        # A list comes from a binding (`@{rows}`); its elements are kept when
        # they are the declared type.
        def list_helper_method
          <<~KOTLIN.gsub(/^/, '    ')
            private inline fun <reified T> resolveList(json: JsonObject, key: String, data: Map<String, Any>): List<T> {
                val raw = json.get(key)?.takeIf { it.isJsonPrimitive }?.asString ?: return emptyList()
                if (!ModifierBuilder.isBinding(raw)) return emptyList()
                val prop = ModifierBuilder.extractBindingProperty(raw) ?: return emptyList()
                return (data[prop] as? List<*>)?.filterIsInstance<T>() ?: emptyList()
            }
          KOTLIN
        end

        # An Object / Hash comes from a binding (`@{options}`).
        def map_helper_method
          <<~KOTLIN.gsub(/^/, '    ')
            private fun resolveMap(json: JsonObject, key: String, data: Map<String, Any>): Map<String, Any?> {
                val raw = json.get(key)?.takeIf { it.isJsonPrimitive }?.asString ?: return emptyMap()
                if (!ModifierBuilder.isBinding(raw)) return emptyMap()
                val prop = ModifierBuilder.extractBindingProperty(raw) ?: return emptyMap()
                return (data[prop] as? Map<*, *>)?.entries?.associate { it.key.toString() to it.value } ?: emptyMap()
            }
          KOTLIN
        end

        # A type outside the vocabulary: the bound value as it is, or the
        # literal string.
        def any_helper_method
          <<~KOTLIN.gsub(/^/, '    ')
            private fun resolveAny(json: JsonObject, key: String, data: Map<String, Any>): Any? {
                val raw = json.get(key)?.takeIf { it.isJsonPrimitive }?.asString ?: return null
                if (!ModifierBuilder.isBinding(raw)) return raw
                val prop = ModifierBuilder.extractBindingProperty(raw) ?: return null
                return data[prop]
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

        # The reader an attribute needs: the shared vocabulary's kind
        # (lib/core/attribute_types.rb). CGFloat reads as a Float; a type
        # outside the vocabulary reads as Any?.
        def normalize_type(type)
          t = JsonUIShared::AttributeTypes.parse(type.to_s)
          case t.kind
          when :callback then :callback
          when :list then :list
          when :outside then :outside
          else
            { 'string' => :string, 'int' => :int, 'long' => :long, 'float' => :float, 'cgfloat' => :float,
              'double' => :double, 'bool' => :bool, 'color' => :color,
              'collection_data_source' => :collection_data_source, 'map' => :map }.fetch(t.canonical)
          end
        end

        # The value a missing attribute takes, from the shared vocabulary.
        def get_default_value(type)
          JsonUIShared::AttributeTypes.kotlin_default(JsonUIShared::AttributeTypes.parse(type.to_s))
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
