# frozen_string_literal: true

require 'swiftui/views/image_converter'

RSpec.describe SjuiTools::SwiftUI::Views::ImageConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic image' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'icon_home'
        }
      end

      it 'generates Image view' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Image(')
        expect(code).to include('icon_home')
      end

      it 'adds resizable modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.resizable()')
      end

      it 'adds default aspectRatio fit' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.aspectRatio(contentMode: .fit)')
      end
    end

    context 'with srcName alias' do
      let(:component) do
        {
          'type' => 'Image',
          'srcName' => 'icon_settings'
        }
      end

      it 'uses srcName as src' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('icon_settings')
      end
    end

    context 'with contentMode AspectFit' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'photo',
          'contentMode' => 'AspectFit'
        }
      end

      it 'adds aspectRatio with fit' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.aspectRatio(contentMode: .fit)')
      end
    end

    context 'with contentMode fill / scaleToFill' do
      # fill = stretch (canonical image.fill = stretch,
      # shared/core/attribute_semantics.json): resizable WITHOUT an
      # aspectRatio modifier — SwiftUI has no stretch ContentMode member,
      # so absence of the modifier is the spelling.
      %w[fill scaleToFill].each do |mode|
        it "emits resizable without aspectRatio for #{mode}" do
          converter = described_class.new(
            { 'type' => 'Image', 'src' => 'photo', 'contentMode' => mode }
          )
          code = converter.convert
          expect(code).to include('.resizable()')
          expect(code).not_to include('.aspectRatio')
        end
      end
    end

    context 'with contentMode AspectFill' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'photo',
          'contentMode' => 'AspectFill'
        }
      end

      it 'adds aspectRatio with fill' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.aspectRatio(contentMode: .fill)')
      end
    end

    context 'with CircleImage type' do
      let(:component) do
        {
          'type' => 'CircleImage',
          'src' => 'avatar'
        }
      end

      it 'adds clipShape Circle' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.clipShape(Circle())')
      end
    end

    context 'with defaultImage' do
      let(:component) do
        {
          'type' => 'Image',
          'defaultImage' => 'placeholder'
        }
      end

      it 'uses defaultImage when no src' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Image("placeholder")')
      end
    end

    context 'with no image source' do
      let(:component) do
        {
          'type' => 'Image'
        }
      end

      it 'generates system photo image' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Image(systemName: "photo")')
      end
    end

    context 'with canTap and onclick' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'icon',
          'canTap' => true,
          'onClick' => 'handleTap'
        }
      end

      it 'adds onTapGesture' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.onTapGesture')
      end
    end

    context 'with background and cornerRadius' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'icon',
          'background' => '#F5F5F5',
          'cornerRadius' => 8
        }
      end

      it 'adds background modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.background(')
      end

      it 'adds cornerRadius modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.cornerRadius(8)')
      end
    end

    context 'with alpha/opacity' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'icon',
          'alpha' => 0.5
        }
      end

      it 'adds opacity modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0.5)')
      end
    end

    context 'with hidden' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'icon',
          'hidden' => true
        }
      end

      it 'adds hidden modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0).accessibilityHidden(true)')
      end
    end

    # `onSrc` is NOT an image-loaded callback. The SSoT declares it as an alias
    # of `CheckBox.selectedIcon` — a string icon path — and every
    # implementation with a provenance reads it that way. The callback reading
    # here arrived with the initial commit carrying no rationale, spec or
    # fixture, and turned the declared value into `data.<icon_name>?()`. The
    # 51-E ruling removed the read; this pins that it stays removed.
    context 'with onSrc' do
      let(:component) do
        {
          'type' => 'Image',
          'src' => 'photo',
          'onSrc' => 'star_on'
        }
      end

      it 'does not invent a callback out of an icon name' do
        code = described_class.new(component).convert

        expect(code).not_to include('data.star_on')
        expect(code).not_to include('Image loaded callback')
      end
    end

    # UIKit gets this free — UIImageView has `highlightedImage`, set by
    # SJUIImageView. SwiftUI has no such property, so the swap has to be driven
    # by a press gesture; the codegen emitted nothing at all.
    describe 'highlightSrc' do
      let(:component) do
        { 'type' => 'Image', 'id' => 'hero', 'src' => 'photo', 'highlightSrc' => 'photo_hl' }
      end

      it 'overlays the highlighted image and swaps on press' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('Image("photo_hl")')
        expect(code).to include('.onLongPressGesture(minimumDuration: 0')
      end

      it 'hides the base image while pressed, so the two do not stack' do
        code = described_class.new(component).convert

        expect(code).to include('.opacity(heroIsPressed ? 0 : 1)')
        expect(code).to include('.opacity(heroIsPressed ? 1 : 0)')
      end

      it 'declares the press flag as local view state, not a data property' do
        converter = described_class.new(component)
        converter.convert

        expect(converter.state_variables)
          .to include('@State private var heroIsPressed = false')
      end

      it 'emits nothing when absent' do
        code = described_class.new({ 'type' => 'Image', 'src' => 'photo' }).convert

        expect(code).not_to include('onLongPressGesture')
      end
    end
  end
  # systemIcon reinterprets `src` as an SF Symbol name, which is a different
  # Image initializer rather than a modifier.
  describe 'systemIcon' do
    it 'switches src to the systemName initializer' do
      code = described_class.new({ 'type' => 'Image', 'src' => 'star.fill', 'systemIcon' => true }, 0, nil).convert
      expect(code).to include('Image(systemName: "star.fill")')
      expect(code).not_to include('Image("star.fill")')
    end

    it 'treats src as an asset name without it' do
      code = described_class.new({ 'type' => 'Image', 'src' => 'star.fill' }, 0, nil).convert
      expect(code).to include('Image("star.fill")')
      expect(code).not_to include('systemName')
    end
  end
