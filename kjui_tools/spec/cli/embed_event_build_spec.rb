# frozen_string_literal: true

require 'open3'
require 'tmpdir'
require 'json'
require 'fileutils'

# An Embed event names the handler it calls as it is — a method of the
# parent ViewModel. A value that is not a name (`@{name}`, the binding
# spelling) is not called, and the build says so once per event, in the
# sentence the three tools share (JsonUIShared::BindingValidatorCore
# .embed_event_handler_problem). Until 1.8.121 the build said only that
# 'name' was not in data, and the three codegens wrote
# `viewModel.@{name}(…)`, which does not parse (ticket
# rjui-embed-event-bridge-calls-an-undeclared-view-model).
#
# The tool is COPIED (links dereferenced), as the other build specs do.
RSpec.describe 'an Embed event that names no handler, through kjui build' do
  def tool_root
    File.expand_path('../..', __dir__)
  end

  before(:all) do
    @dir = Dir.mktmpdir('kjui_embed_event')
    tool = File.join(@dir, 'kjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    File.write(File.join(@dir, 'kjui.config.json'), JSON.pretty_generate(
      'mode' => 'compose', 'project_name' => 'FieldProbe',
      'source_directory' => 'app/src/main', 'layouts_directory' => 'assets/Layouts',
      'styles_directory' => 'assets/Styles',
      'data_directory' => 'kotlin/com/example/app/data',
      'viewmodel_directory' => 'kotlin/com/example/app/viewmodels',
      'view_directory' => 'kotlin/com/example/app/views',
      'extension_directory' => 'kotlin/com/example/app/extensions',
      'adapter_directory' => 'kotlin/com/example/app/adapters',
      'resource_manager_directory' => 'app/src/main/kotlin/com/kotlinjsonui/generated',
      'package_name' => 'com.example.app',
      'string_files' => ['res/values/strings.xml'], 'use_network' => true
    ))
    @layouts = File.join(@dir, 'app', 'src', 'main', 'assets', 'Layouts')
    FileUtils.mkdir_p(@layouts)
    FileUtils.mkdir_p(File.join(@dir, 'app', 'src', 'main', 'assets', 'Styles'))

    node = ->(id, extra = {}) { { 'type' => 'Embed', 'id' => id, 'width' => 'matchParent', 'height' => 200, 'screen' => 'order_detail' }.merge(extra) }
    File.write(File.join(@layouts, 'panes.json'), JSON.generate(
      'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent', 'orientation' => 'vertical',
      'child' => [
        node.call('detail_pane', 'events' => { 'onOrderUpdated' => 'handleOrderUpdated', 'onClose' => '@{closePane}' }),
        node.call('plain_pane')
      ]
    ))
    File.write(File.join(@layouts, 'order_detail.json'), JSON.generate(
      'type' => 'View', 'id' => 'detail_root', 'width' => 'matchParent', 'height' => 'matchParent',
      'child' => [{ 'type' => 'Label', 'id' => 'detail_title', 'text' => 'x', 'width' => 'wrapContent', 'height' => 'wrapContent' }]
    ))
    @log, @status = Open3.capture2e('ruby', File.join(tool, 'bin', 'kjui'), 'build', chdir: @dir)
    @log = @log.gsub(/\e\[[0-9;]*m/, '')
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  def said
    @log.lines.grep(/Embed event '/)
  end

  # Every file the build wrote that holds a bridge.
  def bridges
    Dir.glob(File.join(@dir, '**', '*')).reject { |f| f.include?('kjui_tools') || !File.file?(f) }
       .map { |f| File.read(f, encoding: 'UTF-8', invalid: :replace) }.select { |b| b.include?('eventBridge') }
  end

  it 'builds' do
    expect(@status).to be_success, @log[-3000..]
  end

  it 'names the event whose value names no handler, once, and nothing else' do
    expect(said.size).to eq(1), @log
    expect(said.first).to include('id=detail_pane]')
    expect(said.first).to include("Embed event 'onClose' is not called: '@{closePane}' is a binding; " \
                                  "an event names a method of the parent ViewModel as it is: 'closePane'")
  end

  it 'no longer says the handler is a binding missing from data' do
    expect(@log).not_to match(/Binding variable 'closePane'/)
    expect(@log.lines.grep(/closePane/).size).to eq(1), @log
  end

  it 'writes the named handler as a call and the other as a comment, nothing of it into code' do
    expect(bridges.size).to eq(1), bridges.size.to_s
    expect(bridges.first).to include('handleOrderUpdated')
    expect(bridges.first).to include('Embed event onClose names no handler, and is not called')
    expect(bridges.first).not_to include('@{closePane}')
  end
end
