# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/react_generator'
require 'react/converters/view_converter'

# Regression: rjui-parent-invisible-class-lands-on-a-descendant
#
# inject_class_expression ran over the converter's whole subtree and took the
# first className it found — template literals before static strings. A child
# with its own visibility binding produces a template literal, so the parent's
# `invisible` class landed on that child and the parent rendered fully
# visible. The injection is now scoped to the subtree root's opening tag.
RSpec.describe 'invisible-class injection scope' do
  let(:config) { { 'use_tailwind' => true } }

  # A generated extension converter: emits its element, no self-wrapping.
  let(:extension_converter_class) do
    Class.new(RjuiTools::React::Converters::BaseConverter) do
      def convert(indent = 2)
        %(#{indent_str(indent)}<PageIndicator className="#{build_class_name}" />)
      end
    end
  end

  let(:config_with_ext) do
    config.merge('_extension_converters' => { 'PageIndicator' => extension_converter_class })
  end

  # The reported shape: a container with its own visibility binding whose
  # child is a custom component with a different visibility binding.
  let(:node) do
    {
      'type' => 'View',
      'id' => 'candidate_section',
      'orientation' => 'vertical',
      'visibility' => '@{candidateVisibility}',
      'child' => [
        { 'type' => 'Label', 'id' => 'question_label', 'text' => 'q' },
        { 'type' => 'PageIndicator', 'id' => 'page_indicator',
          'visibility' => '@{indicatorVisibility}' }
      ]
    }
  end

  let(:result) do
    RjuiTools::React::Converters::ViewConverter.new(node, config_with_ext).convert_node
  end

  it 'keeps the container’s own invisible class on the container' do
    container_line = result.lines.find { |l| l.include?('id="candidate_section"') }
    expect(container_line).to include('data.candidateVisibility === "invisible" ? "invisible" : ""')
  end

  it 'does not move the container’s condition onto the child' do
    child_line = result.lines.find { |l| l.include?('<PageIndicator') }
    expect(child_line).to include('data.indicatorVisibility === "invisible" ? "invisible" : ""')
    expect(child_line).not_to include('data.candidateVisibility')
  end

  it 'emits each condition exactly once' do
    expect(result.scan('data.candidateVisibility === "invisible"').length).to eq(1)
    expect(result.scan('data.indicatorVisibility === "invisible"').length).to eq(1)
  end

  it 'still guards both nodes with their own gone condition' do
    expect(result).to include('data.candidateVisibility !== "gone" && (')
    expect(result).to include('data.indicatorVisibility !== "gone" && (')
  end

  describe 'opening-tag scanning' do
    let(:converter) { RjuiTools::React::Converters::ViewConverter.new({ 'type' => 'View' }, config) }

    it 'does not end the tag on a `>` inside a brace expression' do
      jsx = %(  <Foo onChange={(e) => handle(e)} className="a b" />)
      out = converter.send(:inject_class_expression, jsx, '${x}')
      expect(out).to include('className={`a b ${x}`}')
      expect(out).to include('onChange={(e) => handle(e)}')
    end

    it 'does not end the tag on a `>` inside a string prop' do
      jsx = %(  <Foo label="a > b" className="c" />)
      out = converter.send(:inject_class_expression, jsx, '${x}')
      expect(out).to include('className={`c ${x}`}')
    end

    it 'upgrades a template-literal className on the root tag' do
      jsx = %(  <Foo className={`a ${y}`}>\n    <Bar className="z" />\n  </Foo>)
      out = converter.send(:inject_class_expression, jsx, '${x}')
      expect(out).to include('className={`a ${y} ${x}`}')
      expect(out).to include('<Bar className="z" />')
    end

    it 'leaves the subtree alone when the root tag has no className' do
      jsx = %(  <MainMenu id="m" />\n  <Other className="z" />)
      out = converter.send(:inject_class_expression, jsx, '${x}')
      expect(out).to eq(jsx)
    end
  end
end
