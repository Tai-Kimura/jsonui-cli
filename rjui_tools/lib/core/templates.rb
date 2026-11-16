# frozen_string_literal: true

module RjuiTools
  module Core
    # The built-in templates `rjui init` and `rjui build` copy into a project
    # (NetworkImage, LinkifyText, EmbedContainer, Configuration, useColorMode),
    # in the project's language: the TypeScript templates (lib/react/templates)
    # when `typescript` is true, else their JavaScript twins (templates/js,
    # derived from them by spec/support/js_templates.rb) under .js / .jsx
    # names — as `rjui build` names its components .tsx or .jsx. Until
    # jsonui-cli 1.9.0 a JavaScript project was given the .ts / .tsx copies.
    module Templates
      module_function

      DIR = File.expand_path('../react/templates', __dir__)

      def typescript?(config)
        config.is_a?(Hash) && config['typescript'] ? true : false
      end

      # The template to copy: `network_image.tsx`, or its twin
      # `js/network_image.jsx`.
      def path(template, config)
        return File.join(DIR, template) if typescript?(config)

        File.join(DIR, 'js', javascript_name(template))
      end

      # The name the copy takes: `NetworkImage.tsx`, or `NetworkImage.jsx`.
      def file_name(name, config)
        typescript?(config) ? name : javascript_name(name)
      end

      def javascript_name(name)
        name.sub(/\.tsx\z/, '.jsx').sub(/\.ts\z/, '.js')
      end
    end
  end
end
