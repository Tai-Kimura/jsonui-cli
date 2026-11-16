# frozen_string_literal: true

require 'spec_helper'
require 'stringio'
require 'tmpdir'
require 'core/generated_marker'
require 'swiftui/generators/converter_generator'
require 'swiftui/generators/swift_component_generator'
require 'swiftui/generators/adapter_generator'
require 'swiftui/generators/view_adapter_generator'

# A scaffold says it is the user's; a registry the generator appends to says
# it is the tool's.
#
# Until 1.8.112 every scaffold (the converter, the Swift component, the
# adapters) opened with "@generated AUTO-GENERATED FILE — DO NOT EDIT … LLM/
# Agent: you MUST NOT modify this file", while the converter core called the
# scaffold user-owned and the generator never replaced one unasked. An agent
# obeying the banner refused a two-line fix the file needed. Ruled 2026-09-24
# (sjui-converter-scaffold-banner-contradicts-user-owned): every scaffold is
# the user's. The registration file stays the tool's — the control that the
# arm can tell the two headers apart.
RSpec.describe 'sjui scaffold headers' do
  marker = SjuiTools::Core::GeneratedMarker
  forbidden = [marker::SENTINEL, 'DO NOT EDIT', marker::AGENT_WARNING, marker::END_LINE]

  let(:dir) { File.realpath(Dir.mktmpdir('sjui_scaffold_header')) }

  around do |example|
    saved = [Dir.pwd, $stdout]
    Dir.chdir(dir) { example.run }
  ensure
    $stdout = saved[1]
    FileUtils.rm_rf(dir)
  end

  before do
    %i[info warn success debug].each { |m| allow(SjuiTools::Core::Logger).to receive(m) }
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return(
      'extension_directory' => 'Extensions', 'adapter_directory' => 'Extensions/Adapters'
    )
    allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths)
    allow(SjuiTools::Core::ProjectFinder).to receive(:project_dir).and_return(dir)
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
    $stdout = StringIO.new
  end

  def expect_user_owned(text, what)
    expect(text).to include(SjuiTools::Core::GeneratedMarker::SCAFFOLD_NOTE), what
  end

  it 'the converter scaffold' do
    %w[true false].each do |container|
      text = SjuiTools::SwiftUI::Generators::ConverterGenerator
             .new('Probe', is_container: container == 'true').send(:converter_template)
      expect_user_owned(text, "converter container=#{container}")
      forbidden.each { |word| expect(text).not_to include(word) }
    end
  end

  {
    'the Swift component (container)' => [->(o) { SjuiTools::SwiftUI::Generators::SwiftComponentGenerator.new('Probe', o) }, { is_container: true }],
    'the Swift component (leaf)' => [->(o) { SjuiTools::SwiftUI::Generators::SwiftComponentGenerator.new('Probe', o) }, { is_container: false }],
    'the adapter' => [->(o) { SjuiTools::SwiftUI::Generators::AdapterGenerator.new('Probe', o) }, {}],
    'the view adapter' => [->(o) { SjuiTools::SwiftUI::Generators::ViewAdapterGenerator.new('Probe', o) }, {}]
  }.each do |what, (build, opts)|
    it what do
      build.call(opts).generate
      files = Dir.glob(File.join(dir, '**', '*.swift'))
      scaffolds = files.reject { |f| File.basename(f).include?('Registration') }
      registries = files - scaffolds
      expect(scaffolds).not_to be_empty
      scaffolds.each do |f|
        text = File.read(f)
        expect_user_owned(text, f)
        forbidden.each { |word| expect(text).not_to include(word), "#{File.basename(f)}: #{word}" }
      end
      # The tool's own file keeps the banner (the control).
      registries.each { |f| expect(File.read(f)).to include(SjuiTools::Core::GeneratedMarker::SENTINEL) }
    end
  end

  it 'a registry is written at all, so the control above is exercised' do
    SjuiTools::SwiftUI::Generators::AdapterGenerator.new('Probe', {}).generate
    registries = Dir.glob(File.join(dir, '**', '*Registration*.swift'))
    expect(registries).not_to be_empty
    expect(File.read(registries.first)).to include(SjuiTools::Core::GeneratedMarker::SENTINEL)
  end
end
