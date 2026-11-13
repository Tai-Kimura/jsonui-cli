# frozen_string_literal: true

module KjuiTools
  module Compose
    module Helpers
      # A component's text size as KotlinJsonUI's text size rule draws it (ticket
      # sjui-label-font-size-ignores-dynamic-type; shared/core/font_scale_vectors.json): every emitted font size,
      # and every line height derived from one, goes through `jsonUIFontSize(<size>)`, with the component's
      # `fontScaling` / `maxFontScale` when it declares them (literal only, as attribute_definitions types them).
      # Undeclared, the call reads KotlinJsonUI's Configuration.Font.scaling / maxScale, so an app's default reaches
      # the generated code too.
      module FontScale
        module_function

        # `, fontScaling = false, maxFontScale = 1.5f` for what the component declares; '' when nothing.
        def declaration_args(json_data)
          return '' unless json_data.is_a?(Hash)

          args = []
          scaling = json_data['fontScaling']
          args << "fontScaling = #{scaling}" if [true, false].include?(scaling)
          max = json_data['maxFontScale']
          args << "maxFontScale = #{float_literal(max)}" if max.is_a?(Numeric)
          args.empty? ? '' : ", #{args.join(', ')}"
        end

        # `jsonUIFontSize(<expr>[, declarations])`; nil stays nil.
        def wrap(expr, json_data, required_imports = nil)
          return expr if expr.nil?

          required_imports&.add(:json_ui_font_size)
          "jsonUIFontSize(#{expr}#{declaration_args(json_data)})"
        end

        # `jsonUILetterSpacing(<declarations>)`: the text style's letter spacing by the same rule as the size
        # (shared/core/font_scale_vectors.json rule.letterSpacing), the companion of every emitted text size.
        def letter_spacing(json_data, required_imports = nil)
          required_imports&.add(:json_ui_letter_spacing)
          "jsonUILetterSpacing(#{declaration_args(json_data).sub(/\A, /, '')})"
        end

        # `jsonUIFontSize(TextUnit.Unspecified, <declarations>)` for a component that declares fontScaling /
        # maxFontScale but no fontSize: the size it draws (the text style's), by its declarations (rule.noFontSize);
        # nil when it declares neither - the library leaves an unspecified size alone then, so nothing is emitted
        # and the generated code stays as it was.
        def undeclared_size(json_data, required_imports = nil)
          return nil if declaration_args(json_data).empty?

          required_imports&.add(:text_unit)
          wrap('TextUnit.Unspecified', json_data, required_imports)
        end

        # The declarations as named arguments of a call that takes them (PartialAttributesText): '' when none.
        def call_args(json_data)
          declaration_args(json_data)
        end

        def float_literal(value)
          f = value.to_f
          (f == f.to_i ? f.to_i.to_s : f.to_s) + 'f'
        end
      end
    end
  end
end
