# frozen_string_literal: true

module KjuiTools
  module Compose
    module Generators
      # The types the generated DynamicComponentRegistry draws, listed beside
      # its `when (type)` as `val types`, and the debug DynamicComponentInitializer
      # line that hands them to KotlinJsonUI (Configuration.customComponentTypes,
      # KotlinJsonUI >= 2.42.0). What classifies a node by its type in Dynamic
      # mode — its viewId, its tap and image roles — reads that list, so an
      # app's own component is read as the app draws it, as kjui's codegen
      # reads the app's converters first. Without the list an app's own
      # ProgressBar was named `progress_<path>` in Debug and
      # `progressBar_<path>` in release.
      #
      # A registry or an initializer written before 1.9.0 has neither. `g
      # converter` and `g view` add them when they run, by adding lines and
      # never rewriting one the file has. `kjui build` does not touch either
      # file. Until they are added, KotlinJsonUI names each type the app's
      # handler draws once, with the fix.
      module DynamicRegistryTypes
        TYPES_OPEN = 'val types: Set<String> = setOf('
        ASSIGNMENT = 'Configuration.customComponentTypes = DynamicComponentRegistry.types'
        CONFIGURATION_IMPORT = 'import com.kotlinjsonui.core.Configuration'

        module_function

        # The spellings the registry's `when (type)` draws, in order.
        def cases(content)
          content.scan(/^\s*"([^"]+)"\s*->/).flatten.uniq
        end

        # The list, as the registry declares it: members indented four spaces.
        def types_block(types)
          ['    /** The types [createCustomComponent] draws: Configuration.customComponentTypes (KotlinJsonUI >= 2.42.0). */',
           "    #{TYPES_OPEN}",
           *types.map { |t| %(        "#{t}",) },
           '    )',
           ''].join("\n")
        end

        # [content, changed]: the registry with every one of `types` in its
        # list. A registry with no list gets one, made of its cases and
        # `types`, as the object's first member. nil when the registry has
        # no `object DynamicComponentRegistry {` to put it in.
        def list(content, types)
          if (open = content.index(TYPES_OPEN))
            close = content.index(/\n\s*\)/, open) or return nil
            listed = content[open...close].scan(/"([^"]+)"/).flatten
            missing = types - listed
            return [content, false] if missing.empty?

            lines = missing.map { |t| %(\n        "#{t}",) }.join
            return [content.dup.insert(close, lines), true]
          end

          head = content.match(/^object DynamicComponentRegistry \{\n/) or return nil
          all = (cases(content) + types).uniq
          [content.dup.insert(head.end(0), types_block(all)), true]
        end

        # [content, changed]: the debug initializer that also hands the
        # registry's types to KotlinJsonUI, first in initialize(). nil when
        # it has no `fun initialize() {`.
        def initializer(content)
          return [content, false] if content.include?(ASSIGNMENT)

          head = content.match(/^(\s*)fun initialize\(\) \{\n/) or return nil
          indent = "#{head[1]}    "
          line = "#{indent}// Requires KotlinJsonUI >= 2.42.0 (Configuration.customComponentTypes)\n" \
                 "#{indent}#{ASSIGNMENT}\n"
          updated = content.dup.insert(head.end(0), line)
          unless updated.include?(CONFIGURATION_IMPORT)
            last_import = updated.scan(/^import .+\n/).last
            updated = last_import ? updated.sub(last_import, "#{last_import}#{CONFIGURATION_IMPORT}\n") : updated
          end
          [updated, true]
        end
      end
    end
  end
end
