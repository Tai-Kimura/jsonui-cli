# frozen_string_literal: true

require_relative '../core/type_synonyms'

module SjuiTools
  module SwiftUI
    # What a Debug build (SwiftJsonUI Dynamic) draws for the app's own
    # components, compared with what sjui's codegen draws, from the project's
    # own files. It names what differs and rewrites nothing.
    #
    # 1. A type the app's converters draw (views/extensions,
    #    converter_mappings.rb) that CustomComponentRegistration.swift does not
    #    register an adapter for: Debug draws the built-in its spelling names,
    #    or nothing. And an adapter registered for a type no converter draws —
    #    a component's, not a screen's (`sjui g adapter`, snake_case).
    # 2. An adapter whose source does not apply the standard modifiers
    #    (DynamicModifierHelper.applyStandardModifiers): Debug draws none of the
    #    node's common stages — its tap, onAppear, frame, background — which
    #    the codegen applies. (A Debug build says so too, once per type, when
    #    such a node is drawn.)
    # A file it cannot read is named, not skipped.
    module AppComponentDynamicCheck
      module_function

      # The lines to say, given the adapter directory the generators use
      # (nil: none configured) and the types the converters draw. Nothing when
      # the directory has no CustomComponentRegistration.swift: whether the
      # project draws in Dynamic mode is not known then.
      def warnings(adapter_dir, mappings:)
        return [] unless adapter_dir

        registration = File.join(adapter_dir, 'CustomComponentRegistration.swift')
        return [] unless File.exist?(registration)

        source = read(registration)
        return ["Could not read #{registration} (#{source}) — the Dynamic adapters were not compared with the app's converters"] unless source.is_a?(Array)

        list = source.first[/adapters\s*:\s*\[CustomComponentAdapter\]\s*=\s*\[(.*?)\]/m, 1].to_s
        lines = []
        registered = {}
        list.scan(/(\w+)\s*\(\s*\)/).flatten.each do |adapter|
          file = File.join(adapter_dir, "#{adapter}.swift")
          text = File.exist?(file) ? read(file) : nil
          if text.is_a?(String)
            lines << "Could not read #{file} (#{text}) — its adapter was not compared with the converters"
            next
          end
          type = text && text.first[/componentType\s*:\s*String\s*\{\s*"([^"]+)"/, 1] || adapter.sub(/Adapter\z/, '')
          # A screen `sjui g adapter` registers (a TabView tab's view) is
          # snake_case; a component type is not.
          registered[type] = text&.first if type.match?(/\A[A-Z]/)
        end
        lines += (mappings - registered.keys).map do |type|
          "'#{type}' is drawn by the app in release but has no Dynamic adapter registered — Debug draws #{built_in(type)}"
        end
        lines += (registered.keys - mappings).map do |type|
          "'#{type}' has a Dynamic adapter registered but no converter draws it — release draws #{built_in(type)}"
        end
        (mappings & registered.keys).each do |type|
          adapter_source = registered[type]
          next if adapter_source.nil? || adapter_source.include?('applyStandardModifiers(')

          lines << "'#{type}''s adapter does not apply the standard modifiers — Debug draws none of the node's common stages " \
                   '(its tap, onAppear, frame, background), which release draws. Call DynamicModifierHelper.applyStandardModifiers ' \
                   'on the view buildView returns, as a generated adapter does.'
        end
        lines
      end

      # The built-in a spelling draws as without the app's converter.
      def built_in(type)
        drawn = JsonUIShared::ComponentAliases.canonical(JsonUIShared::TypeSynonyms.drawn_as(type))
        drawn == type ? 'no built-in of its own (an undeclared type, unless a built-in has that name)' : "the built-in '#{drawn}'"
      end

      # [text] from a UTF-8 file, else the reason it could not be read.
      def read(path)
        text = File.read(path, encoding: 'UTF-8')
        return 'it is not UTF-8' unless text.valid_encoding?

        [text]
      rescue StandardError => e
        "#{e.class}: #{e.message}"
      end
    end
  end
end
