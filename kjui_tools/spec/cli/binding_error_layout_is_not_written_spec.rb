# frozen_string_literal: true

require 'open3'
require 'rbconfig'
require 'tmpdir'
require 'json'
require 'digest'
require 'fileutils'

# A layout whose bindings carry an ERROR is not written: its generated files
# (GeneratedView, Data — and its variants, which build_file writes with it) stay as the last good build left them, the build says
# so and exits 1 as before, and the layout is not cached — the build after the
# fix converts it again. Until jsonui-cli 1.9.8 the bindings were checked in
# the conversion loop, after the Data models were written, and the layout was
# converted anyway (ticket failed-build-writes-the-generated-files).
#
# The control: the other layout, edited between the builds, IS written by the
# failing build.
RSpec.describe 'kjui build: a layout with a binding ERROR is not written' do
  def tool_root
    File.expand_path('../..', __dir__)
  end

  def name
    'BindingProbe'
  end

  def layout(text_field_text, label_text)
    { 'type' => 'View', 'id' => 'root', 'width' => 'matchParent', 'height' => 'matchParent',
      'orientation' => 'vertical',
      'data' => [{ 'name' => 'profileName', 'class' => 'String', 'defaultValue' => '' }],
      'child' => [
        { 'type' => 'TextField', 'id' => 'name_field', 'width' => 'matchParent', 'height' => 'wrapContent',
          'text' => text_field_text },
        { 'type' => 'Label', 'id' => 'title', 'width' => 'wrapContent', 'height' => 'wrapContent',
          'text' => label_text }
      ] }
  end

  def write_layouts(bad_text, good_label, bad_label = 'Bad')
    sleep 1.1 # the build cache compares mtimes in seconds
    File.write(File.join(@layouts, 'bad_form.json'), JSON.generate(layout(bad_text, bad_label)))
    File.write(File.join(@layouts, 'good_form.json'), JSON.generate(layout('@{profileName}', good_label)))
  end

  def build
    log, status = Open3.capture2e(RbConfig.ruby, File.join(@dir, 'kjui_tools', 'bin', 'kjui'), 'build', chdir: @dir)
    [log.gsub(/\e\[[0-9;]*m/, ''), status]
  end

  def outputs(stem)
    Dir.glob(File.join(@dir, 'app', '**', "#{stem}*.kt")).sort
  end

  def digests(files)
    files.to_h { |f| [f, Digest::MD5.file(f).hexdigest] }
  end

  before(:all) do
    @dir = Dir.mktmpdir('kjui_binding_error')
    tool = File.join(@dir, 'kjui_tools')
    FileUtils.mkdir_p(tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), tool)
    end
    File.write(File.join(@dir, 'kjui.config.json'), JSON.pretty_generate(
      'mode' => 'compose', 'project_name' => name,
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

    write_layouts('@{profileName}', 'Before')
    @log1, @status1 = build
    @bad_before = digests(outputs('BadForm'))
    @good_before = digests(outputs('GoodForm'))

    # The ERROR: a two-way field whose value mixes literal text with a binding.
    # Its label changes too, so the refused layout's output WOULD differ if it
    # were written — a face that draws the mixed value as the bare binding
    # (kjui) emits the same file for it, and the byte-for-byte arm would hold
    # on the parent for the wrong reason.
    write_layouts('Name: @{profileName}', 'After', 'Bad Changed')
    @log2, @status2 = build
    @bad_after = digests(outputs('BadForm'))
    @good_after = digests(outputs('GoodForm'))

    # Fixed, with only the label changed — the refused layout was not cached,
    # so this build converts it again.
    write_layouts('@{profileName}', 'After', 'Bad Changed')
    @bad_layout_mtime_fix = File.mtime(File.join(@layouts, 'bad_form.json'))
    @log3, @status3 = build
    @bad_fixed = digests(outputs('BadForm'))
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  it 'the first build is clean and writes both layouts (the premise)' do
    expect(@status1.exitstatus).to eq(0), @log1
    expect(@bad_before.keys.map { |f| File.basename(f) }).to include('BadFormGeneratedView.kt', 'BadFormData.kt')
  end

  it 'the failing build exits 1 and names the layout it did not write' do
    expect(@status2.exitstatus).to eq(1), @log2
    expect(@log2).to match(/bad_form\.json was not written: 1 binding error\(s\) — its generated files are the last build's/)
    expect(@log2).not_to match(/good_form\.json was not written/)
  end

  it "keeps the refused layout's generated files byte for byte" do
    expect(@bad_after).to eq(@bad_before)
  end

  it 'still writes the other layout (control: the build carried on)' do
    view = @good_after.keys.find { |f| File.basename(f) == 'GoodFormGeneratedView.kt' }
    expect(@good_after[view]).not_to eq(@good_before[view])
    # A Label literal may go through a string resource, not as text.
    expect(File.read(view)).to match(/after/i)
  end

  it 'converts the refused layout again once it is fixed (it was not cached)' do
    expect(@status3.exitstatus).to eq(0), @log3
    expect(@log3).not_to match(/was not written/)
    expect(@bad_fixed.keys).to eq(@bad_before.keys)
  end
end
