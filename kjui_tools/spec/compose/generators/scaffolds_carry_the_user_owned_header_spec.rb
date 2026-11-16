# frozen_string_literal: true

require 'stringio'
require 'tmpdir'
require 'core/generated_marker'
require 'core/config_manager'
require 'core/project_finder'
require 'core/logger'
require 'compose/generators/kotlin_component_generator'
require 'compose/generators/view_adapter_generator'

# A kjui scaffold says it is the user's (ruled 2026-09-24,
# sjui-converter-scaffold-banner-contradicts-user-owned): the Kotlin component
# and the view adapter open with the scaffold header, not the "@generated …
# DO NOT EDIT … MUST NOT modify" banner they carried through 1.8.111.
RSpec.describe 'kjui scaffold headers' do
  marker = KjuiTools::Core::GeneratedMarker
  forbidden = [marker::SENTINEL, 'DO NOT EDIT', marker::AGENT_WARNING, marker::END_LINE]

  let(:dir) { File.realpath(Dir.mktmpdir('kjui_scaffold_header')) }

  around do |example|
    Dir.chdir(dir) { example.run }
  ensure
    FileUtils.rm_rf(dir)
  end

  before do
    %i[info warn success debug].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(
      '_config_dir' => dir, 'source_directory' => 'src/main', 'package_name' => 'com.example.app'
    )
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
    allow(KjuiTools::Core::ProjectFinder).to receive(:setup_paths).and_return(true)
  end

  {
    'the Kotlin component (container)' => [->(o) { KjuiTools::Compose::Generators::KotlinComponentGenerator.new('Probe', o) }, { is_container: true }, 'Probe.kt'],
    'the Kotlin component (leaf)' => [->(o) { KjuiTools::Compose::Generators::KotlinComponentGenerator.new('Probe', o) }, { is_container: false }, 'Probe.kt'],
    'the view adapter' => [->(o) { KjuiTools::Compose::Generators::ViewAdapterGenerator.new('Probe', o) }, {}, 'ProbeViewAdapter.kt']
  }.each do |what, (build, opts, name)|
    it what do
      $stdout = StringIO.new
      build.call(opts).generate
      $stdout = STDOUT
      files = Dir.glob(File.join(dir, '**', name))
      expect(files.size).to eq(1), Dir.glob(File.join(dir, '**', '*')).inspect
      text = File.read(files.first)
      expect(text).to include(marker::SCAFFOLD_NOTE)
      forbidden.each { |word| expect(text).not_to include(word), word }
    end
  end
end
