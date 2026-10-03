# frozen_string_literal: true

require 'open3'
require 'rbconfig'
require 'tmpdir'
require 'json'
require 'digest'
require 'fileutils'

# A layout whose bindings carry an ERROR is not written: its generated files
# stay as the last good build left them, and the build says so — then exits 1
# as before. Until jsonui-cli 1.9.8 the build wrote that layout's component,
# Data and hook anyway (the bindings were checked inside the component loop,
# after the Data models were written) and then failed: a failed build that had
# replaced good files with broken ones (measured on a consumer copy: the
# component's input `value` became `Name: ${data.profileName ?? ""}` and its
# onChange `data.onChange?.`). Ticket failed-build-writes-the-generated-files.
#
# The control: the other layout, edited between the two builds, IS written by
# the failing build — the build carries on, only the refused layout is held.
RSpec.describe 'rjui build: a layout with a binding ERROR is not written' do
  def tool_root
    File.expand_path('../..', __dir__)
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

  def build
    log, status = Open3.capture2e(RbConfig.ruby, File.join(@tool, 'bin', 'rjui'), 'build', chdir: @dir)
    [log.gsub(/\e\[[0-9;]*m/, ''), status]
  end

  def outputs(stem)
    Dir.glob(File.join(@dir, 'src', 'generated', '**', "*#{stem}*")).select { |f| File.file?(f) }.sort
  end

  def digests(files)
    files.to_h { |f| [f, Digest::MD5.file(f).hexdigest] }
  end

  before(:all) do
    @dir = Dir.mktmpdir('rjui_binding_error')
    @tool = File.join(@dir, 'rjui_tools')
    FileUtils.mkdir_p(@tool)
    %w[bin lib].each do |d|
      raise "could not copy #{d}" unless system('cp', '-RL', File.join(tool_root, d), @tool)
    end
    @layouts = File.join(@dir, 'src', 'Layouts')
    FileUtils.mkdir_p(@layouts)
    File.write(File.join(@layouts, 'bad_form.json'), JSON.generate(layout('@{profileName}', 'Bad')))
    File.write(File.join(@layouts, 'good_form.json'), JSON.generate(layout('@{profileName}', 'Before')))

    @log1, @status1 = build
    @bad_before = digests(outputs('BadForm'))
    @good_before = digests(outputs('GoodForm'))

    # The ERROR: a two-way field whose value mixes literal text with a binding.
    # Its label changes too, so the refused layout's output WOULD differ if it
    # were written (a face drawing the mixed value as the bare binding would
    # otherwise emit the same file, and the byte-for-byte arm would hold on the
    # parent for the wrong reason).
    File.write(File.join(@layouts, 'bad_form.json'), JSON.generate(layout('Name: @{profileName}', 'Bad Changed')))
    File.write(File.join(@layouts, 'good_form.json'), JSON.generate(layout('@{profileName}', 'After')))
    @log2, @status2 = build
    @bad_after = digests(outputs('BadForm'))
    @good_after = digests(outputs('GoodForm'))
  end

  after(:all) { FileUtils.rm_rf(@dir) }

  it 'the first build is clean and writes both layouts (the premise)' do
    expect(@status1.exitstatus).to eq(0), @log1
    # rjui's defaults (no rjui.config.json): JavaScript, so .jsx / .js.
    expect(@bad_before.keys.map { |f| File.basename(f, '.*') }).to include('BadForm', 'BadFormData')
    expect(@good_before.size).to eq(@bad_before.size)
  end

  it 'the failing build exits 1 and names the layout it did not write' do
    expect(@status2.exitstatus).to eq(1), @log2
    expect(@log2).to match(%r{bad_form\.json was not written: 1 binding error\(s\) — its generated files are the last build's})
    expect(@log2).not_to match(/good_form\.json was not written/)
  end

  it "keeps the refused layout's generated files byte for byte" do
    expect(@bad_after).to eq(@bad_before)
  end

  it 'still writes the other layout (control: the build carried on)' do
    expect(@good_after.keys).to eq(@good_before.keys)
    changed = @good_after.select { |f, d| @good_before[f] != d }.keys.map { |f| File.basename(f, '.*') }
    expect(changed).to include('GoodForm')
    expect(File.read(@good_after.keys.find { |f| File.basename(f, '.*') == 'GoodForm' })).to include('After')
  end
end
