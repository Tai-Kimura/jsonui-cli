# frozen_string_literal: true

require 'swiftui/views/child_renderer'

RSpec.describe SjuiTools::SwiftUI::Views::ChildRenderer do
  let(:renderer_class) do
    Class.new do
      include SjuiTools::SwiftUI::Views::ChildRenderer

      attr_accessor :converter_factory, :action_manager, :view_registry, :indent_level, :state_variables
      attr_reader :generated_code

      def initialize
        @generated_code = []
        @state_variables = []
        @indent_level = 0
      end

      def add_line(line)
        @generated_code << line
      end

      def indent
        @indent_level += 1
        yield
        @indent_level -= 1
      end

      def to_camel_case(str)
        str.gsub(/_([a-z])/) { Regexp.last_match(1).upcase }
      end

      def apply_zstack_positioning(child, index)
        # mirrors the real helper: offsets only, no positional zIndex stamp
        @generated_code << ".offset(x: 0, y: 0)"
      end
    end
  end

  let(:mock_child_converter) do
    converter = double('ChildConverter')
    allow(converter).to receive(:convert).and_return("Text(\"Child\")")
    allow(converter).to receive(:state_variables).and_return([])
    allow(converter).to receive(:respond_to?).with(:state_variables).and_return(true)
    converter
  end

  let(:mock_factory) do
    factory = double('ConverterFactory')
    allow(factory).to receive(:create_converter).and_return(mock_child_converter)
    factory
  end

  describe '#render_child_element' do
    let(:renderer) do
      r = renderer_class.new
      r.converter_factory = mock_factory
      r.action_manager = nil
      r.view_registry = nil
      r
    end

    context 'with ZStack (no orientation)' do
      it 'wraps child in Group' do
        child = { 'type' => 'View' }
        renderer.render_child_element(child, 0, nil, 0, 0)

        expect(renderer.generated_code).to include('Group {')
        expect(renderer.generated_code).to include('}')
        expect(renderer.generated_code).to include('.offset(x: 0, y: 0)')
      end
    end

    context 'with horizontal orientation and weight' do
      it 'sets parent_orientation for weighted child' do
        child = { 'type' => 'View' }
        renderer.render_child_element(child, 0, 'horizontal', 1, 2)

        expect(child['parent_orientation']).to eq('horizontal')
      end
    end

    context 'with vertical orientation and weight' do
      it 'sets parent_orientation for weighted child' do
        child = { 'type' => 'View' }
        renderer.render_child_element(child, 0, 'vertical', 2, 4)

        expect(child['parent_orientation']).to eq('vertical')
      end
    end

    context 'with visibility attribute' do
      it 'wraps child with VisibilityWrapper' do
        child = { 'type' => 'View', 'visibility' => '@{isVisible}' }
        renderer.render_child_element(child, 0, 'horizontal', 0, 0)

        expect(renderer.generated_code).to include('VisibilityWrapper(data.isVisible) {')
      end
    end
  end

  describe '#render_child_with_visibility' do
    let(:renderer) do
      r = renderer_class.new
      r.converter_factory = mock_factory
      r.action_manager = nil
      r.view_registry = nil
      r
    end

    context 'with binding visibility' do
      # Intended diff (renderer-ssot-15-4): canonical expression parsing —
      # the binding key is used verbatim (no to_camel_case mangling)
      it 'uses the binding path verbatim' do
        child = { 'type' => 'View', 'visibility' => '@{is_shown}' }
        renderer.send(:render_child_with_visibility, child, 'horizontal')

        expect(renderer.generated_code).to include('VisibilityWrapper(data.is_shown) {')
      end

      it 'emits a canonical ?? default without mangling' do
        child = { 'type' => 'View', 'visibility' => "@{vis ?? 'gone'}" }
        renderer.send(:render_child_with_visibility, child, 'horizontal')

        expect(renderer.generated_code).to include('VisibilityWrapper(data.vis ?? "gone") {')
      end
    end

    context 'with string visibility' do
      it 'uses quoted string' do
        child = { 'type' => 'View', 'visibility' => 'visible' }
        renderer.send(:render_child_with_visibility, child, 'horizontal')

        expect(renderer.generated_code).to include('VisibilityWrapper("visible") {')
      end
    end
  end

  describe '#render_child_with_alignment' do
    let(:renderer) do
      r = renderer_class.new
      r.converter_factory = mock_factory
      r.action_manager = nil
      r.view_registry = nil
      r
    end

    context 'with horizontal orientation' do
      context 'with alignTop' do
        it 'wraps in VStack with top alignment' do
          child = { 'type' => 'View', 'alignTop' => true }
          renderer.send(:render_child_with_alignment, child, 'horizontal')

          expect(renderer.generated_code).to include('VStack {')
          expect(renderer.generated_code.last).to include('.frame(maxHeight: .infinity, alignment: .top)')
        end
      end

      context 'with alignBottom' do
        it 'wraps in VStack with bottom alignment' do
          child = { 'type' => 'View', 'alignBottom' => true }
          renderer.send(:render_child_with_alignment, child, 'horizontal')

          expect(renderer.generated_code.last).to include('alignment: .bottom')
        end
      end

      context 'with centerVertical' do
        it 'wraps in VStack with center alignment' do
          child = { 'type' => 'View', 'centerVertical' => true }
          renderer.send(:render_child_with_alignment, child, 'horizontal')

          expect(renderer.generated_code.last).to include('alignment: .center')
        end
      end

      context 'with alignRight' do
        it 'adds spacer before' do
          child = { 'type' => 'View', 'alignRight' => true }
          renderer.send(:render_child_with_alignment, child, 'horizontal')

          expect(renderer.generated_code.first).to eq('Spacer()')
        end
      end

      context 'with alignLeft' do
        it 'adds spacer after' do
          child = { 'type' => 'View', 'alignLeft' => true }
          renderer.send(:render_child_with_alignment, child, 'horizontal')

          expect(renderer.generated_code.last).to eq('Spacer()')
        end
      end

      context 'with centerHorizontal' do
        it 'adds spacers before and after' do
          child = { 'type' => 'View', 'centerHorizontal' => true }
          renderer.send(:render_child_with_alignment, child, 'horizontal')

          expect(renderer.generated_code.first).to eq('Spacer()')
          expect(renderer.generated_code.last).to eq('Spacer()')
        end
      end

      context 'with centerInParent' do
        it 'adds spacers and wraps with center alignment' do
          child = { 'type' => 'View', 'centerInParent' => true }
          renderer.send(:render_child_with_alignment, child, 'horizontal')

          expect(renderer.generated_code).to include('Spacer()')
          expect(renderer.generated_code).to include('VStack {')
          expect(renderer.generated_code.find { |l| l.include?('.frame') }).to include('alignment: .center')
        end
      end
    end

    context 'with vertical orientation' do
      context 'with alignLeft' do
        it 'wraps in HStack with leading alignment' do
          child = { 'type' => 'View', 'alignLeft' => true }
          renderer.send(:render_child_with_alignment, child, 'vertical')

          expect(renderer.generated_code).to include('HStack {')
          expect(renderer.generated_code.last).to include('.frame(maxWidth: .infinity, alignment: .leading)')
        end
      end

      context 'with alignRight' do
        it 'wraps in HStack with trailing alignment' do
          child = { 'type' => 'View', 'alignRight' => true }
          renderer.send(:render_child_with_alignment, child, 'vertical')

          expect(renderer.generated_code.last).to include('alignment: .trailing')
        end
      end

      context 'with alignBottom' do
        it 'adds spacer before' do
          child = { 'type' => 'View', 'alignBottom' => true }
          renderer.send(:render_child_with_alignment, child, 'vertical')

          expect(renderer.generated_code.first).to eq('Spacer()')
        end
      end

      context 'with alignTop' do
        it 'adds spacer after' do
          child = { 'type' => 'View', 'alignTop' => true }
          renderer.send(:render_child_with_alignment, child, 'vertical')

          expect(renderer.generated_code.last).to eq('Spacer()')
        end
      end
    end

    context 'with ZStack (no orientation)' do
      it 'indents child code' do
        child = { 'type' => 'View' }
        renderer.send(:render_child_with_alignment, child, nil)

        # Should add indented child code
        expect(mock_factory).to have_received(:create_converter)
      end
    end
  end

  describe '#prepare_child_for_rendering' do
    let(:renderer) { renderer_class.new }

    context 'with horizontal orientation and wrapper needed' do
      it 'removes vertical alignment properties' do
        child = {
          'type' => 'View',
          'alignTop' => true,
          'alignBottom' => true,
          'centerVertical' => true,
          'alignLeft' => true
        }

        result = renderer.send(:prepare_child_for_rendering, child, 'horizontal', true)

        expect(result).not_to have_key('alignTop')
        expect(result).not_to have_key('alignBottom')
        expect(result).not_to have_key('centerVertical')
        expect(result).not_to have_key('alignLeft')
      end
    end

    context 'with vertical orientation and wrapper needed' do
      it 'removes horizontal alignment properties' do
        child = {
          'type' => 'View',
          'alignLeft' => true,
          'alignRight' => true,
          'centerHorizontal' => true,
          'alignTop' => true
        }

        result = renderer.send(:prepare_child_for_rendering, child, 'vertical', true)

        expect(result).not_to have_key('alignLeft')
        expect(result).not_to have_key('alignRight')
        expect(result).not_to have_key('centerHorizontal')
        expect(result).not_to have_key('alignTop')
      end
    end
  end

  describe '#wrap_child_for_alignment' do
    let(:renderer) { renderer_class.new }
    let(:child_lines) { ['Text("Hello")'] }

    context 'with horizontal orientation' do
      it 'wraps in VStack' do
        renderer.send(:wrap_child_for_alignment, child_lines, 'horizontal', '.top')

        expect(renderer.generated_code).to include('VStack {')
        expect(renderer.generated_code.last).to include('.frame(maxHeight: .infinity')
      end
    end

    context 'with vertical orientation' do
      it 'wraps in HStack' do
        renderer.send(:wrap_child_for_alignment, child_lines, 'vertical', '.leading')

        expect(renderer.generated_code).to include('HStack {')
        expect(renderer.generated_code.last).to include('.frame(maxWidth: .infinity')
      end
    end
  end
end
