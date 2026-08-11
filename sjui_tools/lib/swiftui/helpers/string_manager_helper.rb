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

        # warnings: false is the data-default face (data_model_updater). A
        # `defaultValue` is not declared display text — it can be sentinel
        # vocabulary (a DateSelectBox's "today", a visibility's "gone") or
        # an enum-ish literal that happens to collide with some section's
        # key name — so resolution stays best-effort and SILENT there:
        # resolve when the layout's own sections (or a fully-qualified
        # spelling, or a value match) claim it, keep the literal otherwise,
        # and never gate the build over it (a date sentinel made zero-warning
        # unreachable by authoring, 2026-08-11 filing).
        def get_text_with_string_manager(text_content, warnings: true)
          # Remove quotes if present
          text_without_quotes = text_content.gsub(/^\"|\"|^'|'$/, '')

          # Check if it's a binding (starts with @{)
          return text_content if text_without_quotes.match?(/^@\{.*\}$/)

          # A text that IS a declared strings.json key resolves as that key,
          # before any value reverse-lookup or spelling heuristic: membership
          # in the SSoT is what makes something a key, not how it is spelled.
          # The extractor truncates long ASCII text to 31 chars, which can
          # leave a trailing underscore ("dont_have_an_account_apply_for_") —
          # a spelling the old snake_case gate rejected, so a declared key
          # fell through to the raw literal (downstream login screen, 2026-08-09).
          string_manager_call = lookup_string_manager_key(text_without_quotes)
          return string_manager_call if string_manager_call

          # Then, try to find by value in strings.json (for non-snake_case text like "AppFinder")
          string_manager_call = lookup_string_manager_by_value(text_without_quotes, warnings: warnings)
          return string_manager_call if string_manager_call

          # Undeclared snake_case-shaped text falls back to .localized().
          # Same spelling the extractor's should_extract_string? skips,
          # trailing underscore included.
          if text_without_quotes.match?(/^[a-z][a-z0-9]*(_[a-z0-9]+)*_?$/)
            # If the bare key IS declared — just under a section this layout
            # does not own — the .localized() below is known-unresolvable
            # (the section-prefixed key never lands in Localizable.strings
            # under the bare spelling) and the RAW KEY reaches the screen.
            # Silence here let exactly that ship (asymmetric-resolution
            # filing, 2026-08-11); the warning gates via `jui build`'s
            # zero-warning invariant.
            report_foreign_bare_key(text_without_quotes) if warnings
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
        def lookup_string_manager_by_value(text, warnings: true)
          strings_data = load_strings_json
          return nil if strings_data.nil? || strings_data.empty?

          resolved = JsonUIShared::StringManagerCore.resolve_string_reference(
            strings_data, text, StringManagerHelper.current_namespaces || []
          )
          return nil if resolved.nil?

          report_string_namespace(text, resolved) if warnings
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

        # A bare key declared ONLY under sections this layout does not own is
        # a broken reference under the own-section canon (kjui's resolver
        # carries the same check) — a bare key resolves in the layout's own
        # sections, and cross-section reach is the fully-qualified spelling.
        def report_foreign_bare_key(text)
          strings_data = load_strings_json
          return unless strings_data.is_a?(Hash)

          own = StringManagerHelper.current_namespaces || []
          # map + compact, not filter_map — see order_sections_by_ownership.
          foreign = strings_data.map do |namespace, entries|
            namespace if entries.is_a?(Hash) && entries.key?(text) && !own.include?(namespace)
          end.compact
          return if foreign.empty?

          Core::Logger.warn(
            "Bare key #{text.inspect} is declared only in foreign strings.json " \
            "section(s) #{foreign.join(', ')} — a bare key resolves within the " \
            "layout's own sections (#{own.join(' / ')}). Use the fully-qualified " \
            "'<section>_<key>' spelling for a deliberate cross-section reference, " \
            "or register the key under the layout's own section (jsonui-localize)."
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

            # Check if text matches just the key (without file prefix) — but
            # ONLY within sections this layout owns. The prefixed form above
            # names its section explicitly, so a foreign hit is a deliberate
            # reference; a BARE key hitting a foreign section is a collision,
            # not a reference. A literal data default of "sample" resolved to
            # another fixture's key "sample" (value "Sample") this way and the
            # codegen face drew the wrong string while every other face drew
            # the literal (Radio/Switch label__binding parity, run
            # 31202080745).
            own = StringManagerHelper.current_namespaces || []
            if own.include?(file_name) && file_strings.key?(text)
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

          # `map` + `compact`, not `filter_map`: the latter is Ruby 2.7+ and
          # this tool can reach a consumer's system Ruby, which is 2.6 on
          # macOS. `sjui_tools/.ruby-version` pins 3.2.2 and `jui sync_tool`
          # propagates that pin to the platform root, so the pin normally
          # binds — but it binds only where rbenv is installed, and the cost
          # of not depending on it is one method call. kjui found this the
          # expensive way: it ships no `.ruby-version` at all, and 252 layouts
          # failed silently under 2.6 (plan 49 lane C).
          owned = own.map { |namespace| [namespace, strings_data[namespace]] if strings_data.key?(namespace) }.compact
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