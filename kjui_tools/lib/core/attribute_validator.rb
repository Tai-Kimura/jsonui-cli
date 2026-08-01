#!/usr/bin/env ruby
# frozen_string_literal: true

require_relative 'attribute_validator_core'

module KjuiTools
  module Core
    # Android-toolchain profile over the shared validator body
    # (lib/core/attribute_validator_core.rb — byte-identical mirror of
    # shared/core/attribute_validator_core.rb, pinned by
    # spec/core/shared_core_mirror_spec.rb). Only platform facts live
    # here; every validation rule is in the shared core. Used by both
    # XML and Compose converters.
    class AttributeValidator < ::JsonUIShared::AttributeValidatorCore
      # Valid modes for this platform
      MODES = [:xml, :compose, :dynamic, :all].freeze

      # Current platform identifier
      PLATFORM = 'kotlin'.freeze

      private

      def log_tag
        'KJUI'
      end

      # Check for extension definitions in various locations
      def extension_definition_paths
        [
          # Main KotlinJsonUI structure
          File.join(Dir.pwd, 'kjui_tools', 'lib', 'compose', 'components', 'extensions', 'attribute_definitions'),
          # Test app structure
          File.join(Dir.pwd, 'app', 'kjui_tools', 'lib', 'compose', 'components', 'extensions', 'attribute_definitions')
        ]
      end

      def styles_fallback_dirs
        [
          # Styles inside Layouts directory (common pattern)
          File.join(Dir.pwd, 'src', 'main', 'assets', 'Layouts', 'Styles'),
          File.join(Dir.pwd, 'app', 'src', 'main', 'assets', 'Layouts', 'Styles'),
          # Styles at assets root
          File.join(Dir.pwd, 'src', 'main', 'assets', 'Styles'),
          File.join(Dir.pwd, 'app', 'src', 'main', 'assets', 'Styles'),
          # Other common locations
          File.join(Dir.pwd, 'Styles'),
          File.join(Dir.pwd, 'styles'),
          File.join(Dir.pwd, 'Layouts', 'Styles'),
          File.join(Dir.pwd, 'Layouts', 'styles')
        ]
      end

      def config_file_name
        'kjui.config.json'
      end
    end
  end
end
