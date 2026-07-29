# frozen_string_literal: true

require 'compose/components/button_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

# Regression: rjui-button-image-attribute-dropped (Android half).
#
# `image` was declared for Button and DynamicButtonComponent rendered it, but
# the Compose codegen never read it — so the hot-reload preview showed the
# icon and the built app did not. Static/dynamic parity is the contract.
RSpec.describe KjuiTools::Compose::Components::ButtonComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  def generate(json)
    described_class.generate({ 'type' => 'Button' }.merge(json), 0, required_imports)
  end

  describe 'Button#image' do
    it 'renders the drawable instead of an empty button' do
      result = generate('image' => 'menu')
      expect(result).to include('painterResource(id = R.drawable.menu)')
      expect(required_imports).to include(:painter_resource, :r_class)
    end

    it 'drops the "Button" placeholder for an icon-only button' do
      # The placeholder is for a button with nothing in it; an icon-only
      # button would otherwise render the word "Button" beside its icon.
      expect(generate('image' => 'menu')).not_to include('Text("Button")')
    end

    it 'keeps the placeholder when there is neither text nor icon' do
      expect(generate({})).to include('Text("Button")')
    end

    it 'lays an icon and a label out in a Row with a gap' do
      result = generate('image' => 'menu', 'text' => 'Menu')
      expect(result).to include('Row(verticalAlignment = Alignment.CenterVertically)')
      expect(result).to include('Spacer(modifier = Modifier.width(8.dp))')
      expect(result).to include('Text("Menu")')
    end

    it 'emits no Row for an icon-only button' do
      expect(generate('image' => 'menu')).not_to include('Row(')
    end

    it 'draws an untinted icon as an Image so a multi-colour asset survives' do
      result = generate('image' => 'menu')
      expect(result).to include('Image(')
      expect(result).not_to include('tint =')
    end

    it 'draws a tinted icon as an Icon' do
      result = generate('image' => 'menu', 'fontColor' => '#FFFFFF')
      expect(result).to include('Icon(')
      expect(result).to match(/tint = .+#FFFFFF/)
    end

    it 'prefers tintColor over fontColor for the icon' do
      result = generate('image' => 'menu', 'fontColor' => '#FFFFFF', 'tintColor' => '#FF0000')
      expect(result).to match(/tint = .+#FF0000/)
    end

    it 'gives an icon-only button an accessible name' do
      # A button whose only child is a decorative image has no accessible
      # name at all.
      expect(generate('image' => 'menu_open')).to include('contentDescription = "menu open"')
    end

    it 'treats the icon as decorative when a label is present' do
      expect(generate('image' => 'menu', 'text' => 'Menu'))
        .to include('contentDescription = null')
    end

    it 'resolves a bound name at runtime and skips a missing drawable' do
      result = generate('image' => '@{icon_name}', 'text' => 'Menu')
      expect(result).to include('ctx.resources.getIdentifier(data.iconName, "drawable", ctx.packageName)')
      expect(result).to include('if (iconResId != 0) {')
      expect(required_imports).to include(:local_context)
      # The gap belongs inside the branch: an unresolved icon must not leave
      # a stray indent in front of the label.
      expect(result).to match(/if \(iconResId != 0\) \{.*Spacer/m)
    end

    it 'sanitises an asset name into a drawable reference' do
      expect(generate('image' => 'star.fill')).to include('R.drawable.star_fill')
    end

    it 'leaves a text-only button exactly as before' do
      result = generate('text' => 'Save')
      expect(result).not_to include('painterResource')
      expect(result).not_to include('Row(')
      expect(result).to include('Text("Save")')
    end

    it 'still routes font attributes through the FontSpec hook beside an icon' do
      result = generate('image' => 'menu', 'text' => 'Menu', 'fontSize' => 20)
      expect(result).to include('Configuration.Font.resolve')
      expect(result).to include('text = "Menu",')
    end
  end
end
