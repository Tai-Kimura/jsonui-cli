# frozen_string_literal: true

require 'fileutils'
require 'tmpdir'
require 'swiftui/app_component_dynamic_check'

# sjui build compares the Dynamic adapters an app registers
# (CustomComponentRegistration.swift) with the converters it draws in release
# (converter_mappings.rb), and names what differs; it rewrites nothing.
RSpec.describe 'sjui build: the app components Debug and release draw differently' do
  around do |example|
    Dir.mktmpdir('sjui_dynamic_check') do |dir|
      @dir = dir
      example.run
    end
  end

  def adapter(name, type, applies: true)
    body = applies ? 'DynamicModifierHelper.applyStandardModifiers(AnyView(EmptyView()), component: component, data: data)' : 'AnyView(EmptyView())'
    File.write(File.join(@dir, "#{name}.swift"),
               "struct #{name}: CustomComponentAdapter {\n    var componentType: String { \"#{type}\" }\n    func buildView() -> AnyView { #{body} }\n}\n")
  end

  def registration(*adapters)
    File.write(File.join(@dir, 'CustomComponentRegistration.swift'),
               "public struct CustomComponentRegistration {\n    public static func registerAll() {\n" \
               "        let adapters: [CustomComponentAdapter] = [\n#{adapters.map { |a| "            #{a}()" }.join(",\n")}\n        ]\n" \
               "        CustomComponentRegistry.shared.registerAll(adapters)\n    }\n}\n")
  end

  def said(mappings)
    SjuiTools::SwiftUI::AppComponentDynamicCheck.warnings(@dir, mappings: mappings)
  end

  it 'names a type release draws with no adapter registered, and an adapter no converter draws' do
    adapter('FadeHeroViewAdapter', 'FadeHeroView')
    adapter('ShimmerTextAdapter', 'ShimmerText')
    registration('FadeHeroViewAdapter', 'ShimmerTextAdapter')
    lines = said(%w[FadeHeroView ProgressBar])
    expect(lines).to include("'ProgressBar' is drawn by the app in release but has no Dynamic adapter registered — Debug draws the built-in 'Progress'")
    expect(lines).to include(a_string_starting_with("'ShimmerText' has a Dynamic adapter registered but no converter draws it"))
    expect(lines.join).not_to include("'FadeHeroView'") # on both sides, applying the modifiers (control)
  end

  # A face registers its screens too (`sjui g adapter Home` → "home", drawn
  # as a TabView tab's view): not a component, so not named.
  it 'leaves out the screens the registration holds, and names a component beside them' do
    adapter('HomeViewAdapter', 'home', applies: false)
    adapter('ItemDetailViewAdapter', 'item_detail', applies: false)
    adapter('ShimmerTextAdapter', 'ShimmerText')
    registration('HomeViewAdapter', 'ItemDetailViewAdapter', 'ShimmerTextAdapter')
    lines = said(%w[])
    expect(lines).to eq(["'ShimmerText' has a Dynamic adapter registered but no converter draws it — release draws " \
                         'no built-in of its own (an undeclared type, unless a built-in has that name)'])
  end

  it 'reads the type from the adapter, not from its struct name' do
    adapter('BarProgressAdapter', 'ProgressBar')
    registration('BarProgressAdapter')
    expect(said(%w[ProgressBar])).to eq([])
  end

  it 'names an adapter that does not apply the standard modifiers, and not one that does' do
    adapter('ProgressBarAdapter', 'ProgressBar', applies: false)
    registration('ProgressBarAdapter')
    expect(said(%w[ProgressBar])).to eq(["'ProgressBar''s adapter does not apply the standard modifiers — Debug draws none of the node's common stages " \
                                         '(its tap, onAppear, frame, background), which release draws. Call DynamicModifierHelper.applyStandardModifiers ' \
                                         'on the view buildView returns, as a generated adapter does.'])
    adapter('ProgressBarAdapter', 'ProgressBar', applies: true)
    expect(said(%w[ProgressBar])).to eq([])
  end

  it 'says nothing with no adapter directory or no registration' do
    expect(SjuiTools::SwiftUI::AppComponentDynamicCheck.warnings(nil, mappings: %w[ProgressBar])).to eq([])
    expect(said(%w[ProgressBar])).to eq([])
  end

  it 'names a file it cannot read instead of skipping it' do
    registration('ProgressBarAdapter')
    File.binwrite(File.join(@dir, 'ProgressBarAdapter.swift'), "\xFF\xFE".b)
    expect(said(%w[ProgressBar])).to include(a_string_starting_with("Could not read #{File.join(@dir, 'ProgressBarAdapter.swift')} (it is not UTF-8)"))
  end
end
