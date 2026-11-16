# frozen_string_literal: true

require 'json'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'

module SjuiTools
  module SwiftUI
    module Views
      # A colour mode's own picture: jui build writes `<name>.<mode>.svg` as the
      # asset `<name>__<mode>` and the table `image_modes.json` beside
      # colors.json ({"images": {name: {mode: asset}}}). A generated view names
      # such an image through ColorManager.image(_:), which reads the current
      # mode; GeneratedView observes the mode, so its body (and the name) is
      # read again when the mode changes.
      #
      # Only a project with a picture for a mode, and a ColorManager
      # (resource_manager_directory), writes anything new: every other image is
      # `Image("<name>")`, as it always was.
      module ImageModes
        module_function

        def table
          path = table_path
          return {} unless path && File.exist?(path)

          images = JSON.parse(File.read(path))['images']
          images.is_a?(Hash) ? images.select { |_, by_mode| by_mode.is_a?(Hash) && !by_mode.empty? } : {}
        rescue JSON::ParserError, StandardError
          {}
        end

        def table_path
          config = Core::ConfigManager.load_config
          source_path = Core::ProjectFinder.get_full_source_path || Dir.pwd
          File.join(source_path, config['layouts_directory'] || 'Layouts', 'Resources', 'image_modes.json')
        rescue StandardError
          nil
        end

        def color_manager?
          !Core::ConfigManager.load_config['resource_manager_directory'].to_s.empty?
        rescue StandardError
          false
        end

        def active?
          color_manager? && !table.empty?
        end

        # A written name with a mode's picture, as a Swift String expression;
        # nil for any other name (the call site writes it as it always did).
        def wrap_literal(name)
          return nil unless active? && table.key?(name.to_s)

          "ColorManager.image(#{name.to_s.to_json})"
        end

        # A String expression read at run time (a binding, a ternary of
        # names); nil when the project has no mode's picture.
        def wrap_expression(expr)
          return nil unless active?

          "ColorManager.image(#{expr})"
        end

        # The operand a call site writes for an image's name: *code* as it
        # always was, or ColorManager.image(...) around it. *literal* is the
        # written name when *code* is its quoted spelling.
        def operand(code, literal: nil)
          (literal.nil? ? wrap_expression(code) : wrap_literal(literal)) || code
        end
      end
    end
  end
end
