# frozen_string_literal: true

require 'swiftui/view_updater'
require 'json'
require 'fileutils'

RSpec.describe SjuiTools::SwiftUI::ViewUpdater do
  let(:updater) { described_class.new }
  let(:temp_dir) { File.join(Dir.tmpdir, 'view_updater_test') }

  before do
    FileUtils.mkdir_p(temp_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#update_generated_body' do
    let(:swift_file_path) { File.join(temp_dir, 'TestGeneratedView.swift') }

    context 'when file does not exist' do
      it 'returns false' do
        result = updater.update_generated_body('/nonexistent/path.swift', 'code')
        expect(result).to be false
      end
    end

    context 'when file exists' do
      before do
        content = <<~SWIFT
          import SwiftUI

          struct TestGeneratedView: View {
              @Binding var data: TestData

              var body: some View {
                  Text("Old content")
              }
          }
        SWIFT
        File.write(swift_file_path, content)
      end

      it 'updates file content' do
        result = updater.update_generated_body(swift_file_path, 'Text("New content")')
        expect(result).to be true
      end

      it 'writes new body code' do
        updater.update_generated_body(swift_file_path, 'VStack { Text("Updated") }')
        content = File.read(swift_file_path)

        expect(content).to include('VStack { Text("Updated") }')
      end

      it 'includes DynamicView support' do
        updater.update_generated_body(swift_file_path, 'Text("Test")')
        content = File.read(swift_file_path)

        expect(content).to include('ViewSwitcher.isDynamicMode')
        expect(content).to include('DynamicView')
      end

      it 'preserves Data name' do
        updater.update_generated_body(swift_file_path, 'Text("Test")')
        content = File.read(swift_file_path)

        expect(content).to include('TestData')
      end

      # Intended diff (renderer-ssot-15-4): unconditional embed init-params
      # child-side wiring. The type-erased overload lands in SwiftJsonUI
      # 10.6.0; the default `()` keeps VM-less call sites source compatible.
      it 'emits unconditional embed init-params child-side wiring' do
        updater.update_generated_body(swift_file_path, 'Text("Test")')
        content = File.read(swift_file_path)

        expect(content).to include('var viewModel: Any = ()')
        expect(content).to include('// Requires SwiftJsonUI >= 10.6.0')
        expect(content).to include('.receiveEmbedInitParams(to: viewModel)')
      end
    end

    context 'viewModel injection (regression: sjui-embed-event-bridge-references-undeclared-viewmodel)' do
      before do
        content = <<~SWIFT
          import SwiftUI

          struct TabletBarBrowserGeneratedView: View {
              @Binding var data: TabletBarBrowserData

              var body: some View {
                  Text("Old content")
              }
          }
        SWIFT
        File.write(swift_file_path, content)
      end

      let(:swift_file_path) { File.join(temp_dir, 'TabletBarBrowserGeneratedView.swift') }

      it 'declares @ObservedObject viewModel when body references viewModel.' do
        updater.update_generated_body(
          swift_file_path,
          "EmbedContainer(...) { eventBridge: { event in viewModel.onBarSelected(payload) } }"
        )
        content = File.read(swift_file_path)
        expect(content).to include('@ObservedObject var viewModel: TabletBarBrowserViewModel')
      end

      it 'omits viewModel declaration when body does not reference viewModel.' do
        updater.update_generated_body(swift_file_path, 'Text("no embed events")')
        content = File.read(swift_file_path)
        expect(content).not_to include('@ObservedObject var viewModel:')
        # renderer-ssot-15-4: a type-erased slot takes its place for the
        # unconditional init-params wiring
        expect(content).to include('var viewModel: Any = ()')
      end

      it 'keeps the typed viewModel declaration AND wires init params for eventBridge bodies' do
        updater.update_generated_body(
          swift_file_path,
          "EmbedContainer(...) { eventBridge: { event in viewModel.onBarSelected(payload) } }"
        )
        content = File.read(swift_file_path)
        expect(content).to include('@ObservedObject var viewModel: TabletBarBrowserViewModel')
        expect(content).not_to include('var viewModel: Any = ()')
        expect(content).to include('.receiveEmbedInitParams(to: viewModel)')
      end
    end

    context 'when struct not found' do
      let(:invalid_swift_file) { File.join(temp_dir, 'Invalid.swift') }

      before do
        File.write(invalid_swift_file, 'let x = 1')
      end

      it 'returns false' do
        result = updater.update_generated_body(invalid_swift_file, 'code')
        expect(result).to be false
      end
    end
  end

  describe 'private #generate_split_code (WeightedStack root closing-line contract)' do
    # The closing line is part of the rendering contract, not decoration:
    # `], hasMatchParentCrossAxis: true)` toggles the library's inner
    # .fixedSize, and everything after the closing line is the root's
    # modifier chain. Re-emitting a hardcoded "])" dropped the flag, and the
    # old exact-match scan (`== '])'`) then never found the closing line, so
    # every trailing modifier was deleted too — both silently, and both
    # triggered purely by the body crossing LINE_THRESHOLD.
    let(:root_children) do
      [
        { code: "VStack {\n  Text(\"left\")\n}", weight: 1.0, fixed_size: nil },
        { code: "VStack {\n  Text(\"right\")\n}", weight: 2.0,
          fixed_size: '.fixedSize(horizontal: false, vertical: true)' },
      ]
    end

    def weighted_body(closing_line)
      [
        'WeightedHStack(alignment: .top, spacing: 8, children: [',
        '    (',
        '      view: AnyView(',
        '        VStack {',
        '          Text("left")',
        '        }',
        '      ),',
        '      weight: 1.0',
        '    ),',
        '    (',
        '      view: AnyView(',
        '        VStack {',
        '          Text("right")',
        '        }',
        '      ),',
        '      weight: 2.0',
        '    )',
        closing_line,
        '.background(Color.red)',
        '.padding(16)',
      ].join("\n")
    end

    it 'preserves hasMatchParentCrossAxis on the closing line' do
      body, _functions = updater.send(
        :generate_split_code, weighted_body('], hasMatchParentCrossAxis: true)'), root_children
      )
      expect(body).to include('], hasMatchParentCrossAxis: true)')
    end

    it 'keeps the root trailing modifiers when the closing line carries the flag' do
      body, _functions = updater.send(
        :generate_split_code, weighted_body('], hasMatchParentCrossAxis: true)'), root_children
      )
      expect(body).to include('.background(Color.red)')
      expect(body).to include('.padding(16)')
    end

    it 'still handles the bare closing line with trailing modifiers' do
      body, _functions = updater.send(:generate_split_code, weighted_body('])'), root_children)
      expect(body).to include('])')
      expect(body).not_to include('hasMatchParentCrossAxis')
      expect(body).to include('.background(Color.red)')
      expect(body).to include('.padding(16)')
    end

    it 'preserves the call-site fixedSize contract alongside the flag' do
      body, _functions = updater.send(
        :generate_split_code, weighted_body('], hasMatchParentCrossAxis: true)'), root_children
      )
      expect(body).to include('AnyView(section1().fixedSize(horizontal: false, vertical: true))')
    end

    it 'is not fooled by an inner line that starts with "])" while the children array is open' do
      # A nested config array (e.g. constraints: [ ... ]) can legitimately
      # close as "])" inside a child; the bracket-depth guard must keep
      # scanning until the ROOT array closes.
      inner = [
        'WeightedHStack(alignment: .top, spacing: 8, children: [',
        '    (',
        '      view: AnyView(',
        '        RelativePositionContainer(children: [',
        '          RelativeChildConfig(view: AnyView(Text("x")), constraints: [',
        '            RelativePositionConstraint(type: .top)',
        '          ])',
        '        ])',
        '      ),',
        '      weight: 1.0',
        '    ),',
        '    (',
        '      view: AnyView(Text("y")),',
        '      weight: 2.0',
        '    )',
        '], hasMatchParentCrossAxis: true)',
        '.padding(4)',
      ].join("\n")
      body, _functions = updater.send(:generate_split_code, inner, root_children)
      expect(body).to include('], hasMatchParentCrossAxis: true)')
      expect(body).to include('.padding(4)')
    end
  end

  describe 'private #generate_swiftui_code' do
    context 'with View type' do
      it 'generates VStack for vertical orientation' do
        json = { 'type' => 'View', 'orientation' => 'vertical' }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('VStack')
      end

      it 'generates HStack for horizontal orientation' do
        json = { 'type' => 'View', 'orientation' => 'horizontal' }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('HStack')
      end

      it 'defaults to VStack' do
        json = { 'type' => 'View' }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('VStack')
      end
    end

    context 'with Label type' do
      it 'generates Text with static text' do
        json = { 'type' => 'Label', 'text' => 'Hello World' }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('Text("Hello World")')
      end

      it 'generates Text with binding' do
        json = { 'type' => 'Label', 'text' => '@{userName}' }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('Text(data.userName)')
      end

      it 'applies fontSize modifier' do
        json = { 'type' => 'Label', 'text' => 'Hi', 'fontSize' => 18 }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('.font(.system(size: 18))')
      end

      it 'applies fontColor modifier' do
        json = { 'type' => 'Label', 'text' => 'Hi', 'fontColor' => '#FF0000' }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('.foregroundColor(Color(hex: "#FF0000"))')
      end

      it 'applies topMargin modifier' do
        json = { 'type' => 'Label', 'text' => 'Hi', 'topMargin' => 10 }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('.padding(.top, 10)')
      end
    end

    context 'with Button type' do
      it 'generates Button with text' do
        json = { 'type' => 'Button', 'text' => 'Submit' }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('Button(action:')
        expect(result).to include('Text("Submit")')
      end

      it 'uses onClick action' do
        json = { 'type' => 'Button', 'text' => 'Go', 'onClick' => 'handleTap' }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('data.handleTap')
      end

      it 'applies topMargin modifier' do
        json = { 'type' => 'Button', 'text' => 'Btn', 'topMargin' => 20 }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('.padding(.top, 20)')
      end
    end

    context 'with nested children' do
      it 'processes child array' do
        json = {
          'type' => 'View',
          'child' => [
            { 'type' => 'Label', 'text' => 'Child 1' },
            { 'type' => 'Label', 'text' => 'Child 2' }
          ]
        }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('Text("Child 1")')
        expect(result).to include('Text("Child 2")')
      end

      it 'skips data declarations' do
        json = {
          'type' => 'View',
          'child' => [
            { 'data' => { 'name' => 'test' } },
            { 'type' => 'Label', 'text' => 'Visible' }
          ]
        }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('Text("Visible")')
        expect(result).not_to include('test')
      end
    end

    context 'with modifiers' do
      it 'applies paddings' do
        json = { 'type' => 'View', 'paddings' => true }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('.padding()')
      end

      it 'applies background' do
        json = { 'type' => 'View', 'background' => '#FFFFFF' }
        result = updater.send(:generate_swiftui_code, json)

        expect(result).to include('.background(Color(hex: "#FFFFFF"))')
      end
    end
  end

  describe 'private #indent_body_code' do
    it 'indents all lines' do
      code = "Line1\nLine2\nLine3"
      result = updater.send(:indent_body_code, code, "    ")

      expect(result).to eq("    Line1\n    Line2\n    Line3")
    end

    it 'preserves empty lines' do
      code = "Line1\n\nLine2"
      result = updater.send(:indent_body_code, code, "  ")

      expect(result).to eq("  Line1\n\n  Line2")
    end
  end

  describe 'private #generate_split_code (weighted section extraction)' do
    # Regression: a section-extracted weight:0 wrapContent child must keep the
    # call-site .fixedSize(...) contract that the inline path emits inside
    # AnyView(...). Section extraction must be an emit-equivalent transform
    # (drops-weighted-child-call-site-fixed-size).
    let(:full_body_code) do
      <<~SWIFT.chomp
        WeightedVStack(alignment: .leading, children: [
          (
            view: AnyView(
              Text("a")
            ),
            weight: 0
          ),
          (
            view: AnyView(
              Text("b")
            ),
            weight: 1
          )
        ])
      SWIFT
    end

    let(:root_children) do
      [
        { code: 'Text("a")', weight: 0, fixed_size: '.fixedSize(horizontal: false, vertical: true)' },
        { code: 'Text("b")', weight: 1, fixed_size: nil }
      ]
    end

    it 'appends the captured fixedSize to the extracted weight:0 child call site' do
      body_code, _section_functions = updater.send(:generate_split_code, full_body_code, root_children)

      expect(body_code).to include('view: AnyView(section0().fixedSize(horizontal: false, vertical: true))')
    end

    it 'leaves a child without a fixedSize contract as a plain section call' do
      body_code, _section_functions = updater.send(:generate_split_code, full_body_code, root_children)

      expect(body_code).to include('view: AnyView(section1())')
      expect(body_code).not_to include('section1().fixedSize')
    end

    it 'still emits a section function body for the extracted child' do
      _body_code, section_functions = updater.send(:generate_split_code, full_body_code, root_children)

      expect(section_functions).to include('func section0()')
      expect(section_functions).to include('Text("a")')
    end
  end
end
