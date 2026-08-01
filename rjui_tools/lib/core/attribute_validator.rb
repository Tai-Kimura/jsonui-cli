#!/usr/bin/env ruby
# frozen_string_literal: true

require_relative 'attribute_validator_core'

module RjuiTools
  module Core
    # Web-toolchain profile over the shared validator body
    # (lib/core/attribute_validator_core.rb — byte-identical mirror of
    # shared/core/attribute_validator_core.rb, pinned by
    # spec/core/shared_core_mirror_spec.rb). Only platform facts live
    # here; every validation rule is in the shared core. Used by React
    # converters to ensure JSON layout correctness.
    class AttributeValidator < ::JsonUIShared::AttributeValidatorCore
      # Valid modes for this platform
      MODES = [:react, :all].freeze

      # Current platform identifier
      PLATFORM = 'react'.freeze

      private

      def log_tag
        'RJUI'
      end

      # Check for extension definitions in various locations
      def extension_definition_paths
        [
          # Main ReactJsonUI structure (converters/extensions)
          File.join(Dir.pwd, 'rjui_tools', 'lib', 'react', 'converters', 'extensions', 'attribute_definitions'),
          # Project with rjui_tools at root
          File.join(Dir.pwd, 'lib', 'react', 'converters', 'extensions', 'attribute_definitions'),
          # Legacy path (components/extensions) for backwards compatibility
          File.join(Dir.pwd, 'rjui_tools', 'lib', 'react', 'components', 'extensions', 'attribute_definitions')
        ]
      end

      def styles_fallback_dirs
        [
          File.join(Dir.pwd, 'Styles'),
          File.join(Dir.pwd, 'styles'),
          File.join(Dir.pwd, 'src', 'Styles'),
          File.join(Dir.pwd, 'src', 'styles'),
          File.join(Dir.pwd, 'Layouts', 'Styles'),
          File.join(Dir.pwd, 'Layouts', 'styles')
        ]
      end

      def config_file_name
        'rjui.config.json'
      end
    end
  end
end
