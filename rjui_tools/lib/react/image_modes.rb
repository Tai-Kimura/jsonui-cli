# frozen_string_literal: true

require 'json'
require_relative '../core/config_manager'

module RjuiTools
  module React
    # A colour mode's own picture on the web. jui build copies
    # `<name>.<mode>.svg` beside `<name>.svg` into the images directory and
    # writes `image_modes.json` beside colors.json
    # ({"images": {name: {mode: asset}}}).
    #
    # The page draws it by CSS, by the same rule as a colour: theme.css binds
    # `--image-<name>` under `:root`, `:root[data-theme=…]` and the OS's dark,
    # and a chosen mode's `<style id="jsonui-color-mode">` binds it under
    # `:root:root:root` (ColorManager#mode_css). An `<img>` keeps its `src` (the
    # name's own picture) and takes `content: var(--image-<name>)`: where the
    # variable is bound, the element is replaced by that picture; where it is
    # not (no theme.css), `content` is invalid at computed time and the `src`
    # is drawn. A CSS url() takes `var(--image-<name>, url(<the picture>))`.
    # No script, so the first paint already has the mode's picture and there
    # is nothing to hydrate.
    module ImageModes
      module_function

      def table(layouts_dir = nil)
        path = table_path(layouts_dir)
        return {} unless path && File.exist?(path)

        images = JSON.parse(File.read(path))['images']
        images.is_a?(Hash) ? images.select { |_, by_mode| by_mode.is_a?(Hash) && !by_mode.empty? } : {}
      rescue StandardError
        {}
      end

      def table_path(layouts_dir = nil)
        layouts_dir ||= File.join(Dir.pwd, Core::ConfigManager.load_config['layouts_directory'] || 'src/Layouts')
        File.join(layouts_dir, 'Resources', 'image_modes.json')
      rescue StandardError
        nil
      end

      # The custom property a name's picture is bound to.
      def variable(name)
        "--image-#{name.to_s.gsub(/[^A-Za-z0-9_-]/, '-')}"
      end

      # The written name (an image's srcName, a Button's image) without its
      # extension, when it has a mode's picture; else nil.
      def name_with_modes(written)
        return nil unless written.is_a?(String)

        name = written.sub(/\.svg\z/i, '')
        table.key?(name) ? name : nil
      end

      def any?
        !table.empty?
      end

      # `content` for an <img> whose name is written: a JS string literal.
      def content_literal(name)
        "'var(#{variable(name)})'"
      end

      # `content` for an <img> whose name is bound: a template literal.
      def content_bound(expr)
        "`var(--image-${#{expr}})`"
      end

      # The declarations of one mode: each name's picture in *mode*, else its
      # own (so a mode's rule never leaves another mode's picture bound).
      def declarations(mode, images = table)
        images.sort.map do |name, by_mode|
          file = by_mode.key?(mode) ? "#{name}.#{mode}.svg" : "#{name}.svg"
          "#{variable(name)}:url(\"/images/#{file}\")"
        end
      end
    end
  end
end