end

# What VoiceOver reads for an image: its alt (localized like `text`, or a
# binding), nothing for a decorative image, and — for an image that operates
# a control and has no alt — the asset name, as before alt existed
# (shared/core/image_accessibility.rb). The roles come from the vectors the
# kjui codegen and both Dynamic runtimes also run.
RSpec.describe 'sjui image accessibility from alt' do
  require 'swiftui/views/network_image_converter'
  require 'swiftui/json_to_swiftui_converter'
  require 'core/image_accessibility'
  require 'json'
  require 'tmpdir'
  require 'stringio'

  rule = JsonUIShared::ImageAccessibility
  vectors_path = File.expand_path('../../../../shared/core/image_accessibility_vectors.json', __dir__)

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(node)
    klass = node['type'] == 'NetworkImage' ? SjuiTools::SwiftUI::Views::NetworkImageConverter : SjuiTools::SwiftUI::Views::ImageConverter
    klass.new(node).convert
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
          swift = emit(node)
          case vector['roles'][node['id']]
          when 'decorative'
            expect(swift).to include('.accessibilityHidden(true)'), node['id']
            expect(swift).not_to include('.accessibilityLabel('), node['id']
          when 'control'
            expect(swift).not_to include('.accessibilityHidden('), node['id']
            expect(swift).not_to include('.accessibilityLabel('), node['id']
          when 'label'
            alt = rule.alt(node)
            if alt.start_with?('@{')
              name = alt[2..-2]
              expect(swift).to match(/\.accessibilityLabel\(Text\(\(.*data\.#{name}.*\)\)\)/), node['id']
              expect(swift).to match(/\.accessibilityHidden\(\(.*data\.#{name}.*\)\.isEmpty\)/), node['id']
            else
              expect(swift).to include(".accessibilityLabel(Text(\"#{alt}\""), node['id']
              expect(swift).not_to include('.accessibilityHidden('), node['id']
            end
          else raise "no role for #{node['id']}"
          end
        end
      end
    end
  end

  # The tappable around an image is only visible to the converter's entry,
  # which writes each image's role after expanding includes (the path
  # `jui build` takes). The same image, alone in a tappable and then beside
  # a Label in it.
  describe 'on the jui build path' do
    let(:dir) { Dir.mktmpdir('sjui_image_role') }
    after { FileUtils.rm_rf(dir) }

    def build(children)
      path = File.join(dir, 'probe.json')
      File.write(path, JSON.generate('type' => 'View', 'child' => [
        { 'type' => 'View', 'onClick' => '@{onMenu}', 'child' => children }
      ]))
      errors = StringIO.new
      $stderr = errors
      begin
        swift = SjuiTools::SwiftUI::JsonToSwiftUIConverter.new.convert_json_to_view(path).first
      ensure
        $stderr = STDERR
      end
      [swift, errors.string]
    end

    let(:icon) { { 'type' => 'Image', 'id' => 'menu_icon', 'src' => 'menu' } }

    it 'leaves the only image of a tappable readable, and names it' do
      swift, printed = build([icon])
      expect(swift).to include('Image("menu")')
      expect(swift).not_to include('.accessibilityHidden(true)')
      expect(printed).to include("[info] probe.json: Image 'menu_icon' operates a control and has no alt")
    end

    it 'hides the same image beside text, and says nothing' do
      swift, printed = build([icon, { 'type' => 'Label', 'text' => 'Menu' }])
      expect(swift).to include('.accessibilityHidden(true)')
      expect(printed).not_to include('[info]')
    end
  end
end
