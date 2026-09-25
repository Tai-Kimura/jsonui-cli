# frozen_string_literal: true

require_relative '../../core/image_accessibility'
require_relative '../../core/string_literals'
require_relative 'modifier_builder'
require_relative 'resource_resolver'

module KjuiTools
  module Compose
    module Helpers
      # The `contentDescription` argument of an image, from its role
      # (shared/core/image_accessibility.rb):
      #   label      — the alt, localized like `text` (stringResource for a
      #                strings.json key); a bound alt that is "" at run time
      #                reads as decorative
      #   decorative — null, so TalkBack skips it
      #   control    — `legacy`, what this image read before alt existed; the
      #                build has already named it (INFO)
      # The builder writes the role after expanding includes. A node that
      # reaches a converter without one (a converter called on its own) gets
      # the role its own attributes decide, with no tappable around it.
      module ImageAccessibilityHelper
        module_function

        def content_description(json_data, legacy, required_imports = nil)
          rule = JsonUIShared::ImageAccessibility
          role = json_data[rule::ROLE_KEY] || rule.role(json_data)
          case role
          when 'label'
            alt = rule.alt(json_data)
            text = ResourceResolver.process_text(alt, required_imports)
            ModifierBuilder.is_binding?(alt) ? "(#{text}).ifEmpty { null }" : text
          when 'decorative'
            'null'
          else
            JsonUIShared::StringLiterals.kotlin(legacy)
          end
        end
      end
    end
  end
end
