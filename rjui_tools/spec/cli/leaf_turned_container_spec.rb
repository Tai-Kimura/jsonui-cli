# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# A leaf (`rjui g converter <Name> --no-container`) turned back into a
# container — `--container`, which `jui g converter --from` passes for a
# component spec that gained slots — by a run that KEEPS existing files:
# --skip-existing, a closed stdin (read as "n"), or an "n" to one prompt.
#
# Until 1.8.121 (measured on f16f3a11, 2026-09-26) the definition went back to
# `child` / `children` while the kept converter still said
# `is_container = false`: the build accepted the children and the converter
# drew the component without them — rc 0, not a word. A kept component .tsx
# made for a leaf does not mention `children`, so it drops them too. Ticket
# leaf-turned-container-keeps-its-leaf-scaffold-silently. Now the run names
# every kept file in the leaf form and the definition stays a leaf, so the
# build refuses the children instead of dropping them; `--force` makes it a
# container, and a leaf kept a leaf says nothing new.
#
# End to end, as leaf_children_build_spec.rb: the overwrite decision, the
# definition and the build that reads it are three steps. The tool is COPIED
# (links dereferenced): `g converter` writes into the tool's own
# converters/extensions.
RSpec.describe 'a leaf turned back into a container, through rjui g converter and rjui build' do
  def tool_root
    File.expand_path('../..', __dir__)
  end

  # component => [the re-run's flags, its stdin, the kept files the warning names].
  # A method, not a constant: a constant in a describe block is top-level.
  def self.reruns
    {
      'Kept' => [['--container', '--skip-existing'], '', %w[kept_converter.rb Kept.tsx]],
      'Closed' => [['--container'], '', %w[closed_converter.rb Closed.tsx]],
      # "n" to the converter, "y" to the component
      'Half' => [['--container'], "n\ny\n", %w[half_converter.rb]],
      # "y" to the converter; the component reads EOF, "n"
      'Viewed' => [['--container'], "y\n", %w[Viewed.tsx]],
      'Forced' => [['--container', '--force'], '', []],
      'Still' => [['--no-container', '--skip-existing'], '', []]
    }
  end

  before(:all) do
    @dir = Dir.mktmpdir('rjui_leaf_turned')
    tool = File.join(@dir, 'rjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    # No rjui.config.json: rjui writes its defaults (layouts in src/Layouts,
    # output under src/generated), as leaf_children_build_spec.rb.
    layouts = File.join(@dir, 'src', 'Layouts')
    FileUtils.mkdir_p(layouts)

    rjui = lambda do |component, args, stdin|
      said, status = Open3.capture2e('ruby', File.join(tool, 'bin', 'rjui'), 'g', 'converter', component,
                                     '--attributes', 'title:String', *args, chdir: @dir, stdin_data: stdin)
      [said.gsub(/\e\[[0-9;]*m/, ''), status]
    end
    @first = {}
    @rerun = {}
    self.class.reruns.each do |component, (args, stdin, _)|
      @first[component] = rjui.call(component, ['--no-container', '--force'], '')
      @rerun[component] = rjui.call(component, args, stdin)
      File.write(File.join(layouts, "#{component.downcase}_screen.json"), JSON.generate(
        'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
        'orientation' => 'vertical',
        'child' => [{ 'type' => component, 'id' => component.downcase, 'title' => component,
                      'width' => 'matchParent', 'height' => 'wrapContent',
                      'child' => [{ 'type' => 'Label', 'id' => "#{component.downcase}_kid", 'text' => 'kid',
                                    'width' => 'wrapContent', 'height' => 'wrapContent' }] }]
      ))
    end

    @ledger = File.join(@dir, 'stage-failures.json')
    @log, @status = Open3.capture2e({ 'JUI_STAGE_FAILURES' => @ledger },
                                    'ruby', File.join(tool, 'bin', 'rjui'), 'build', chdir: @dir)
    @log = @log.gsub(/\e\[[0-9;]*m/, '')
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  def definition(component)
    path = File.join(@dir, 'rjui_tools', 'lib', 'react', 'converters', 'extensions', 'attribute_definitions',
                     "#{component}.json")
    JSON.parse(File.read(path))[component]
  end

  def leaf_form_warnings(component)
    @rerun[component].first.lines.select { |l| l.include?('in the leaf form') }
  end

  def refused?(component)
    ledger = File.exist?(@ledger) ? JSON.parse(File.read(@ledger)) : []
    ledger.any? do |e|
      e['stage'] == 'layout' && e['message'].include?("#{component.downcase}_screen.json") &&
        e['message'].include?("'#{component}' (id=#{component.downcase}) takes no children")
    end
  end

  def drawn?(component)
    Dir.glob(File.join(@dir, 'src', 'generated', '**', '*.{tsx,jsx}'))
       .any? { |f| File.read(f).include?("\"#{component.downcase}_kid\"") }
  end

  it 'runs every scaffold to rc 0' do
    runs = @first.values + @rerun.values
    expect(runs.map { |_, s| s.success? }).to all(be(true)), runs.map(&:first).join("\n")
  end

  %w[Kept Closed Half Viewed].each do |component|
    args, stdin, names = reruns[component]
    context "#{component}: #{args.join(' ')}#{stdin.empty? ? '' : " answering #{stdin.inspect}"}" do
      it 'names each kept file in the leaf form, and only those' do
        said = leaf_form_warnings(component)
        expect(said.size).to eq(1), @rerun[component].first
        named = said.first.scan(/([\w.]+) \((?:draws|refuses|does not)/).flatten
        expect(named).to match_array(names)
        expect(said.first).to include("#{component} would take children (--container)")
          .and include('--force').and include('--no-container')
      end

      it 'keeps the definition a leaf, so the build refuses the children instead of dropping them' do
        expect(definition(component)).to include('_children' => 'none')
        expect(definition(component)).not_to include('child', 'children')
        expect(refused?(component)).to be(true), @log
        expect(drawn?(component)).to be(false)
      end
    end
  end

  it '--force: a container, the children drawn, no leaf-form warning' do
    expect(leaf_form_warnings('Forced')).to be_empty
    expect(definition('Forced').keys).to include('child', 'children')
    expect(definition('Forced')).not_to include('_children')
    expect(refused?('Forced')).to be(false)
    expect(drawn?('Forced')).to be(true), @log
  end

  it 'a leaf kept a leaf: still refused, and nothing new said' do
    expect(leaf_form_warnings('Still')).to be_empty
    expect(definition('Still')).to include('_children' => 'none')
    expect(refused?('Still')).to be(true), @log
    expect(drawn?('Still')).to be(false)
  end
end
