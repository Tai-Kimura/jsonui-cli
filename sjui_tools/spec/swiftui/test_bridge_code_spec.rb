# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'fileutils'
require 'stringio'
require 'swiftui/data_model_updater'
require 'swiftui/view_updater'
require 'swiftui/test_bridge_code'

# The test bridge sjui emits (jsonui-test-runner spec section 10.3-10.4):
# applyTestInitialState / testSnapshot on every Data type, .jsonUITestBridge
# on every screen view. Whether a value fits is SwiftJsonUI's
# JsonUITestValue.check (unit-tested there against the shared coercion
# vector); these arms hold the code around it.
RSpec.describe 'test bridge (sjui)' do
  let(:vector) { File.expand_path('../../../shared/core/initial_state_coercion_vectors.json', __dir__) }

  describe SjuiTools::SwiftUI::TestBridgeCode do
    # The generator decides only what Swift to write for an accepted value.
    # It must agree with the judge about which classes can be set at all: a
    # class the judge accepts but the generator calls unsupported would be
    # applied in the receipt and never assigned; the reverse would assign a
    # value the judge never hands over.
    it 'calls unsupported exactly the classes the shared vector rejects as unsupported' do
      cases = JSON.parse(File.read(vector))['cases']
      expect(cases.size).to be > 50
      unsupported = cases.flat_map { |c| c['expect']['rejected'] }.map { |r| r['reason'] }
                         .grep(/\Aunsupported type /).map { |r| r.delete_prefix('unsupported type ') }.uniq
      applied = cases.flat_map { |c| c['expect']['applied'].map { |k| c['data'].find { |d| d['name'] == k }['class'] } }.uniq

      expect(unsupported).not_to be_empty
      expect(applied.size).to be > 20
      unsupported.each { |klass| expect(described_class.kind(klass)).to eq(:unsupported), klass }
      applied.each { |klass| expect(described_class.kind(klass)).not_to eq(:unsupported), klass }
    end

    it 'names the class as declared in the check call and the Swift type in the cast' do
      code = described_class.apply_function([
        { name: 'agreed', declared: 'Boolean', swift_type: 'Bool', swift_optional: false },
        { name: 'nickname', declared: 'String?', swift_type: 'String?', swift_optional: true }
      ])
      expect(code).to include('JsonUITestValue.check(value, declaredClass: "Boolean")')
      expect(code).to include('if let typed = accepted as? Bool { self.agreed = typed }')
      expect(code).to include('self.nickname = accepted as? String')
      expect(code).to include('rejected.append(.notADataField(key))')
    end

    it 'leaves closures and colours out of the snapshot, and writes null for a nil optional' do
      code = described_class.snapshot_function([
        { name: 'email', declared: 'String', swift_type: 'String', swift_optional: false },
        { name: 'age', declared: 'Int?', swift_type: 'Int?', swift_optional: true },
        { name: 'tint', declared: 'Color', swift_type: 'Color', swift_optional: false },
        { name: 'onTap', declared: '(() -> Void)?', swift_type: '(() -> Void)?', swift_optional: true }
      ])
      expect(code).to include('snapshot["email"] = email')
      expect(code).to include('snapshot["age"] = age.map { $0 as Any } ?? NSNull()')
      expect(code).not_to include('"tint"')
      expect(code).not_to include('"onTap"')
    end
  end

  describe 'the Data type' do
    let(:dir) { Dir.mktmpdir('test_bridge') }

    before do
      %w[Layouts Data Styles].each { |d| FileUtils.mkdir_p(File.join(dir, d)) }
      allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return(
        'layouts_directory' => 'Layouts', 'data_directory' => 'Data', 'styles_directory' => 'Styles'
      )
      allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
    end

    after { FileUtils.rm_rf(dir) }

    let(:declared) do
      [
      { 'name' => 'email', 'class' => 'String', 'defaultValue' => '' },
      { 'name' => 'nickname', 'class' => 'String?' },
      { 'name' => 'count', 'class' => 'Integer', 'defaultValue' => 0 },
      { 'name' => 'ratio', 'class' => 'Double', 'defaultValue' => 0 },
      { 'name' => 'weight', 'class' => 'Float', 'defaultValue' => 0 },
      { 'name' => 'inset', 'class' => 'CGFloat', 'defaultValue' => 0 },
      { 'name' => 'agreed', 'class' => 'Boolean', 'defaultValue' => false },
      { 'name' => 'tint', 'class' => 'Color' },
      { 'name' => 'tags', 'class' => 'Array(String)', 'defaultValue' => [] },
      { 'name' => 'scores', 'class' => '[Int]', 'defaultValue' => [] },
      { 'name' => 'palette', 'class' => 'Array(Color)', 'defaultValue' => [] },
      { 'name' => 'extra', 'class' => 'Object', 'defaultValue' => {} },
      { 'name' => 'items', 'class' => 'Array', 'defaultValue' => [] },
      { 'name' => 'onTap', 'class' => '(() -> Void)?' }
      ]
    end

    def build
      File.write(File.join(dir, 'Layouts', 'screen.json'),
                 JSON.generate('type' => 'View', 'id' => 'root', 'child' => [{ 'data' => declared }]))
      $stdout = StringIO.new
      SjuiTools::SwiftUI::DataModelUpdater.new.send(:process_json_file, File.join(dir, 'Layouts', 'screen.json'))
      File.read(File.join(dir, 'Data', 'ScreenData.swift'))
    ensure
      $stdout = STDOUT
    end

    it 'checks every declared field by the class as the layout spells it' do
      data = build
      declared.each do |d|
        expect(data).to include("case \"#{d['name']}\":")
        expect(data).to include("JsonUITestValue.check(value, declaredClass: #{d['class'].to_json})")
      end
    end

    # The bridge's library signatures are in the compiler's own stubs
    # (spec/support/swift_compiler.rb); ColorManager is the one this file adds,
    # as Color fields resolve through it.
    let(:color_manager_stub) do
      <<~SWIFT
        enum ColorManager {
            struct SwiftUIColors { func color(for name: String) -> Color? { nil } }
            static let swiftui = SwiftUIColors()
        }
      SWIFT
    end

    # Not 'Number' nor a Color default here: sjui's Data emission writes
    # `var x: Number` (it does not map that synonym for Data properties) and a
    # Color default as UIColor, which this macOS compile check lacks. Both are
    # outside the bridge; the Number spelling is held by the vector arm above.
    it 'compiles, every class kind included' do
      data = build.lines.reject { |l| l.start_with?('import ') }.join
      expect("#{EmittedSwift::LIBRARY_STUBS}\n#{color_manager_stub}\n#{data}").to compile_as_swift.with_imports('SwiftUI')
    end
  end

  describe 'the screen view' do
    def generated(screen_id)
      Dir.mktmpdir do |dir|
        path = File.join(dir, 'HomeGeneratedView.swift')
        File.write(path, <<~SWIFT)
          import SwiftUI

          struct HomeGeneratedView: View {
              @SwiftUI.Binding var data: HomeData

              var body: some View {
                  // >>> GENERATED_CODE_START
                  Text("Placeholder")
                  // >>> GENERATED_CODE_END
              }
          }
        SWIFT
        SjuiTools::SwiftUI::ViewUpdater.new.update_generated_body(path, 'Text("base")', screen_id: screen_id)
        File.read(path)
      end
    end

    it 'carries the bridge on the outer Group, beside the marker, with the bare screen id' do
      content = generated('home')
      bridge = '.jsonUITestBridge("home", snapshot: { data.testSnapshot() }, apply: { data.applyTestInitialState($0) })'
      expect(content.scan(bridge).size).to eq(1)
      expect(content.index(bridge)).to be < content.index('private var generatedBody')
      expect(content.index(bridge)).to be > content.index('.jsonUIScreenMarker("home")')
      expect(content).to include("// Requires SwiftJsonUI >= #{SjuiTools::SwiftUI::TestBridgeCode::MIN_LIBRARY_VERSION} (test bridge")
    end

    it 'emits no bridge for a layout that is not a screen' do
      expect(generated(nil)).not_to include('jsonUITestBridge')
    end
  end
end
