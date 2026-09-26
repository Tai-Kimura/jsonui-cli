# frozen_string_literal: true

require 'open3'
require 'rbconfig'
require 'tmpdir'
require 'json'
require 'fileutils'

# A text field's declared onClick is not called — its own tap focuses it
# (ticket control-onclick-is-called-differently-on-every-path) — and the
# build says so once per node, in the sentence the three tools share
# (JsonUIShared::AttributeValidatorCore#check_text_field_click). A text field
# with no onClick, and a control given one, are not named.
#
# The tool is COPIED (links dereferenced), as the other build specs do.
RSpec.describe 'onClick on a text field, through sjui build' do
  def tool_root
    File.expand_path('../../..', __dir__)
  end

  before(:all) do
    @dir = Dir.mktmpdir('sjui_field_click')
    tool = File.join(@dir, 'sjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    name = 'FieldProbe'
    File.write(File.join(@dir, 'sjui.config.json'), JSON.pretty_generate(
      'mode' => 'swiftui', 'project_name' => name, 'project_file_name' => name,
      'source_directory' => name, 'layouts_directory' => 'Layouts',
      'resources_directory' => 'Resources', 'styles_directory' => 'Styles',
      'view_directory' => 'View', 'data_directory' => 'Data',
      'viewmodel_directory' => 'ViewModel',
      'resource_manager_directory' => 'ResourceManager',
      'string_files' => ["#{name}/Localizable.strings"], 'use_network' => true
    ))
    FileUtils.mkdir_p(File.join(@dir, "#{name}.xcodeproj"))
    @layouts = File.join(@dir, name, 'Layouts')
    FileUtils.mkdir_p(@layouts)

    node = ->(type, id, extra = {}) { { 'type' => type, 'id' => id, 'width' => 'matchParent', 'height' => 'wrapContent' }.merge(extra) }
    File.write(File.join(@layouts, 'fields.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical',
      'child' => [
        node.call('TextField', 'search', 'onClick' => '@{onSearchTap}'),
        node.call('TextView', 'memo', 'onclick' => 'memoTapped'),
        node.call('TextField', 'plain'),
        node.call('Switch', 'toggle', 'onClick' => '@{onToggle}')
      ]
    ))
    @log, @status = Open3.capture2e(RbConfig.ruby, File.join(tool, 'bin', 'sjui'), 'build', chdir: @dir)
    @log = @log.gsub(/\e\[[0-9;]*m/, '')
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  def said(id)
    @log.lines.grep(/id=#{id}\]/).grep(/is not called: a text field's tap focuses it/)
  end

  it 'builds' do
    expect(@status).to be_success, @log[-3000..]
  end

  it 'names each text field given an onClick once, in the one sentence' do
    expect(said('search').size).to eq(1), @log
    expect(said('search').first).to include("onClick on a TextField is not called: a text field's tap focuses it")
    expect(said('memo').size).to eq(1), @log
    expect(said('memo').first).to include("onClick on a TextView is not called: a text field's tap focuses it")
  end

  it 'says nothing for a text field with no onClick, or for a control' do
    expect(said('plain')).to be_empty
    expect(@log.lines.grep(/id=toggle\]/).grep(/not called/)).to be_empty
    expect(@log.scan(/is not called: a text field's tap focuses it/).size).to eq(2), @log
  end
end
