# frozen_string_literal: true

require 'swiftui/include_expander'
require 'json'
require 'fileutils'
require 'tmpdir'

# Every include path resolves from the layouts ROOT (design U8, 2026-09-25).
# The Python normalizer, rjui and both dynamic runtimes read include paths
# from the root, and the layouts measured on the consumer faces are written
# that way: all three nested references resolve from the root and none from
# the including file's directory — which this expander used, so a screen or a
# partial in a subdirectory failed with "Include file not found".
RSpec.describe SjuiTools::SwiftUI::IncludeExpander do
  let(:root) { File.realpath(Dir.mktmpdir('include_root')) }

  def write(rel, data)
    path = File.join(root, rel)
    FileUtils.mkdir_p(File.dirname(path))
    File.write(path, JSON.generate(data))
    path
  end

  before do
    # A screen in a subdirectory, including a partial by its root path; the
    # partial, in a subdirectory too, includes another by its root path.
    write('alpha/screen_one.json', { 'type' => 'View', 'id' => 'root',
                                   'child' => [{ 'include' => 'alpha/part_two', 'id' => 'two' }] })
    write('alpha/part_two.json', { 'type' => 'View', 'id' => 'box',
                                       'child' => [{ 'include' => 'beta/part_three', 'id' => 'three' }] })
    write('beta/part_three.json', { 'type' => 'View', 'id' => 'row',
                                 'child' => [{ 'type' => 'Label', 'id' => 'leaf_label' }] })
  end

  after do
    described_class.layouts_root = nil
    FileUtils.rm_rf(root)
  end

  def ids(node, out = [])
    if node.is_a?(Hash)
      out << node['id'] if node['id']
      Array(node['child']).each { |c| ids(c, out) }
    end
    out
  end

  def screen_one
    JSON.parse(File.read(File.join(root, 'alpha/screen_one.json')))
  end

  it 'resolves a subdirectory screen\'s include and a nested one from the root it is given' do
    expanded = described_class.process_includes(screen_one, File.join(root, 'alpha'), nil, root)
    expect(ids(expanded)).to eq(%w[root twoBox twoThreeRow twoThreeLeafLabel])
  end

  it 'uses the root an entry point set, when none is passed' do
    described_class.layouts_root = root
    expanded = described_class.process_includes(screen_one, File.join(root, 'alpha'))
    expect(ids(expanded)).to eq(%w[root twoBox twoThreeRow twoThreeLeafLabel])
  end

  it 'without a root, still resolves from base_dir (the control: the old reading)' do
    expect { described_class.process_includes(screen_one, File.join(root, 'alpha')) }
      .to raise_error(/Include file not found: .*alpha\/alpha\/part_two\.json/)
  end

  it 'a top-level screen resolves the same either way' do
    write('home.json', { 'type' => 'View', 'id' => 'root',
                         'child' => [{ 'include' => 'beta/part_three', 'id' => 'three' }] })
    home = JSON.parse(File.read(File.join(root, 'home.json')))
    with_root = described_class.process_includes(JSON.parse(JSON.generate(home)), root, nil, root)
    without = described_class.process_includes(JSON.parse(JSON.generate(home)), root)
    expect(with_root).to eq(without)
  end
end
