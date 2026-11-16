# frozen_string_literal: true

require_relative '../../spec_helper'
# The whole converter set: get_converter_class builds its map eagerly, so a
# partial require raises NameError on the first unrelated entry.
require 'react/react_generator'
require 'react/converters/view_converter'
require 'react/converters/label_converter'
require 'react/converters/include_converter'

# Regression: rjui-codeblock-visibility-dropped
#
# `visibility` was applied by each converter calling wrap_with_visibility
# inside its own `convert`. Converters scaffolded by `rjui g converter` never
# did, so the attribute was read, validated, and then silently dropped — the
# node rendered unconditionally with no warning. The wrap now happens at the
# dispatchers' entry point (BaseConverter#convert_node), so a converter cannot
# forget it.
RSpec.describe 'visibility on custom-component converters' do
  let(:config) { { 'use_tailwind' => true } }

  # Stands in for a generated extension converter: emits its element and does
  # NOT call wrap_with_visibility. This is the shape `rjui g converter` emits.
  let(:extension_converter_class) do
    Class.new(RjuiTools::React::Converters::BaseConverter) do
      def convert(indent = 2)
        %(#{indent_str(indent)}<CodeBlock className="#{build_class_name}" />)
      end
    end
  end

  describe 'BaseConverter#convert_node' do
    it 'guards a custom component whose converter never wraps' do
      node = { 'type' => 'CodeBlock', 'visibility' => '@{optionsVisibility}' }
      result = extension_converter_class.new(node, config).convert_node

      expect(result).to include('data.optionsVisibility !== "gone" && (')
      expect(result).to include('data.optionsVisibility === "invisible" ? "invisible" : ""')
    end

    it 'leaves a custom component without visibility untouched' do
      node = { 'type' => 'CodeBlock' }
      result = extension_converter_class.new(node, config).convert_node

      expect(result).not_to include('!== "gone"')
      expect(result.lines.length).to eq(1)
    end

    it 'applies a bound `hidden` on a custom component too' do
      node = { 'type' => 'CodeBlock', 'hidden' => '@{isBusy}' }
      result = extension_converter_class.new(node, config).convert_node

      expect(result).to include('data.isBusy ? "invisible" : ""')
    end

    it 'does not double-wrap a converter that already wraps in `convert`' do
      node = { 'type' => 'Label', 'text' => 'hi', 'visibility' => '@{show}' }
      result = RjuiTools::React::Converters::LabelConverter.new(node, config).convert_node

      expect(result.scan('data.show !== "gone" && (').length).to eq(1)
    end

    it 'guards an include site — IncludeConverter never wrapped either' do
      node = { 'include' => 'main_menu', 'visibility' => '@{showMenu}' }
      result = RjuiTools::React::Converters::IncludeConverter.new(node, config).convert_node

      expect(result).to include('data.showMenu !== "gone" && (')
      expect(result).to include('<MainMenu')
    end
  end

  describe 'children dispatch' do
    it 'guards a custom component nested inside a View' do
      node = {
        'type' => 'View',
        'child' => [
          { 'type' => 'Label', 'text' => 'heading', 'visibility' => '@{optionsVisibility}' },
          { 'type' => 'CodeBlock', 'visibility' => '@{optionsVisibility}' }
        ]
      }
      config_with_ext = config.merge(
        '_extension_converters' => { 'CodeBlock' => extension_converter_class }
      )
      result = RjuiTools::React::Converters::ViewConverter.new(node, config_with_ext).convert_node

      # Both siblings get the same guard — the point of the report was that
      # the same attribute behaved differently per node type.
      expect(result.scan('data.optionsVisibility !== "gone" && (').length).to eq(2)
    end
  end
end
