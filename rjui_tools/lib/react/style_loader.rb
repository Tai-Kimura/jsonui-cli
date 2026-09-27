# frozen_string_literal: true

require 'json'
require_relative '../core/config_manager'
require_relative '../core/stage_failures'

module RjuiTools
  module React
    class StyleLoader
      # What load_style_file returns for a file that exists and does not parse.
      UNPARSED = :unparsed

      def self.load_and_merge(component, styles_dir = nil)
        return component unless component.is_a?(Hash)

        # If style attribute exists, load style file and merge
        if component['style']
          style_name = component['style']
          style_data = load_style_file(style_name, styles_dir)

          if style_data && style_data != UNPARSED
            # Merge style data as base, then override with component data
            # Remove style attribute (to prevent infinite loop)
            component_without_style = component.dup
            component_without_style.delete('style')

            # If component has type, ignore style's type
            # If component has no type, use style's type
            style_data_for_merge = style_data.dup
            if component_without_style['type']
              style_data_for_merge.delete('type')
            end

            # Merge: style as base, component properties override
            merged = deep_merge(style_data_for_merge, component_without_style)
            component = merged
          elsif style_data.nil?
            # Only a file that is not there. One that is there and did not
            # parse was named with its parse error where it was read; until
            # 1.9.0 this line followed it and said it was not found
            # (ticket uikit-build-reports-success-after-a-binding-error).
            puts "Warning: Style file '#{style_name}' not found"
            component.delete('style')
          else
            # Remove style attribute and continue
            component.delete('style')
          end
        end

        # Process children recursively
        if component['child']
          if component['child'].is_a?(Array)
            component['child'] = component['child'].map { |child| load_and_merge(child, styles_dir) }
          else
            component['child'] = load_and_merge(component['child'], styles_dir)
          end
        end

        # Also process children attribute (used by some components)
        if component['children']
          if component['children'].is_a?(Array)
            component['children'] = component['children'].map { |child| load_and_merge(child, styles_dir) }
          else
            component['children'] = load_and_merge(component['children'], styles_dir)
          end
        end

        component
      end

      # A style that could not be parsed: the layouts using it are drawn
      # without it, which the build names at its end, once. Until 1.9.0
      # this path printed an "Error parsing" line above "Build completed!",
      # and the converters' own loader (BaseConverter#load_style) said
      # nothing at all (ticket uikit-build-reports-success-after-a-binding-error).
      def self.unparsed_style(style_file, error)
        JsonUI::StageFailures.record_once(
          'styles', "#{File.expand_path(style_file)} could not be parsed (#{error.message}); " \
                    'the layouts using it were drawn without it'
        )
      end

      # A style a layout names that is not there: the layouts using it are drawn
      # without it — a stage that did not complete, named once at the end of the
      # build. Ruled so on 2026-09-26 after counting the faces' references: 2167
      # `style` references in the config-declared layout dirs of the four
      # consumer layout trees, 0 to no file (ticket
      # uikit-build-reports-success-after-a-binding-error).
      def self.missing_style(where)
        JsonUI::StageFailures.record_once('styles', "#{where} was not found; the layouts using it were drawn without it")
      end

      class << self
        private

        def load_style_file(style_name, styles_dir = nil)
          # Determine styles directory
          if styles_dir.nil?
            # Load config
            config = Core::ConfigManager.load_config

            # Get source path
            source_path = config['source_path'] || Dir.pwd

            # Get styles directory from config (default: 'Styles')
            styles_directory = config['styles_directory'] || 'Styles'
            styles_dir = File.join(source_path, styles_directory)

            # If directory doesn't exist, try fallbacks
            unless Dir.exist?(styles_dir)
              fallback_dirs = [
                File.join(source_path, 'styles'),
                File.join(source_path, config['layouts_directory'] || 'Layouts', 'Styles'),
                File.join(source_path, config['layouts_directory'] || 'Layouts', 'styles')
              ]

              styles_dir = fallback_dirs.find { |dir| Dir.exist?(dir) }

              unless styles_dir
                StyleLoader.missing_style("style '#{style_name}' (no styles directory: #{File.join(source_path, styles_directory)}, #{fallback_dirs.join(', ')})")
                return nil
              end
            end
          end

          # Style file path
          style_file = File.join(styles_dir, "#{style_name}.json")

          unless File.exist?(style_file)
            StyleLoader.missing_style(File.expand_path(style_file))
            return nil
          end

          # Parse and return JSON
          JSON.parse(File.read(style_file))
        rescue JSON::ParserError => e
          puts "Error parsing style file '#{style_file}': #{e.message}"
          StyleLoader.unparsed_style(style_file, e)
          UNPARSED
        end

        def deep_merge(hash1, hash2)
          return hash2 if hash1.nil?
          return hash1 if hash2.nil?

          result = hash1.dup

          hash2.each do |key, value|
            if result[key].is_a?(Hash) && value.is_a?(Hash)
              # Both are hashes - merge recursively
              result[key] = deep_merge(result[key], value)
            elsif result[key].is_a?(Array) && value.is_a?(Array)
              # Both are arrays - override (don't merge arrays)
              result[key] = value
            else
              # Otherwise override
              result[key] = value
            end
          end

          result
        end
      end
    end
  end
end
