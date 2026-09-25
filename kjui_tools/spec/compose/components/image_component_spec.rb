# frozen_string_literal: true

require 'compose/components/image_component'
require 'compose/helpers/modifier_builder'

RSpec.describe KjuiTools::Compose::Components::ImageComponent do
  let(:required_imports) { Set.new }

  describe '.generate' do
    it 'generates basic Image component' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Image(')
      expect(result).to include('painterResource')
      expect(result).to include('icon_home')
    end

    it 'generates Image with size' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'size' => 48 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.size(48.dp)')
    end

    it 'generates Image with width and height' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'width' => 100, 'height' => 50 }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.size(100.dp, 50.dp)')
    end

    it 'generates Image with contentMode aspectFill' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'contentMode' => 'aspectFill' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentScale = ContentScale.Crop')
      expect(required_imports).to include(:content_scale)
    end

    it 'generates Image with contentMode aspectFit' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'contentMode' => 'aspectFit' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentScale = ContentScale.Fit')
    end

    it 'generates Image with contentMode center' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'contentMode' => 'center' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentScale = ContentScale.None')
    end

    it 'generates Image with contentDescription' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home', 'contentDescription' => 'Home icon' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentDescription = "Home icon"')
    end

    it 'adds required imports' do
      json_data = { 'type' => 'Image', 'src' => 'icon_home' }
      described_class.generate(json_data, 0, required_imports)
      expect(required_imports).to include(:image)
      expect(required_imports).to include(:painter_resource)
      expect(required_imports).to include(:r_class)
    end

    it 'uses placeholder when no src provided' do
      json_data = { 'type' => 'Image' }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('placeholder')
    end
  end
end

