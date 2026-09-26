# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# What `sjui g view / partial / collection / adapter` print about each file,
# held to what happened on disk (a snapshot before and after each run, not
# anything the generators record), on a new project and on a run again over
# the same files with stdin closed. SwiftUI mode, and UIKit mode on a real
# (empty) Xcode project, which it patches.
#
# Until 1.8.121 (measured on 1b80b5ba + the reporting fixes, 2026-09-26): run
# again, `g view` said "Generated SwiftUI view:" with its five files when it
# wrote none; `g partial` "Generated partial:" after "File already exists";
# `g adapter` "Successfully generated adapter" after keeping it; UIKit `g view`
# "Created ViewController" for a file it overwrote, "Added files to Xcode
# project" after "File already in project" (logged as an ERROR) for every
# file, and "Successfully generated:" with a ViewModel it had kept; UIKit
# `g partial` / `g collection` "Successfully generated …" and "File(s)
# created" for files that were already there. Ticket
# kjui-g-view-reports-what-it-did-not-do (widened to every generate command).
RSpec.describe 'what sjui g view / partial / collection / adapter say they did, against the disk' do
  def tool_root
    File.expand_path('../../..', __dir__)
  end

  # [label, mode, generate arguments]
  def self.commands
    [
      ['swiftui view', 'swiftui', %w[view home]],
      ['swiftui partial', 'swiftui', %w[partial header]],
      ['swiftui collection', 'swiftui', %w[collection item_cell]],
      ['swiftui adapter', 'swiftui', %w[adapter Card]],
      ['uikit view', 'uikit', %w[view home]],
      ['uikit partial', 'uikit', %w[partial header]],
      ['uikit collection', 'uikit', %w[collection Item/Cell]]
    ]
  end

  def project(dir, mode)
    tool = File.join(dir, 'sjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    File.write(File.join(dir, 'sjui.config.json'), JSON.pretty_generate(
      'mode' => mode, 'project_name' => 'P', 'project_file_name' => 'P', 'source_directory' => 'P',
      'layouts_directory' => 'Layouts', 'resources_directory' => 'Resources', 'styles_directory' => 'Styles',
      'view_directory' => 'View', 'data_directory' => 'Data', 'viewmodel_directory' => 'ViewModel',
      'resource_manager_directory' => 'ResourceManager', 'string_files' => ['P/Localizable.strings'],
      'use_network' => true, 'adapter_directory' => 'Extensions/Adapters'
    ))
    FileUtils.mkdir_p(File.join(dir, 'P', 'Layouts'))
    # A real, empty Xcode project: UIKit mode adds its files to it.
    script = "require 'xcodeproj'; pr = Xcodeproj::Project.new(ARGV[0]); pr.new_target(:application, 'P', :ios); " \
             "pr.main_group.new_group('P', 'P'); pr.save"
    raise 'could not make an Xcode project' unless system('ruby', '-e', script, File.join(dir, 'P.xcodeproj'))

    tool
  end

  def snapshot(dir)
    Dir.glob(File.join(dir, '**', '*'), File::FNM_DOTMATCH).select { |f| File.file?(f) }
       .reject { |f| f.include?('/sjui_tools/') }
       .to_h { |f| [File.realpath(f), File.mtime(f)] }
  end

  def run_twice(mode, args)
    dir = Dir.mktmpdir('sjui_g_report')
    tool = project(dir, mode)
    %w[new again].map do |run|
      before = snapshot(dir)
      sleep 0.01
      said, = Open3.capture2e('ruby', File.join(tool, 'bin', 'sjui'), 'g', *args, chdir: dir, stdin_data: '')
      after = snapshot(dir)
      disk = after.to_h { |f, m| [f, !before.key?(f) ? :created : (before[f] == m ? :untouched : :rewritten)] }
      [run, said.gsub(/\e\[[0-9;]*m/, ''), disk, dir]
    end
  end

  before(:all) do
    @runs = self.class.commands.to_h { |label, mode, args| [label, run_twice(mode, args)] }
  end

  after(:all) { @runs.values.flatten(1).map(&:last).uniq.each { |dir| FileUtils.rm_rf(dir) } }

  # The file a line names (resolved in the project), or nil.
  def named_file(line, dir)
    token = line[%r{(?:/|\b)[\w./-]+\.(?:swift|json)\b}]
    return nil unless token

    full = File.expand_path(token, dir)
    File.exist?(full) ? File.realpath(full) : nil
  end

  def claim(line)
    case line
    when /\bKept\b|\bkept\b|Skipped existing|already exists|Unchanged/ then :untouched
    when /Overwrote|\(overwritten\)/ then :rewritten
    when /\bCreated\b|\(created\)|File created/ then :created
    end
  end

  def scaffold(disk)
    disk.reject { |f, _| f.include?('/.sjui_cache/') || f.end_with?('project.pbxproj') }
  end

  it 'runs each command twice as it is meant to (the precondition): the first run creates files' do
    aggregate_failures do
      @runs.each do |label, ((_, said, disk, _), _)|
        expect(scaffold(disk).values).to include(:created), "#{label}: #{said}"
      end
    end
  end

  it 'says of each file what happened to it on disk' do
    checked = 0
    aggregate_failures do
      @runs.each do |label, runs|
        runs.each do |run, said, disk, dir|
          said.lines.each do |line|
            file = named_file(line, dir)
            want = claim(line)
            next unless file && want && disk.key?(file)

            checked += 1
            expect(disk[file]).to eq(want), "#{label} (#{run}): #{line.strip} — on disk #{disk[file]}"
          end
        end
      end
    end
    expect(checked).to be >= 40
  end

  it 'says nothing was generated by a run that wrote no scaffold file' do
    aggregate_failures do
      @runs.each do |label, runs|
        runs.each do |run, said, disk, _|
          next if scaffold(disk).values.any? { |s| s != :untouched }

          expect(said).not_to match(/Successfully generated|^Generated |Files? created|Added \d+ file|Added (collection cell|JSON layout) to Xcode/),
                              "#{label} (#{run}): #{said}"
        end
      end
    end
  end

  it 'says it added files to the Xcode project exactly when the project changed' do
    aggregate_failures do
      @runs.each do |label, runs|
        next unless label.start_with?('uikit')

        runs.each do |run, said, disk, _|
          changed = disk.any? { |f, s| f.end_with?('project.pbxproj') && s != :untouched }
          expect(said.match?(/Added \d+ file\(s\) to Xcode project|Added (collection cell|JSON layout) to Xcode project|Added to Xcode project/))
            .to eq(changed), "#{label} (#{run}): #{said}"
          expect(said).not_to include('ERROR: File already in project'), label
        end
      end
    end
  end
end
