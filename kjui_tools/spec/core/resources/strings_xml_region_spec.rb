# frozen_string_literal: true

require 'core/resources/string_manager'
require 'rexml/document'
require 'tmpdir'
require 'json'

# kjui writes its entries in a marked region of strings.xml, rewritten from
# strings.json on every build, and never touches what is outside it (ticket
# face-strings-json-keeps-a-section-the-shared-copy-removed). It upserted into
# the whole file and pruned only inside a namespace a layout or a section
# claims, so a key whose layout and section were both gone stayed forever:
# nothing told it from a hand-written string.
RSpec.describe KjuiTools::Core::Resources::StringManager, 'the generated region of strings.xml' do
  let(:temp_dir) { Dir.mktmpdir }
  let(:config) { { 'source_directory' => 'src/main', 'package_name' => 'com.example.app' } }
  let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }
  let(:resources_dir) { File.join(layouts_dir, 'Resources') }
  let(:xml_path) { File.join(temp_dir, 'src/main/res/values/strings.xml') }
  let(:shared) { { 'home' => { 'title' => { 'en' => 'Home', 'ja' => 'ホーム' } } } }

  before do
    FileUtils.mkdir_p(resources_dir)
    File.write(File.join(layouts_dir, 'home.json'), '{"type": "View", "id": "root"}')
    allow(KjuiTools::Core::Logger).to receive(:info)
    allow(KjuiTools::Core::Logger).to receive(:debug)
  end

  after { FileUtils.rm_rf(temp_dir) }

  # One build as jui runs it: the face strings.json is the shared copy, then
  # extraction over every layout, then strings.xml.
  def build(strings)
    File.write(File.join(resources_dir, 'strings.json'), JSON.pretty_generate(strings))
    manager = described_class.new(config, temp_dir, resources_dir)
    manager.process_strings([File.join(layouts_dir, 'home.json')], 1, 0)
    manager.apply_to_strings_files
    File.read(xml_path)
  end

  def pairs(xml)
    REXML::Document.new(xml).root.elements.to_a.to_h { |e| [e.attributes['name'], e.to_s] }
  end

  def outside_region(xml)
    xml.split('JsonUI generated strings (kjui): begin').first
  end

  it 'comes back byte-identical after a section with no layout is added and removed' do
    before = build(shared)
    with_probe = build(shared.merge('zz_probe' => { 'probe_key' => 'Probe Removed Text' }))
    expect(with_probe).to include('Probe Removed Text') # control: the probe reached strings.xml
    expect(build(shared)).to eq(before)
  end

  it 'leaves a hand-written entry outside the region alone, a name kjui would manage included' do
    build(shared)
    hand = File.read(xml_path).sub('<resources>', "<resources>\n    <string name=\"app_name\">My App</string>\n    " \
                                                   '<string name="home_footer">Hand footer</string>')
    File.write(xml_path, hand)
    after = build(shared)
    expect(outside_region(after)).to include('My App').and include('Hand footer')
    expect(after.scan(/name=["']home_title["']/).size).to eq(1)
  end

  it 'moves kjui\'s entries into the region on the first build and keeps every name and value' do
    FileUtils.mkdir_p(File.dirname(xml_path))
    File.write(xml_path, <<~XML)
      <?xml version='1.0' encoding='utf-8'?>
      <resources>
          <string name="home_title">Home</string>
          <string name="app_name">My App</string>
      </resources>
    XML
    old = pairs(File.read(xml_path))
    after = build(shared)
    expect(pairs(after)).to eq(old)
    expect(outside_region(after)).to include('app_name')
    expect(outside_region(after)).not_to include('home_title')
    expect(KjuiTools::Core::Logger).to have_received(:info).with(%r{values/strings.xml: moved 1 entry into the generated region \(1 hand-written left outside\)})
  end

  it 'moves into the region an entry outside it named as kjui generates (two of one name do not compile)' do
    build(shared)
    File.write(xml_path, File.read(xml_path).sub('<resources>', "<resources>\n    <string name=\"home_title\">Stray</string>"))
    after = build(shared)
    expect(after.scan(/name=["']home_title["']/).size).to eq(1)
    expect(outside_region(after)).not_to include('home_title')
  end

  it 'is idempotent: a second build with nothing changed writes the same bytes' do
    first = build(shared)
    expect(build(shared)).to eq(first)
  end
end
