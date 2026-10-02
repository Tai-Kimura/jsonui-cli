# frozen_string_literal: true

require 'swiftui/generators/collection_generator'
require 'open3'
require 'tmpdir'

# A scaffolded cell draws the item it is given. The cell ViewModel knew a cell
# only by the "cellId" the Collection writes, and a Collection writes one only
# under autoChangeTrackingId + cellIdProperty: with neither, nil == nil and the
# first setData returned before reading anything, so every cell drew the
# Data's defaults ("Item"), with the build at warning 0. From 1.9.6 the build
# scaffolds this ViewModel for a hand-written cell layout (3ecbc61f), which is
# how 13 ConformanceHost probes went blank on the generated face (measured
# 2026-10-03; green on jsonui-cli 1.9.5, whose host wrote its own wrapper).
#
# The drawn arm is those probes. Here: the ViewModel compiled and RUN.
RSpec.describe 'sjui: a scaffolded cell ViewModel reads its data' do
  def scaffold(dir)
    allow(SjuiTools::Core::ProjectFinder).to receive(:project_dir).and_return(dir)
    allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
    allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    generator = SjuiTools::SwiftUI::Generators::CollectionGenerator.new('probe_cell')
    allow(generator).to receive(:puts)
    generator.generate
  end

  it 'loads an item with no cellId, follows a changed one, and keeps a cellId as the identity' do
    unless system('which swiftc > /dev/null 2>&1')
      raise 'swiftc is not on PATH in CI' if ENV['CI']

      skip 'swiftc is not on PATH: the ViewModel run is UNMEASURED here'
    end
    Dir.mktmpdir do |dir|
      scaffold(dir)
      sources = [File.join(dir, 'Data', 'ProbeCellData.swift'), File.join(dir, 'ViewModel', 'ProbeCellViewModel.swift')]
      program = sources.map { |p| File.read(p).gsub(/^import SwiftJsonUI\n/, '') }.join("\n") + <<~SWIFT
        let vm = ProbeCellViewModel()
        vm.setData(["title": "A0"])
        print(vm.data.title)
        vm.setData(["title": "A1"])
        print(vm.data.title)
        vm.setData(["title": "B", "cellId": "k"])
        print(vm.data.title)
        vm.setData(["title": "C", "cellId": "k"])
        print(vm.data.title)
      SWIFT
      File.write(File.join(dir, 'main.swift'), program)
      out, err, status = Open3.capture3('swiftc', '-o', File.join(dir, 'main'), File.join(dir, 'main.swift'))
      expect(status).to be_success, out + err
      got, _, run = Open3.capture3(File.join(dir, 'main'))
      expect(run).to be_success
      expect(got.lines.map(&:chomp)).to eq(%w[A0 A1 B B])
    end
  end

  it 'the View compares and reloads by the same key' do
    Dir.mktmpdir do |dir|
      scaffold(dir)
      view = File.read(File.join(dir, 'View', 'ProbeCell', 'ProbeCellView.swift'))
      expect(view).to include('self.cellKey = ProbeCellViewModel.cellKey(of: data)',
                              'lhs.cellKey == rhs.cellKey', '.onChange(of: cellKey)')
      expect(view).not_to include('cellId')
    end
  end
end
