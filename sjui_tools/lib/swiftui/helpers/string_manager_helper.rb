# frozen_string_literal: true

require 'json'
require 'pathname'
require_relative '../../core/config_manager'
require_relative '../../core/project_finder'
require_relative '../../core/logger'
require_relative '../../core/string_manager_core'

module SjuiTools
  module SwiftUI
    module Helpers
      module StringManagerHelper
        class << self
          # The layout currently being converted, as the strings.json
          # section spellings it owns (StringManagerCore#namespace_candidates).
          # Class-level per-file state, the same pattern as
          # BaseViewConverter.layout_normalized — every converter resolves
          # strings, so threading a path through their constructors would
          # touch every call site to say one thing.
          #
          # Empty means "no layout context": resolution then falls back to
          # strings.json order, which is what every caller got before.
          attr_accessor :current_namespaces
        end
        self.current_namespaces = []

        # Announce the layout about to be converted. Accepts the path as
        # written on disk; the layouts-dir-relative part is what names a
        # section.
        def self.begin_layout(json_file_path)
          self.current_namespaces = JsonUIShared::StringManagerCore.namespace_candidates(
            layout_relative_path(json_file_path), preferred: :basename
          )
        rescue StandardError
          self.current_namespaces = []
        end

        def self.layout_relative_path(json_file_path)
          source_path = Core::ProjectFinder.get_full_source_path
          return File.basename(json_file_path.to_s) if source_path.nil?

          config = Core::ConfigManager.load_config
          layouts_dir = File.join(source_path, config['layouts_directory'] || 'Layouts')
          relative = Pathname.new(File.expand_path(json_file_path.to_s))
                             .relative_path_from(Pathname.new(File.expand_path(layouts_dir))).to_s
          relative.start_with?('..') ? File.basename(json_file_path.to_s) : relative
        rescue StandardError
          File.basename(json_file_path.to_s)
        end

        def get_text_with_string_manager(text_content)
          # Remove quotes if present
          text_without_quotes = text_content.gsub(/^\"|\"|^'|'$/, '')

          # Check if it's a binding (starts with @{)
          return text_content if text_without_quotes.match?(/^@\{.*\}$/)

          # First, try to find by value in strings.json (for non-snake_case text like "AppFinder")
          string_manager_call = lookup_string_manager_by_value(text_without_quotes)
          return string_manager_call if string_manager_call

          # Then, check if it's snake_case key format
          if text_without_quotes.match?(/^[a-z]+(_[a-z0-9]+)*$/)
            # Try to find by key in strings.json
            string_manager_call = lookup_string_manager_key(text_without_quotes)
            return string_manager_call if string_manager_call

            # Fallback to .localized() extension for snake_case strings
            return "\"#{text_without_quotes}\".localized()"
          end

          # Return original text content for non-matched strings
          text_content
        end

        private

        # Lookup by value (e.g., "AppFinder" -> StringManager.Login.appfinder())
        #
        # Resolution order is the shared core's, not strings.json's: the
        # sections this layout owns win over a section that merely holds
        # the same text. Scanning in file order made the reference depend
        # on how the SSoT happened to be sorted, and a cell under a screen
        # directory — which owns two spellings — could land on either one.
        def lookup_string_manager_by_value(text)
          strings_data = load_strings_json
          return nil if strings_data.nil? || strings_data.empty?

          resolved = JsonUIShared::StringManagerCore.resolve_string_reference(
            strings_data, text, StringManagerHelper.current_namespaces || []
          )
          return nil if resolved.nil?

          report_string_namespace(text, resolved)
          struct_name = snake_to_pascal(resolved['namespace'])
          method_name = snake_to_camel(resolved['key'])
          "StringManager.#{struct_name}.#{method_name}()"
        end

        # Both conditions are SSoT damage rather than build errors, so
        # they warn: `jui build`'s zero-warning invariant makes them gate
        # anyway, and `jui lint-strings` reports the same pair statically.
        def report_string_namespace(text, resolved)
          own = StringManagerHelper.current_namespaces || []
          candidates = resolved['candidates'] || []

          if candidates.length > 1
            Core::Logger.warn(
              "String #{text.inspect} is declared in #{candidates.length} strings.json " \
              "sections (#{candidates.join(', ')}) — resolved to " \
              "#{resolved['namespace']}. Two sections holding one string is a forked " \
              'SSoT: delete the duplicate so every platform reads the same key.'
            )
          end

          return unless resolved['foreign'] && own.any?

          Core::Logger.warn(
            "String #{text.inspect} resolved to section #{resolved['namespace']}, which " \
            "this layout does not own (#{own.join(' / ')}) — the SSoT never declared it " \
            'here. Register the string under the layout\'s own section (jsonui-localize).'
          )
        end

        def lookup_string_manager_key(text)
          strings_data = load_strings_json
          return nil if strings_data.nil?

          # Own sections first, for the same reason value lookup does it:
          # a bare key like "rating" exists in as many sections as declare
          # it, and file order decided which one won.
          strings_data = order_sections_by_ownership(strings_data)

          # Check each file's strings
          strings_data.each do |file_name, file_strings|
            next unless file_strings.is_a?(Hash)

            # Check if text matches file_key pattern (e.g., "login_forgot_password")
            if text.start_with?("#{file_name}_")
              key = text.sub(/^#{file_name}_/, '')
              # Key exists in strings.json (has proper value)
              if file_strings.key?(key)
                struct_name = snake_to_pascal(file_name)
                method_name = snake_to_camel(key)
                return "StringManager.#{struct_name}.#{method_name}()"
              end
            end

            # Check if text matches just the key (without file prefix)
            if file_strings.key?(text)
              struct_name = snake_to_pascal(file_name)
              method_name = snake_to_camel(text)
              return "StringManager.#{struct_name}.#{method_name}()"
            end
          end

          nil
        end

        # strings.json re-ordered so the layout's own sections come first;
        # everything else keeps its file order.
        def order_sections_by_ownership(strings_data)
          own = StringManagerHelper.current_namespaces || []
          return strings_data if own.empty?

          owned = own.filter_map { |namespace| [namespace, strings_data[namespace]] if strings_data.key?(namespace) }
          return strings_data if owned.empty?

          rest = strings_data.reject { |namespace, _| own.include?(namespace) }
          owned.to_h.merge(rest)
        end

        def load_strings_json
          @strings_json_cache ||= begin
            source_path = Core::ProjectFinder.get_full_source_path
            return {} if source_path.nil?

            config = Core::ConfigManager.load_config
            layouts_dir = config['layouts_directory'] || 'Layouts'
            strings_file = File.join(source_path, layouts_dir, 'Resources', 'strings.json')

            if File.exist?(strings_file)
              JSON.parse(File.read(strings_file))
            else
              {}
            end
          rescue JSON::ParserError, TypeError
            {}
          end
        end

        def snake_to_pascal(snake_str)
          snake_str.split('_').map(&:capitalize).join
        end

        def snake_to_camel(snake_str)
          parts = snake_str.split('_')

          # Handle pure numbers
          if parts.length == 1 && parts[0].match?(/^\d+$/)
            return "value#{parts[0]}"
          end

          # Handle trailing numbers
          if parts.length > 1 && parts.last.match?(/^\d+$/)
            parts[-2] = parts[-2] + parts[-1]
            parts.pop
          end

          parts[0] + parts[1..-1].map(&:capitalize).join
        end
      end
    end
  end
end