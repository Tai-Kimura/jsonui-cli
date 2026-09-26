# frozen_string_literal: true

require_relative 'base_view_converter'
require_relative 'responsive_helper'

module SjuiTools
  module SwiftUI
    module Views
      # A node with `responsive` whose own converter does not draw the
      # overrides — every type but a View / SafeAreaView with children, a
      # Collection and an Embed; an app's generated converter routes itself —
      # drawn per size class: a function with the node's view in each branch,
      # the branch's attributes merged (ResponsiveHelper.generate_leaf_function),
      # as a generated converter draws its node. The override was dropped,
      # silently, on 21 of the 25 declared types (a Label's, an Image's, a
      # TextField's, a ScrollView's, a View's without children …), while kjui,
      # rjui and both Dynamic runtimes draw it (ticket
      # sjui-codegen-drops-a-leafs-responsive).
      class ResponsiveLeafConverter < BaseViewConverter
        def initialize(component, indent_level, action_manager, converter_factory, view_registry, binding_registry)
          super(component, indent_level, action_manager, binding_registry)
          @converter_factory = converter_factory
          @view_registry = view_registry
        end

        def convert
          name = @converter_factory.next_responsive_name
          branch_states = []
          @converter_factory.register_responsive_function(
            ResponsiveHelper.generate_leaf_function(
              name, @component, @converter_factory, @indent_level, @action_manager, @view_registry, @binding_registry,
              branch_states
            )
          )
          @state_variables.concat(one_per_name(branch_states))
          add_line "#{name}()"
          generated_code
        end

        private

        # Every branch draws the same node, so it declares the same state:
        # one declaration per name, the last branch's — the one without a
        # size class, the node's own values.
        def one_per_name(lines)
          lines.reverse.uniq { |line| line[/private\s+var\s+(\w+)/, 1] || line }.reverse
        end
      end
    end
  end
end
