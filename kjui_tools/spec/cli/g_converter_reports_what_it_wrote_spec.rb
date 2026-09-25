# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# What `kjui g converter` prints about each file, held to what happened on
# disk — a snapshot before and after each run, not the record the generator
# keeps — on every path a scaffold file can take: new, --skip-existing, a
# closed stdin, --force, "y", and the converter deleted with the rest kept.
# The composable, the Dynamic wrapper, the mappings and the definition.
#
# Until 1.8.121 (measured on 1b80b5ba, 2026-09-26) every run ended
# "Successfully generated converter", "Converter file created at: …" and
# "Mappings file updated with …" — after --skip-existing and a closed stdin
# too, when it had written neither; a replaced file was "Created"; the
# definition "Created" when it was rewritten. Ticket
# g-converter-reports-files-it-did-not-write.
RSpec.describe 'what kjui g converter says it wrote, against the disk' do
  def tool_root
    File.expand_path('../..', __dir__)
  end

  # [label, set-up before the run, flags, stdin]
  def self.paths
    [
      ['new', nil, [], ''],
      ['--skip-existing', :scaffolded, ['--skip-existing'], ''],
      ['a closed stdin', :scaffolded, [], ''],
      ['--force', :scaffolded, ['--force'], ''],
      ['"y" to every prompt', :scaffolded, [], "y\ny\ny\ny\n"],
      ['the converter deleted, a closed stdin', :converter_deleted, [], '']
    ]
  end

  def copy_tool(dir)
    tool = File.join(dir, 'kjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    tool
  end

  def write_config(dir)
    File.write(File.join(dir, 'kjui.config.json'), JSON.pretty_generate(
      'mode' => 'compose', 'project_name' => 'P', 'source_directory' => 'app/src/main',
      'layouts_directory' => 'assets/Layouts', 'styles_directory' => 'assets/Styles',
      'data_directory' => 'kotlin/com/example/app/data', 'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
      'view_directory' => 'kotlin/com/example/app/views', 'extension_directory' => 'kotlin/com/example/app/extensions',
      'adapter_directory' => 'kotlin/com/example/app/adapters',
      'resource_manager_directory' => 'app/src/main/kotlin/com/kotlinjsonui/generated',
      'package_name' => 'com.example.app', 'string_files' => ['res/values/strings.xml'], 'use_network' => true
    ))
  end

  def run_tool(dir, tool, flags, stdin)
    said, status = Open3.capture2e('ruby', File.join(tool, 'bin', 'kjui'), 'g', 'converter', 'Probe',
                                   '--attr', 'title:String', *flags, chdir: dir, stdin_data: stdin)
    raise "kjui g converter failed:\n#{said}" unless status.success?

    said.gsub(/\e\[[0-9;]*m/, '')
  end

  def snapshot(dir)
    Dir.glob(File.join(dir, '**', '*')).select { |f| File.file?(f) }
       .reject { |f| f.include?('/kjui_tools/') && !f.include?('/extensions/') }
       .to_h { |f| [File.realpath(f), [File.binread(f), File.mtime(f)]] }
  end

  # file => :created / :rewritten / :untouched
  def disk(before, after)
    after.keys.to_h do |f|
      state = if !before.key?(f) then :created
              elsif before[f][1] != after[f][1] then :rewritten
              else :untouched
              end
      [f, state]
    end
  end

  # The path a line names for `basename`, resolved in the project, with its
  # case (the file system here ignores case; the name printed must not).
  def printed_path(line, dir)
    token = line[%r{(\S*/)?[\w.-]+\.(?:rb|swift|kt|tsx|json)\b}]
    return nil unless token

    full = File.expand_path(token, dir)
    return nil unless File.exist?(full) && Dir.children(File.dirname(full)).include?(File.basename(full))

    File.realpath(full)
  end

  # Runs every path; returns [[label, output, disk, dir], ...].
  def runs(scaffold_files)
    self.class.paths.map do |label, setup, flags, stdin|
      dir = Dir.mktmpdir('kjui_report')
      tool = copy_tool(dir)
      write_config(dir)
      run_tool(dir, tool, ['--force'], '') if setup
      if setup == :converter_deleted
        converter = Dir.glob(File.join(tool, 'lib', '**', 'extensions', scaffold_files.first.first))
        raise "#{label}: no #{scaffold_files.first.first} to delete" unless converter.size == 1

        FileUtils.rm(converter)
      end
      before = snapshot(dir)
      sleep 0.01
      said = run_tool(dir, tool, flags, stdin)
      [label, said, disk(before, snapshot(dir)), dir]
    end
  end

  # Holds each scaffold file's line to the disk: Created / Overwrote /
  # Skipped / Kept, naming the file it is about.
  def check_scaffold_lines(label, said, states, scaffold_files, dir)
    scaffold_files.each do |basename, verb_label, noun|
      file, state = states.find { |f, _| File.basename(f) == basename }
      expect(file).not_to be_nil, "#{label}: no #{basename} on disk"
      lines = said.lines.select { |l| printed_path(l, dir) == file }
      verbs = case state
              when :created then ["Created #{verb_label}:"]
              when :rewritten then ["Overwrote #{verb_label}:"]
              else ["Skipped existing #{noun}:", "Kept existing #{noun}:"]
              end
      expect(lines.any? { |l| verbs.any? { |v| l.include?(v) } }).to be(true),
                                                                     "#{label}: #{basename} #{state}, said:\n#{said}"
      next unless state == :untouched

      expect(said.lines.select { |l| l =~ /creat|overwr|updat|generated/i && l.include?(basename) }).to be_empty,
                                                                                                        "#{label}: #{said}"
    end
  end

  # The precondition: each path did to the scaffold files what it is for —
  # a path that silently became another would leave the checks below
  # green and saying nothing (the first cut of this spec deleted no
  # converter on its last path).
  def check_paths_did_what_they_are_for(runs, scaffold_files)
    want = {
      'new' => [:created] * scaffold_files.size,
      '--skip-existing' => [:untouched] * scaffold_files.size,
      'a closed stdin' => [:untouched] * scaffold_files.size,
      '--force' => [:rewritten] * scaffold_files.size,
      '"y" to every prompt' => [:rewritten] * scaffold_files.size,
      'the converter deleted, a closed stdin' => [:created] + [:untouched] * (scaffold_files.size - 1)
    }
    runs.each do |label, _, states, _|
      got = scaffold_files.map { |basename, *| states.find { |f, _| File.basename(f) == basename }&.last }
      expect(got).to eq(want.fetch(label)), label
    end
  end

  # Every file a line names exists, spelled as it is.
  def check_paths_exist(label, said, dir)
    said.lines.each do |line|
      next unless line =~ %r{[\w.-]+\.(?:rb|swift|kt|tsx|json)\b}

      expect(printed_path(line, dir)).not_to be_nil, "#{label}: names a file that is not there: #{line}"
    end
  end

  describe 'the scaffold' do
    # [basename, what a write calls it, what a keep calls it]
    def scaffold_files
      [['probe_component.rb', 'converter file', 'converter'], ['Probe.kt', 'Kotlin file', 'kotlin file'],
       ['DynamicProbeComponent.kt', 'dynamic component file', 'dynamic component file']]
    end

    before(:all) { @runs = runs(scaffold_files) }
    after(:all) { @runs.each { |*, dir| FileUtils.rm_rf(dir) } }

    it 'runs each path as it is meant to (the precondition)' do
      check_paths_did_what_they_are_for(@runs, scaffold_files)
    end

    it 'says Created, Overwrote, Skipped or Kept for each scaffold file, as the disk shows' do
      aggregate_failures do
        @runs.each { |label, said, states, dir| check_scaffold_lines(label, said, states, scaffold_files, dir) }
      end
    end

    it 'names no file that is not there' do
      aggregate_failures { @runs.each { |label, said, _, dir| check_paths_exist(label, said, dir) } }
    end

    def mapping_line
      {
      created: /Created \S+component_mappings\.rb with the mapping 'Probe'/,
      rewritten: /Updated \S+component_mappings\.rb: added the mapping 'Probe'/,
      untouched: /Unchanged \S+component_mappings\.rb: it already maps 'Probe'/
      }
    end

    it 'says the mapping was created, updated or unchanged, as the disk shows' do
      aggregate_failures do
        @runs.each do |label, said, states, _|
          mapping = states.find { |f, _| f.end_with?('/component_mappings.rb') }&.last
          expect(said).not_to include('Mappings file updated with'), label
          expect(said).to match(mapping_line.fetch(mapping)), "#{label} (#{mapping}): #{said}"
        end
      end
    end

    it 'says Created or Rewrote for the definition, with its path' do
      aggregate_failures do
        @runs.each do |label, said, states, dir|
          file, state = states.find { |f, _| f.end_with?('/attribute_definitions/Probe.json') }
          line = said.lines.find { |l| printed_path(l, dir) == file }
          expect(line).to include(state == :created ? 'Created attribute definition file:' : 'Rewrote attribute definition file:'),
                          "#{label}: #{said}"
        end
      end
    end

    it 'counts what the disk shows, and says "generated" only for what it wrote' do
      aggregate_failures do
        @runs.each do |label, said, states, _|
          scaffold = scaffold_files.map { |basename, *| states.find { |f, _| File.basename(f) == basename }.last }
          counts = "#{scaffold.count(:created)} created, #{scaffold.count(:rewritten)} overwritten, " \
                   "#{scaffold.count(:untouched)} kept"
          expect(said).to include(counts), "#{label}: #{said}"
          expect(said).not_to include('Successfully generated converter'), label
          expect(said).not_to include('Converter file created at'), label
        end
      end
    end
  end
end
