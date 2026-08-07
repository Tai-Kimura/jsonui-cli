# frozen_string_literal: true

require_relative 'value_expression_helper'
require_relative 'attribute_vocabulary'

module SjuiTools
  module SwiftUI
    module Views
      # The three text vocabularies the SSoT declares as enums — text
      # alignment, keyboard/input type and autofill content type — and their
      # SwiftUI spellings.
      #
      # One table each, because a vocabulary that exists twice drifts (plan
      # 40). Two of them already did: `text_alignment_to_swiftui` was a
      # private copy in both the Label and the TextField converter, and
      # TextView — which reads the same declared `textAlign` — had neither and
      # emitted nothing at all.
      #
      # Each table has a bound sibling that resolves the SAME table at run
      # time (see `ValueExpressionHelper#bound_enum`), so a declaration keeps
      # its meaning when it is written as `@{...}`.
      module TextStyleHelper
        include ValueExpressionHelper

        #: JSON spelling -> SwiftUI `TextAlignment`. `Left`/`Center`/`Right`
        #: are the declared enum; the leading/trailing spellings are accepted
        #: because they were before this table had one home.
        TEXT_ALIGNMENTS = {
          'left' => '.leading',
          'leading' => '.leading',
          'right' => '.trailing',
          'trailing' => '.trailing',
          'center' => '.center'
        }.freeze

        #: JSON `input` -> `UIKeyboardType`.
        #
        # `alphabet` (and the historical `allphabet` typo the SSoT still
        # declares) and `phone` and the lower-case `url` were missing, so
        # three of the nine declared values landed on `.default` next to the
        # value that MEANS default — the converter looked like it read the
        # attribute and did not. `password` is deliberately `.default`: the
        # secure entry is a SecureField, not a keyboard.
        KEYBOARD_TYPES = {
          'default' => '.default',
          'alphabet' => '.asciiCapable',
          'allphabet' => '.asciiCapable',
          'email' => '.emailAddress',
          'number' => '.numberPad',
          'decimal' => '.decimalPad',
          'phone' => '.phonePad',
          'url' => '.URL',
          'password' => '.default',
          'twitter' => '.twitter',
          'websearch' => '.webSearch',
          'namephonepad' => '.namePhonePad'
        }.freeze

        #: JSON `contentType` -> `UITextContentType`. Kept in step with rjui's
        #: `map_content_type` (autocomplete) and kjui's keyboard handling.
        CONTENT_TYPES = {
          'username' => '.username',
          'password' => '.password',
          'newpassword' => '.newPassword',
          'onetimecode' => '.oneTimeCode',
          'email' => '.emailAddress',
          'emailaddress' => '.emailAddress',
          'name' => '.name',
          'givenname' => '.givenName',
          'familyname' => '.familyName',
          'tel' => '.telephoneNumber',
          'telephonenumber' => '.telephoneNumber',
          'streetaddress' => '.streetAddressLine1',
          'postalcode' => '.postalCode',
          'country' => '.countryName',
          'creditcardnumber' => '.creditCardNumber',
          'url' => '.URL'
        }.freeze

        def text_alignment_to_swiftui(alignment)
          TEXT_ALIGNMENTS[alignment.to_s.downcase] || '.leading'
        end

        def bound_text_alignment(value)
          bound_enum(value, vocabulary('textAlign', TEXT_ALIGNMENTS),
                     default: '.leading', type: 'TextAlignment')
        end

        def input_to_keyboard_type(input)
          KEYBOARD_TYPES[input.to_s.downcase] || '.default'
        end

        def bound_keyboard_type(value)
          bound_enum(value, vocabulary('input', KEYBOARD_TYPES),
                     default: '.default', type: 'UIKeyboardType')
        end

        # Unknown values warn instead of silently degrading to `.none`
        # (sjui-textfield-contenttype-newpassword-not-mapped).
        def map_content_type(type)
          mapped = CONTENT_TYPES[type.to_s.downcase]
          return mapped if mapped

          puts "Warning: unknown contentType '#{type}' — emitting .textContentType(.none); add a mapping if this is a canonical value"
          '.none'
        end

        # `.textContentType` takes a `UITextContentType?`, so the bound form
        # leaves the lookup Optional: an unrecognised value at run time turns
        # the autofill hint off, which is what `.none` means statically.
        def bound_content_type(value)
          bound_enum(value, vocabulary('contentType', CONTENT_TYPES),
                     default: nil, type: 'UITextContentType')
        end

        # Whether a declared `underline` / `strikethrough` face asks for a
        # line to be drawn.
        #
        # Both are declared `boolean|object|array`, and the object face
        # carries `lineStyle`, whose enum spells "no line" as `None`. Every
        # read site tested the face for truthiness, so `{"lineStyle": "None"}`
        # — an object, therefore truthy — asked for a line, which is the one
        # thing that value cannot mean.
        #
        # The object face's CONTENTS (lineStyle, colour, lineOffset) are still
        # unemitted on ios: `PartialAttributedText` takes `underline: Bool`,
        # so there is nothing to hand them to yet. That is the
        # C2/presence-only row in codegen_effect.json, and it lands when the
        # library grows the styled parameters.
        def line_decoration?(face)
          return false if face.nil? || face == false
          return face['lineStyle'].to_s.downcase != 'none' if face.is_a?(Hash)

          true
        end

        # The tool's token -> SwiftUI table, widened to every spelling the
        # SSoT declares for this component's attribute. A run-time table has
        # to know the ALIAS spellings, which the build-time normalizer would
        # otherwise have rewritten before the converter ever saw them — a
        # binding never passes through it.
        def vocabulary(attribute, mapping)
          AttributeVocabulary.widen(@component && @component['type'] || 'View', attribute, mapping)
        end
      end
    end
  end
end