# renderingMode: `template` means "take the tint, ignore the asset's own
# colours" — a ColorFilter here, `.renderingMode(.template)` on iOS.
RSpec.describe KjuiTools::Compose::Components::ImageComponent, 'renderingMode' do
  let(:required_imports) { Set.new }

  def image(extra)
    described_class.generate({ 'type' => 'Image', 'src' => 'logo' }.merge(extra), 0, required_imports)
  end

  # Compose's stand-in for "the current foreground colour", which is what a
  # template image takes on iOS.
  it 'tints with the content colour when no tint is given' do
    expect(image('renderingMode' => 'template'))
      .to include('colorFilter = ColorFilter.tint(LocalContentColor.current)')
    expect(required_imports).to include(:color_filter, :local_content_color)
  end

  it 'tints with the given colour' do
    expect(image('renderingMode' => 'template', 'tintColor' => '#FF0000'))
      .to match(/colorFilter = ColorFilter\.tint\(Color\(.*FF0000/)
  end

  # `original` says the opposite, so it suppresses a tint that would otherwise
  # apply.
  it 'suppresses a tint for original' do
    expect(image('renderingMode' => 'original', 'tintColor' => '#FF0000')).not_to include('colorFilter')
  end

  it 'still tints without a renderingMode' do
    expect(image('tintColor' => '#FF0000')).to include('ColorFilter.tint(')
  end

  it 'emits nothing when neither is set' do
    expect(image({})).not_to include('colorFilter')
  end
end

# What TalkBack reads for an image: its alt (a strings.json key or text,
# localized like `text`, or a binding), nothing for a decorative image, and —
# for an image that operates a control and has no alt — what it read before
# alt existed (shared/core/image_accessibility.rb). The roles come from the
# vectors the sjui codegen and both Dynamic runtimes also run.
RSpec.describe 'kjui image contentDescription from alt' do
  require 'compose/components/networkimage_component'
  require 'compose/components/circleimage_component'
  require 'compose/components/iconlabel_component'
  require 'core/image_accessibility'
  require 'json'

  rule = JsonUIShared::ImageAccessibility
  vectors_path = File.expand_path('../../../../shared/core/image_accessibility_vectors.json', __dir__)

  # What each converter read before alt existed, kept for a control image.
  LEGACY = { 'Image' => ->(node) { node['id'] }, 'NetworkImage' => ->(_) { 'Image' },
             'CircleImage' => ->(_) { 'Profile Image' } }.freeze

  def emit(node)
    component = case node['type']
                when 'NetworkImage' then KjuiTools::Compose::Components::NetworkImageComponent
                when 'CircleImage' then KjuiTools::Compose::Components::CircleImageComponent
                else KjuiTools::Compose::Components::ImageComponent
                end
    component.generate(node, 0, Set.new)
  end

  def spoken(result)
    result[/contentDescription = (.*?),?$/, 1]
  end

  def images(node, out = [])
    return out unless node.is_a?(Hash)

    out << node if JsonUIShared::ImageAccessibility.image?(node)
    JsonUIShared::ImageAccessibility.children(node).each { |c| images(c, out) }
    out
  end

  if File.exist?(vectors_path)
    JSON.parse(File.read(vectors_path))['cases'].each do |vector|
      it "emits each role: #{vector['name']}" do
        layout = JSON.parse(JSON.generate(vector['layout']))
        rule.annotate!(layout, source_path: 'probe.json')
        images(layout).each do |node|
          said = spoken(emit(node))
          case vector['roles'][node['id']]
          when 'decorative' then expect(said).to eq('null'), node['id']
          when 'control' then expect(said).to eq("\"#{LEGACY.fetch(node['type']).call(node)}\""), node['id']
          when 'label'
            alt = rule.alt(node)
            if alt.start_with?('@{')
              expect(said).to match(/\A\(".*data\.#{alt[2..-2]}.*"\)\.ifEmpty \{ null \}\z/), node['id']
            else
              expect(said).to eq("\"#{alt}\""), node['id']
            end
          else raise "no role for #{node['id']}"
          end
        end
      end
    end
  end

  it 'reads nothing from the icon of an IconLabel, whose label names it' do
    result = KjuiTools::Compose::Components::IconLabelComponent.generate(
      { 'type' => 'IconLabel', 'text' => 'Home', 'icon' => 'ic_home' }, 0, Set.new
    )
    expect(spoken(result)).to eq('null')
  end
end

# The tappable around an image is only visible to the builder, which writes
# each image's role after expanding includes. The same image, alone in a
# tappable and then beside a Label in it.
RSpec.describe 'kjui build: the role reaches the image converter' do
  require 'compose/compose_builder'
  require 'json'
  require 'tmpdir'
  require 'stringio'

  let(:temp_dir) { Dir.mktmpdir('kjui_image_role') }
  let(:layouts_dir) { File.join(temp_dir, 'src/main/assets/Layouts') }

  before do
    FileUtils.mkdir_p(layouts_dir)
    config = { 'source_directory' => 'src/main', 'layouts_directory' => 'assets/Layouts',
               'view_directory' => 'kotlin/com/example/app/views', 'package_name' => 'com.example.app' }
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(config)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
    allow(Dir).to receive(:pwd).and_return(temp_dir)
  end

  after { FileUtils.rm_rf(temp_dir) }

  def build(children)
    layout = { 'type' => 'View', 'child' => [
      { 'data' => [{ 'name' => 'onMenu', 'class' => '(() -> Void)?' }] },
      { 'type' => 'View', 'onClick' => '@{onMenu}', 'child' => children }
    ] }
    File.write(File.join(layouts_dir, 'probe.json'), JSON.generate(layout))
    printed = StringIO.new
    errors = StringIO.new
    $stdout = printed
    $stderr = errors
    begin
      KjuiTools::Compose::ComposeBuilder.new.build_file(File.join(layouts_dir, 'probe.json'))
    ensure
      $stdout = STDOUT
      $stderr = STDERR
    end
    [File.read(Dir.glob(File.join(temp_dir, '**', 'ProbeGeneratedView.kt')).first), errors.string]
  end

  let(:icon) { { 'type' => 'Image', 'id' => 'menu_icon', 'src' => 'menu' } }

  it 'keeps the id of the only image of a tappable, and names it' do
    src, printed = build([icon])
    expect(src).to include('contentDescription = "menu_icon"')
    expect(printed).to include("[info] probe.json: Image 'menu_icon' operates a control and has no alt")
  end

  it 'skips the same image beside text, and says nothing' do
    src, printed = build([icon, { 'type' => 'Label', 'text' => 'Menu' }])
    expect(src).to include('contentDescription = null')
    expect(src).not_to include('contentDescription = "menu_icon"')
    expect(printed).not_to include('[info]')
  end
end
