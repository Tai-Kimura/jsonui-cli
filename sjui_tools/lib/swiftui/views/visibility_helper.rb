require_relative '../binding/binding_expression'

module SjuiTools
  module SwiftUI
    module Views
      module VisibilityHelper
        def apply_visibility_wrapper(child)
          if child['visibility']
            # Canonical expression parsing (path / '?? default' / '!path')
            # shared with view_binding_handler#parse_binding — no more
            # to_camel_case mangling of '??' and '!'
            visibility_param = SwiftUI::Binding::BindingExpression.swift_visibility_param(child['visibility'])

            # Create child converter with extra indent level for content inside VisibilityWrapper
            child_converter = @converter_factory.create_converter(child, @indent_level + 1, @action_manager, @converter_factory, @view_registry)
            child_code = child_converter.convert

            # Add VisibilityWrapper wrapper
            add_line "VisibilityWrapper(#{visibility_param}) {"
            # Child converter was created with @indent_level + 1, so lines already have correct indentation
            child_code.split("\n").each { |line| @generated_code << line }
            add_line "}"

            # Return the child_converter for state propagation
            child_converter
          else
            nil
          end
        end
      end
    end
  end
end
