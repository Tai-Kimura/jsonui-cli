# frozen_string_literal: true

require 'json'

module SjuiTools
  module SwiftUI
    module Views
      # The set of values a declared attribute accepts, read from the SSoT.
      #
      # A converter that resolves an enum at GENERATION time never needs this —
      # it switches on the string in front of it and the normalizer has
      # already rewritten alias spellings into canonical ones. A converter
      # that resolves an enum at RUN time does, and for a reason that is easy
      # to miss:
      #
      #   `valueAliases` are applied by `jui build` to the DECLARATION. A
      #   `@{...}` is not a declaration — its value appears at run time and
      #   never passes through the normalizer.
      #
      # So a table materialized into the emitted Swift has to carry the alias
      # spellings too, or `data.contentType == "emailAddress"` misses a table
      # that only knows the canonical `email` and the binding falls to the
      # default — a fresh `bound-frozen`, created by the fix for the old one
      # (2026-08-05 orchestrator ruling, plan 49 lane B).
      #
      # The vocabulary lives in `shared/core/attribute_definitions.json` and
      # only there. What each tool owns is the mapping from a token to ITS
      # platform's spelling, which the SSoT has no opinion about.
      module AttributeVocabulary
        # Deployed copies mirror the SSoT into lib/core/ next to the
        # validator; the source repo keeps it at shared/core/. Same chain
        # `Core::BindingValidatorCore#load_attribute_definitions` walks.
        CANDIDATES = [
          File.expand_path('../../core/attribute_definitions.json', __dir__),
          File.expand_path('../../../shared/core/attribute_definitions.json', __dir__),
          File.expand_path('../../../../shared/core/attribute_definitions.json', __dir__),
          File.expand_path('~/.jsonui-cli/shared/core/attribute_definitions.json')
        ].freeze

        module_function

        def definitions
          @definitions ||= begin
            path = CANDIDATES.find { |p| p && File.exist?(p) }
            path ? JSON.parse(File.read(path)) : {}
          rescue JSON::ParserError
            {}
          end
        end

        # Test-only seam.
        def reset!
          @definitions = nil
        end

        def declaration(component, attribute)
          defs = definitions
          section = defs[component]
          section = defs[section['_alias_of']] if section.is_a?(Hash) && section['_alias_of'].is_a?(String)
          value = section.is_a?(Hash) ? section[attribute] : nil
          return value if value.is_a?(Hash)

          common = defs['common']
          common.is_a?(Hash) && common[attribute].is_a?(Hash) ? common[attribute] : nil
        end

        # Every spelling the SSoT accepts for this attribute: the enum plus
        # the alias keys. Empty when the attribute declares no vocabulary.
        def tokens(component, attribute)
          declared = declaration(component, attribute)
          return [] unless declared

          list = Array(declared['enum'])
          aliases = declared['valueAliases']
          list += aliases.keys if aliases.is_a?(Hash)
          list.map(&:to_s).uniq
        end

        # `emailAddress` -> `email`, per the SSoT's own alias table.
        def canonical_token(component, attribute, token)
          declared = declaration(component, attribute)
          aliases = declared && declared['valueAliases']
          return token.to_s unless aliases.is_a?(Hash)

          (aliases[token.to_s] || token).to_s
        end

        # *mapping* is the tool's own `json token (lowercased) -> platform
        # literal` table. This returns it widened to every spelling the SSoT
        # declares, resolving an alias to whatever its canonical spelling
        # maps to.
        #
        # A declared token the tool cannot map is a real gap and says so on
        # stderr rather than disappearing: silence is how `contentType`'s
        # `newPassword` went unmapped for a release.
        def widen(component, attribute, mapping)
          table = mapping.dup
          tokens(component, attribute).each do |token|
            key = token.downcase
            next if table.key?(key)

            literal = mapping[canonical_token(component, attribute, token).downcase]
            if literal.nil?
              warn "[AttributeVocabulary] #{component}.#{attribute}: no swiftui mapping for the declared value '#{token}'"
              next
            end
            table[key] = literal
          end
          table
        end
      end
    end
  end
end
