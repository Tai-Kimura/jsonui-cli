# frozen_string_literal: true

require 'compose/components/iconlabel_component'

RSpec.describe KjuiTools::Compose::Components::IconLabelComponent do
  let(:required_imports) { Set.new }

  def generate(extra = {})
    described_class.generate(
      { 'type' => 'IconLabel', 'text' => 'Home' }.merge(extra), 0, required_imports
    )
  end

  # IconLabel had no Compose component at all: the type fell through to
  # check_custom_component and emitted `// TODO: Implement component type`.
  describe 'layout' do
    it 'puts the icon before the text in a Row by default' do
      result = generate('icon_off' => 'home')
      expect(result).to start_with('Row(')
      expect(result.index('Image(')).to be < result.index('Text(')
      expect(result).to include('verticalAlignment = Alignment.CenterVertically')
    end

    it 'puts the text first for iconPosition Right' do
      result = generate('icon_off' => 'home', 'iconPosition' => 'Right')
      expect(result).to start_with('Row(')
      expect(result.index('Text(')).to be < result.index('Image(')
    end

    it 'uses a Column for Top and Bottom' do
      top = generate('icon_off' => 'home', 'iconPosition' => 'Top')
      bottom = generate('icon_off' => 'home', 'iconPosition' => 'Bottom')

      expect(top).to start_with('Column(')
      expect(top.index('Image(')).to be < top.index('Text(')
      expect(bottom).to start_with('Column(')
      expect(bottom.index('Text(')).to be < bottom.index('Image(')
      expect(top).to include('horizontalAlignment = Alignment.CenterHorizontally')
    end

    it 'renders text alone when no icon is supplied' do
      result = generate
      expect(result).not_to include('Image(')
      expect(result).to include('Text(')
    end
  end

  describe 'iconMargin' do
    it 'becomes the arrangement spacing on the layout axis' do
      expect(generate('icon_off' => 'home', 'iconMargin' => 12))
        .to include('horizontalArrangement = Arrangement.spacedBy(12.dp)')
      expect(generate('icon_off' => 'home', 'iconMargin' => 12, 'iconPosition' => 'Top'))
        .to include('verticalArrangement = Arrangement.spacedBy(12.dp)')
    end

    # IconLabelView.swift's own default, so the platforms agree when a layout
    # says nothing.
    it 'defaults to 5' do
      expect(generate('icon_off' => 'home')).to include('Arrangement.spacedBy(5.dp)')
    end

    # DynamicIconLabelComponent reads `spacing`; a layout must not change
    # meaning between dynamic and generated mode.
    it 'accepts the legacy spacing spelling' do
      expect(generate('icon_off' => 'home', 'spacing' => 9))
        .to include('Arrangement.spacedBy(9.dp)')
    end
  end

  describe 'icon_on / icon_off' do
    it 'swaps the drawable on the selected condition' do
      result = generate('icon_off' => 'home_off', 'icon_on' => 'home_on', 'selected' => '@{isHome}')
      expect(result).to include(
        'painter = if (data.isHome) painterResource(id = R.drawable.home_on) ' \
        'else painterResource(id = R.drawable.home_off)'
      )
    end

    it 'resolves a literal selected state at codegen time' do
      expect(generate('icon_off' => 'off', 'icon_on' => 'on', 'selected' => true))
        .to include('painter = painterResource(id = R.drawable.on)')
      expect(generate('icon_off' => 'off', 'icon_on' => 'on', 'selected' => false))
        .to include('painter = painterResource(id = R.drawable.off)')
    end

    # IconLabelView.iconView falls back to iconOn when only that was supplied.
    it 'falls back to icon_on when icon_off is absent' do
      expect(generate('icon_on' => 'only', 'selected' => '@{sel}'))
        .to include('painter = painterResource(id = R.drawable.only)')
    end

    it 'emits no conditional without a selected state to decide it' do
      result = generate('icon_off' => 'off', 'icon_on' => 'on')
      expect(result).to include('painter = painterResource(id = R.drawable.off)')
      expect(result).not_to include('if (')
    end

    it 'accepts the legacy icon / src spellings' do
      expect(generate('icon' => 'legacy')).to include('R.drawable.legacy')
      expect(generate('src' => 'legacy2')).to include('R.drawable.legacy2')
    end
  end

  describe 'selectedFontColor' do
    it 'switches the text colour on the selected condition' do
      result = generate('fontColor' => '#111111', 'selectedFontColor' => '#FF0000',
                        'selected' => '@{isHome}')
      expect(result).to match(/color = if \(data\.isHome\) Color\(.*FF0000.*\) else Color\(.*111111.*\)/)
    end

    it 'falls back to Color.Unspecified when there is no base colour' do
      result = generate('selectedFontColor' => '#FF0000', 'selected' => '@{isHome}')
      expect(result).to include('else Color.Unspecified')
    end

    it 'collapses a literal selected state' do
      result = generate('fontColor' => '#111111', 'selectedFontColor' => '#FF0000', 'selected' => true)
      expect(result).not_to include('if (')
      expect(result).to match(/color = Color\(.*FF0000/)
    end

    # Recolouring on selection is the point of the attribute, so it reaches the
    # icon too.
    it 'tints the icon while selected' do
      result = generate('icon_off' => 'home', 'selectedFontColor' => '#FF0000', 'selected' => '@{isHome}')
      expect(result).to match(/colorFilter = if \(data\.isHome\) ColorFilter\.tint\(.*FF0000.*\) else null/)
      expect(required_imports).to include(:color_filter)
    end
  end

  describe 'icon tint' do
    # iOS tints the icon with the font colour unconditionally, which would
    # flatten a multi-colour asset; the dynamic runtime tints only when asked.
    it 'does not tint without an explicit colour' do
      expect(generate('icon_off' => 'home', 'fontColor' => '#111111')).not_to include('colorFilter')
    end

    it 'tints on tintColor / iconColor' do
      expect(generate('icon_off' => 'home', 'tintColor' => '#00FF00')).to include('ColorFilter.tint(')
      expect(generate('icon_off' => 'home', 'iconColor' => '#00FF00')).to include('ColorFilter.tint(')
    end

    it 'lets selectedFontColor take over the selected state' do
      result = generate('icon_off' => 'home', 'tintColor' => '#00FF00',
                        'selectedFontColor' => '#FF0000', 'selected' => '@{sel}')
      expect(result).to match(/if \(data\.sel\) ColorFilter\.tint\(.*FF0000.*\) else ColorFilter\.tint\(.*00FF00/)
    end
  end

  describe 'text style' do
    it 'passes fontSize through' do
      expect(generate('fontSize' => 12)).to include('fontSize = 12.sp')
    end

    # IconLabelConverter treats `font: "bold"` as a weight, not a family.
    it 'reads a weight from font and from the legacy fontWeight' do
      expect(generate('font' => 'bold')).to include('fontWeight = FontWeight.Bold')
      expect(generate('fontWeight' => 'medium')).to include('fontWeight = FontWeight.Medium')
      expect(required_imports).to include(:font_weight)
    end

    it 'omits the weight for a font name that is not one' do
      expect(generate('font' => 'Helvetica')).not_to include('fontWeight')
    end

    # A shadow does not change the size. A bare TextStyle(shadow = …) dropped
    # the Material default (16sp on a 24sp line): the shadowed IconLabel drew
    # at 14sp on a 16.5 dp line while the dynamic face kept 16 / 24.
    it 'adds a textShadow to the current text style, not to a bare TextStyle' do
      out = generate('textShadow' => { 'color' => '#000000', 'blur' => 2, 'offset' => [1, 1] })
      expect(out).to include('style = LocalTextStyle.current.copy(shadow = ')
      expect(out).not_to include('TextStyle(shadow')
      expect(required_imports).to include(:local_text_style)
    end

    # The text's line is a Label's (user ruling 2026-10-05): a declared
    # fontSize gives fontSize x 1.3, the line a Label at that size has. It kept
    # the theme's 24 under a 20sp font, where a Label is 26.
    it "gives a declared fontSize a Label's line" do
      out = generate('fontSize' => 20)
      expect(out).to include('style = LocalTextStyle.current.copy(lineHeight = 26.0.sp)')
      expect(required_imports).to include(:local_text_style)
    end

    it 'puts the line and a textShadow in one style' do
      out = generate('fontSize' => 20, 'textShadow' => { 'color' => '#000000', 'blur' => 2, 'offset' => [1, 1] })
      expect(out).to include('style = LocalTextStyle.current.copy(lineHeight = 26.0.sp, shadow = ')
      expect(out.scan('style = ').size).to eq(1)
    end

    it 'scales a bound fontSize at run time' do
      expect(generate('fontSize' => '@{size}')).to match(/lineHeight = \(.*size.* \* 1\.3f?\)\.sp/)
    end

    it "keeps the theme's line without a fontSize (control)" do
      expect(generate).not_to include('lineHeight')
      expect(generate).not_to include('style = ')
    end
  end

  describe 'common attributes' do
    it 'applies the test tag and the size to the container' do
      result = generate('id' => 'tab_home', 'width' => 80, 'height' => 60)
      expect(result).to include('.testTag("tab_home")')
      expect(result).to include('modifier = Modifier')
    end

    it 'emits valid Kotlin when no modifier applies' do
      result = generate('icon_off' => 'home')
      expect(result).not_to include('modifier = Modifier,')
      expect(result).to include("Row(\n    horizontalArrangement")
    end
  end

  # `iconSize` is declared ["number", "array"]: a number sizes both edges, a
  # two-element [width, height] sizes them separately. Only the number face was
  # handled, so the declared array reached the source as a Ruby literal —
  # `Modifier.size([40, 20].dp)` is not Kotlin.
  describe 'iconSize' do
    it 'sizes both edges from a number' do
      expect(generate('icon_off' => 'home', 'iconSize' => 40))
        .to include('Modifier.size(40.dp)')
    end

    it 'sizes the edges separately from a [width, height] pair' do
      expect(generate('icon_off' => 'home', 'iconSize' => [40, 20]))
        .to include('Modifier.size(width = 40.dp, height = 20.dp)')
    end

    it 'never emits a Ruby array literal into the source' do
      expect(generate('icon_off' => 'home', 'iconSize' => [40, 20])).not_to include('[40, 20]')
    end

    # attribute_semantics iconLabelIconSize (2026-10-05 ruling): undeclared,
    # the icon is drawn at the image's own size — no size modifier at all.
    it "draws the icon at the image's own size when undeclared" do
      out = generate('icon_off' => 'home')
      expect(out).to include('Image(')
      expect(out).not_to include('Modifier.size(')
    end

    it 'keeps the Image arguments comma-separated without a size (a tint follows the description)' do
      out = generate('icon_off' => 'home', 'tintColor' => '#FF0000')
      expect(out).to match(/contentDescription = null,\n\s*colorFilter = /)
      expect(out).not_to include(',,')
    end
  end
end
