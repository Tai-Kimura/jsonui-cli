# frozen_string_literal: true

require_relative '../core/project_finder'
require_relative '../core/type_synonyms'
require_relative 'generators/dynamic_registry_types'

module KjuiTools
  module Compose
    # What a Debug build (KotlinJsonUI Dynamic) draws for the app's own
    # components, compared with what a release build (kjui's codegen) draws,
    # from the project's own files. It names what differs and rewrites nothing:
    # the registry and the Dynamic components are the app's files.
    #
    # 1. A type the app's converters draw (components/extensions,
    #    component_mappings.rb) that DynamicComponentRegistry does not
    #    register: Debug draws the built-in its spelling names, or nothing.
    #    And one registered for Dynamic that no converter draws.
    # 2. A Dynamic component (Dynamic<Type>Component.kt) that reads the
    #    node's onClick, onLongPress or alpha itself while
    #    ModifierBuilder.buildModifier applies it too (no `handles`): Debug
    #    may call or apply it twice. And one whose converter passes a handler
    #    to the component's own composable (an argument, not a modifier stage)
    #    while the Dynamic component leaves it to buildModifier: Debug applies
    #    it on the component's modifier, release where the component puts it.
    #    A converter that applies it as a modifier stage puts it where
    #    buildModifier does, and is not named.
    # A file it cannot read is named, not skipped.
    module AppComponentDynamicCheck
      STAGE_KEYS = %w[onClick onLongPress alpha].freeze
      PROBE = { 'onClick' => '__jsonuiProbeTap', 'onLongPress' => '__jsonuiProbePress' }.freeze

      module_function

      # The lines to say for the project `config` describes. Nothing when it
      # has no DynamicComponentRegistry: whether it draws in Dynamic mode is
      # not known then.
      def warnings(config, mappings:, converter_class:)
        base = config['_config_dir'] || Dir.pwd
        package = config['package_name'] || Core::ProjectFinder.get_package_name
        return [] unless package

        source_directory = config['source_directory'] || 'src/main'
        dynamic_dir = File.join(base, source_directory.gsub('main', 'debug'), 'kotlin', package.gsub('.', '/'), 'dynamic')
        registry = File.join(dynamic_dir, 'DynamicComponentRegistry.kt')
        return [] unless File.exist?(registry)

        registry_source = read(registry)
        return ["Could not read #{registry} (#{registry_source}) — the Dynamic registry was not compared with the app's converters"] unless registry_source.is_a?(Array)

        # A screen `g view` registers is snake_case; a component type is not.
        registered = Generators::DynamicRegistryTypes.cases(registry_source.first).select { |t| t.match?(/\A[A-Z]/) }
        lines = (mappings - registered).map do |type|
          "'#{type}' is drawn by the app in release but not registered for Dynamic — Debug draws #{built_in(type)}"
        end
        lines += (registered - mappings).map do |type|
          "'#{type}' is registered for Dynamic but no converter draws it — release draws #{built_in(type)}"
        end
        (mappings & registered).each do |type|
          lines.concat(stage_lines(type, File.join(dynamic_dir, 'components', 'extensions', "Dynamic#{type}Component.kt"), converter_class))
        end
        lines
      end

      # What a Dynamic component and its converter do with the node's stages.
      def stage_lines(type, file, converter_class)
        return [] unless File.exist?(file)

        source = read(file)
        return ["Could not read #{file} (#{source}) — '#{type}''s Dynamic component was not compared with its converter"] unless source.is_a?(Array)

        source = source.first
        return [] unless source.include?('buildModifier(')

        handles = source[/handles\s*=\s*setOf\(([^)]*)\)/, 1].to_s.scan(/"([^"]+)"/).flatten
        passed = converter_parameters(type, converter_class)
        STAGE_KEYS.reject { |key| handles.include?(key) }.filter_map do |key|
          if source.match?(/"#{key}"/)
            "Dynamic component '#{type}' reads the node's #{key} itself, and ModifierBuilder.buildModifier applies it too — " \
              "Debug may #{key == 'alpha' ? 'apply' : 'call'} it twice. Pass handles = setOf(\"#{key}\") to buildModifier."
          elsif passed.include?(key)
            "'#{type}': its converter passes #{key} to the component's own composable, and its Dynamic component leaves it to " \
              "ModifierBuilder.buildModifier — Debug applies it on the component's modifier, release where the component puts it."
          end
        end
      end

      # The handlers the converter of `type` passes to the component's own
      # composable, from what it emits for a node that declares them: an
      # argument `<name> = …data.<handler>…` (not `modifier = …`). A call
      # inside a modifier stage (`.pointerInput`, `.clickable`) is where
      # buildModifier puts it too.
      # [] when the converter cannot be asked.
      def converter_parameters(type, converter_class)
        klass = converter_class.call(type)
        return [] unless klass

        node = { 'type' => type, 'alpha' => 0.5 }
        PROBE.each { |key, name| node[key] = "@{#{name}}" }
        result = klass.generate(node, 0, Set.new, nil)
        code = result.is_a?(Hash) ? result[:code].to_s : result.to_s
        PROBE.select { |_, name| code.match?(/\b(?!modifier\b)\w+\s*=\s*[^\n]*data\.#{name}\b/) }.keys
      rescue StandardError
        []
      end

      # The built-in a spelling draws as without the app's converter.
      def built_in(type)
        drawn = JsonUIShared::ComponentAliases.canonical(JsonUIShared::TypeSynonyms.drawn_as(type))
        drawn == type ? "no built-in of its own (an undeclared type, unless a built-in has that name)" : "the built-in '#{drawn}'"
      end

      # [text] from a UTF-8 file, else the reason it could not be read.
      def read(path)
        text = File.read(path, encoding: 'UTF-8')
        return 'it is not UTF-8' unless text.valid_encoding?

        [text]
      rescue StandardError => e
        "#{e.class}: #{e.message}"
      end
    end
  end
end
