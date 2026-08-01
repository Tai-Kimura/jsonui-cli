#!/usr/bin/env ruby
# frozen_string_literal: true

require_relative 'attribute_validator_core'

module SjuiTools
  module Core
    # iOS-toolchain profile over the shared validator body
    # (lib/core/attribute_validator_core.rb — byte-identical mirror of
    # shared/core/attribute_validator_core.rb, pinned by
    # spec/core/shared_core_mirror_spec.rb). Only platform facts live
    # here; every validation rule is in the shared core. Used by both
    # UIKit and SwiftUI converters.
    class AttributeValidator < ::JsonUIShared::AttributeValidatorCore
      # Valid modes for this platform
      MODES = [:uikit, :swiftui, :all].freeze

      # Current platform identifier
      PLATFORM = 'swift'.freeze

      private

      def log_tag
        'SJUI'
      end

      # Only load definitions for the current mode to prevent type conflicts
      def extension_definition_paths
        paths = []
        if @mode == :swiftui || @mode == :all
          paths += [
            File.join(Dir.pwd, 'tools', 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions'),
            File.join(Dir.pwd, 'sjui_tools', 'lib', 'swiftui', 'views', 'extensions', 'attribute_definitions')
          ]
        end
        if @mode == :uikit || @mode == :all
          paths += [
            File.join(Dir.pwd, 'tools', 'sjui_tools', 'lib', 'uikit', 'extensions', 'attribute_definitions'),
            File.join(Dir.pwd, 'sjui_tools', 'lib', 'uikit', 'extensions', 'attribute_definitions')
          ]
        end
        paths
      end

      def styles_fallback_dirs
        # Get app name from current directory (for {app_name}/{app_name}/Styles pattern)
        app_name = File.basename(Dir.pwd)
        [
          File.join(Dir.pwd, 'Styles'),
          File.join(Dir.pwd, 'styles'),
          File.join(Dir.pwd, 'Layouts', 'Styles'),
          File.join(Dir.pwd, 'Layouts', 'styles'),
          # iOS app pattern: {app_name}/{app_name}/Styles
          File.join(Dir.pwd, app_name, 'Styles'),
          File.join(Dir.pwd, app_name, 'styles')
        ]
      end

      def config_file_name
        'sjui.config.json'
      end
    end
  end
end
