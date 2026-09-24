# frozen_string_literal: true

require 'stringio'
require 'tmpdir'
require 'compose/generators/kotlin_component_generator'
require 'compose/generators/dynamic_component_generator'
require 'compose/generators/view_adapter_generator'
require 'core/config_manager'
require 'core/project_finder'
require 'core/logger'

# Every file a `kjui g converter` run scaffolds follows the same overwrite
# rules as the converter itself: JUI_SKIP_EXISTING / --skip-existing keep it
# without asking, --force replaces it without asking, and otherwise the
# prompt decides — with a closed stdin read as "n".
#
# Until 1.8.112 these sub-generators asked with `gets.chomp` on their own
# (jui-converter-scaffold-subgenerators-block-on-stdin). Same arms as the
# sjui side: the real generators run twice, the first run's files are marked
# as hand-maintained, and the second run must keep or replace them as asked.
# The dynamic component registry is rewritten on purpose, and the
# DynamicComponentInitializer files are created only when missing; neither
# goes through the prompt, so neither is guarded here.
RSpec.describe 'kjui scaffold files honor the overwrite options' do
  let(:dir) { File.realpath(Dir.mktmpdir('kjui_scaffold_overwrite')) }
  let(:untouchable_stdin) do
    Object.new.tap { |o| o.define_singleton_method(:gets) { raise 'stdin was read' } }
  end

  around do |example|
    saved = [Dir.pwd, $stdin, $stdout, ENV.delete('JUI_SKIP_EXISTING')]
    Dir.chdir(dir) { example.run }
  ensure
    $stdin, $stdout = saved[1], saved[2]
    saved[3].nil? ? ENV.delete('JUI_SKIP_EXISTING') : ENV['JUI_SKIP_EXISTING'] = saved[3]
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

  generators = {
    'Kotlin component' => ->(opts) { KjuiTools::Compose::Generators::KotlinComponentGenerator.new('Probe', opts) },
    'dynamic component' => ->(opts) { KjuiTools::Compose::Generators::DynamicComponentGenerator.new('Probe', opts) },
    'view adapter' => ->(opts) { KjuiTools::Compose::Generators::ViewAdapterGenerator.new('Probe', opts) }
  }

  def mark
    "// hand-maintained\n"
  end

  # First run writes; the guarded files are marked; the second run happens
  # under the given options / stdin / env. Returns [guarded files, preserved?].
  def second_run(build, options: {}, stdin: StringIO.new(''), env: nil)
    $stdout = StringIO.new
    build.call({}).generate
    guarded = Dir.glob(File.join(dir, '**', '*'))
                 .select { |f| File.file?(f) && !File.basename(f).match?(/Registr|Initializer|config\.json/) }
    # `all(...)` holds on an empty list, so an empty glob must not pass as kept.
    raise 'the first run wrote no guarded file' if guarded.empty?

    guarded.each { |f| File.write(f, mark) }
    ENV['JUI_SKIP_EXISTING'] = env if env
    $stdin = stdin
    build.call(options).generate
    [guarded, guarded.map { |f| File.read(f) == mark }]
  ensure
    $stdout = STDOUT
  end

  generators.each do |name, build|
    describe name do
      it 'keeps the file on a closed stdin, without raising' do
        guarded, kept = second_run(build, stdin: StringIO.new(''))
        expect(guarded).not_to be_empty
        expect(kept).to all(be true)
      end

      it 'keeps it without asking under JUI_SKIP_EXISTING=1' do
        _, kept = second_run(build, stdin: untouchable_stdin, env: '1')
        expect(kept).to all(be true)
      end

      it 'keeps it without asking under --skip-existing' do
        _, kept = second_run(build, options: { skip_existing: true }, stdin: untouchable_stdin)
        expect(kept).to all(be true)
      end

      it 'replaces it without asking under --force' do
        _, kept = second_run(build, options: { force: true }, stdin: untouchable_stdin)
        expect(kept).to all(be false)
      end

      it 'replaces it on "y" and keeps it on "n"' do
        _, replaced = second_run(build, stdin: StringIO.new("y\n" * 4))
        expect(replaced).to all(be false)
        FileUtils.rm_rf(Dir.glob(File.join(dir, '*')))
        _, kept = second_run(build, stdin: StringIO.new("n\n" * 4))
        expect(kept).to all(be true)
      end
    end
  end
end
