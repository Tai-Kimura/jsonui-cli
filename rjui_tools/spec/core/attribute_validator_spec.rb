#!/usr/bin/env ruby

require_relative '../../lib/core/attribute_validator'
require 'json'
require 'fileutils'

RSpec.describe RjuiTools::Core::AttributeValidator do
  let(:validator) { described_class.new(:all) }

  describe '#validate' do
    context 'with enum array values' do
      it 'accepts valid single enum value in array' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'gravity' => ['centerVertical']
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts valid multiple enum values in array' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'gravity' => ['centerVertical', 'left']
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'rejects invalid enum values in array' do
        component = {
          'type' => 'View',
          'gravity' => ['invalid']
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('invalid value')
        expect(warnings.first).to include('invalid')
      end

      it 'rejects mixed valid and invalid enum values in array' do
        component = {
          'type' => 'View',
          'gravity' => ['centerVertical', 'invalid']
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('invalid value')
        expect(warnings.first).to include('invalid')
      end
    end

    context 'with binding expressions' do
      it 'accepts binding expression for visibility' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'visibility' => '@{isVisible}'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts binding expression for enum attribute' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'gravity' => '@{gravityValue}'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts binding expression for width' do
        component = {
          'type' => 'View',
          'width' => '@{dynamicWidth}',
          'height' => 100
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts binding expression for height' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => '@{dynamicHeight}'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with Hash enum type definitions' do
      it 'accepts valid enum string value for width' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts valid enum string value for height' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts numeric value for width' do
        component = {
          'type' => 'View',
          'width' => 100,
          'height' => 100
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts numeric value for height' do
        component = {
          'type' => 'View',
          'width' => 100,
          'height' => 200
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'rejects invalid string value for width' do
        component = {
          'type' => 'View',
          'width' => 'invalid'
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to match(/expects.*got string/)
      end

      it 'rejects invalid string value for height' do
        component = {
          'type' => 'View',
          'height' => 'invalid'
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to match(/expects.*got string/)
      end
    end

    context 'with enum string values' do
      it 'accepts valid enum string value' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'visibility' => 'visible'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts valid textAlign value' do
        component = {
          'type' => 'Label',
          'width' => 'matchParent',
          'height' => 100,
          'text' => 'Test',
          'textAlign' => 'center'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with type validation' do
      it 'accepts valid number type' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'cornerRadius' => 10
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts valid string type' do
        component = {
          'type' => 'Label',
          'width' => 'matchParent',
          'height' => 100,
          'text' => 'Hello World'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts valid boolean type' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'hidden' => false
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts valid array type for padding' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'padding' => [10, 20, 10, 20]
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with min/max validation' do
      it 'accepts valid alpha value within range' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'alpha' => 0.5
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'rejects alpha value below minimum' do
        component = {
          'type' => 'View',
          'alpha' => -0.1
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('less than minimum')
      end

      it 'rejects alpha value above maximum' do
        component = {
          'type' => 'View',
          'alpha' => 1.5
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('greater than maximum')
      end
    end

    context 'with unknown attributes' do
      it 'warns about unknown attributes' do
        component = {
          'type' => 'View',
          'unknownAttribute' => 'value'
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('Unknown attribute')
        expect(warnings.first).to include('unknownAttribute')
      end

      it 'ignores attributes prefixed with underscore' do
        component = {
          'type' => 'View',
          '_generated' => {
            'sentinel' => '@generated',
            'doNotEdit' => true
          }
        }
        warnings = validator.validate(component)
        expect(warnings.any? { |w| w.include?('_generated') }).to be false
      end
    end

    context 'with required attributes' do
      it 'does not require type when already provided' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'does not require height when weight is set in vertical parent' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'vertical')
        expect(warnings).to be_empty
      end

      it 'does not require width when weight is set in horizontal parent' do
        component = {
          'type' => 'View',
          'height' => 100,
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'horizontal')
        expect(warnings).to be_empty
      end

      it 'still requires width when weight is set in vertical parent' do
        component = {
          'type' => 'View',
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'vertical')
        expect(warnings.any? { |w| w.include?("'width'") && w.include?('missing') }).to be true
        expect(warnings.none? { |w| w.include?("'height'") && w.include?('missing') }).to be true
      end

      it 'still requires height when weight is set in horizontal parent' do
        component = {
          'type' => 'View',
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'horizontal')
        expect(warnings.any? { |w| w.include?("'height'") && w.include?('missing') }).to be true
        expect(warnings.none? { |w| w.include?("'width'") && w.include?('missing') }).to be true
      end

      it 'stays silent about weight when parent orientation is nil (include root)' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 'wrapContent',
          'weight' => 1
        }
        warnings = validator.validate(component)
        # (c)-drift fixed in the W3-2 unification: nil means "orientation
        # unknown" (include-file root), so no warning — the sjui semantics.
        expect(warnings.none? { |w| w.include?("'weight'") && w.include?('ZStack') }).to be true
      end
    end

    context 'with nested object validation' do
      it 'accepts valid shadow object' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'shadow' => {
            'color' => '#000000',
            'offsetX' => 2,
            'offsetY' => 2,
            'opacity' => 0.5,
            'radius' => 4
          }
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts shadow as string' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'shadow' => '#000000|2|2|0.5|4'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with mode compatibility' do
      let(:react_validator) { described_class.new(:react) }

      it 'accepts react-specific attributes in react mode' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'className' => 'custom-class'
        }
        warnings = react_validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts react-specific testId in react mode' do
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'testId' => 'test-view'
        }
        warnings = react_validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with Label specific attributes' do
      it 'accepts valid font attributes' do
        component = {
          'type' => 'Label',
          'width' => 'matchParent',
          'height' => 100,
          'text' => 'Test',
          'font' => 'Arial',
          'fontSize' => 16,
          'fontColor' => '#000000'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts valid textTransform value' do
        component = {
          'type' => 'Label',
          'width' => 'matchParent',
          'height' => 100,
          'text' => 'Test',
          'textTransform' => 'uppercase'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'rejects invalid textTransform value' do
        component = {
          'type' => 'Label',
          'text' => 'Test',
          'textTransform' => 'invalid'
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('invalid value')
      end
    end

    context 'with Button attributes' do
      it 'accepts valid button attributes' do
        component = {
          'type' => 'Button',
          'width' => 'matchParent',
          'height' => 100,
          'text' => 'Click Me',
          'onClick' => '@{handleClick}'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with TextField attributes' do
      it 'accepts valid input type' do
        component = {
          'type' => 'TextField',
          'width' => 'matchParent',
          'height' => 100,
          'hint' => 'Enter email',
          'input' => 'email'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'rejects invalid input type' do
        component = {
          'type' => 'TextField',
          'hint' => 'Enter value',
          'input' => 'invalid'
        }
        warnings = validator.validate(component)
        expect(warnings).not_to be_empty
        expect(warnings.first).to include('invalid value')
      end
    end

    context 'with Collection attributes' do
      it 'accepts valid columns value' do
        component = {
          'type' => 'Collection',
          'width' => 'matchParent',
          'height' => 100,
          'columns' => 2
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'accepts valid layout value' do
        component = {
          'type' => 'Collection',
          'width' => 'matchParent',
          'height' => 100,
          'layout' => 'vertical'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end
  end

  describe '#has_warnings?' do
    it 'returns false when no warnings' do
      component = { 'type' => 'View', 'width' => 'matchParent', 'height' => 100 }
      validator.validate(component)
      expect(validator.has_warnings?).to be false
    end

    it 'returns true when there are warnings' do
      component = {
        'type' => 'View',
        'unknownAttr' => 'value'
      }
      validator.validate(component)
      expect(validator.has_warnings?).to be true
    end
  end

  describe '#print_warnings' do
    it 'prints warnings to stdout' do
      component = {
        'type' => 'View',
        'unknownAttr' => 'value'
      }
      validator.validate(component)

      expect {
        validator.print_warnings
      }.to output(/\[RJUI Warning\]/).to_stdout
    end
  end

  # NEW: Tests for invalid binding syntax
  describe 'Invalid binding syntax validation' do
    context 'with valid binding syntax' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'matchParent',
          'height' => 100,
          'text' => '@{userName}'
        }
      end

      it 'returns no warnings for valid binding' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with invalid binding syntax - missing closing brace' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => '@{userName'
        }
      end

      it 'returns warning for invalid binding syntax' do
        warnings = validator.validate(component)
        # Warnings carry a [file id=…]/[type] context prefix since the
        # W3-2 unification (shared core adopted the sjui context machinery).
        expect(warnings).to include(
          "[Label] Attribute 'text' in 'Label' has invalid binding syntax (starts with '@{' but doesn't end with '}')"
        )
      end
    end

    context 'with invalid binding syntax - extra characters after closing brace' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => '@{userName}extra'
        }
      end

      it 'returns warning for invalid binding syntax' do
        warnings = validator.validate(component)
        expect(warnings).to include(
          "[Label] Attribute 'text' in 'Label' has invalid binding syntax (starts with '@{' but doesn't end with '}')"
        )
      end
    end

    context 'with regular string value' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'matchParent',
          'height' => 100,
          'text' => 'Hello World'
        }
      end

      it 'returns no warnings for regular string' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with string containing @{ but not at start' do
      let(:component) do
        {
          'type' => 'Label',
          'width' => 'matchParent',
          'height' => 100,
          'text' => 'Email: @{email}'
        }
      end

      it 'returns no warnings for string with @{ in middle' do
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with binding attribute type and invalid syntax' do
      let(:component) do
        {
          'type' => 'TextField',
          'text' => '@{inputValue'
        }
      end

      it 'returns warning for invalid binding syntax' do
        warnings = validator.validate(component)
        expect(warnings).to include(
          "[TextField] Attribute 'text' in 'TextField' has invalid binding syntax (starts with '@{' but doesn't end with '}')"
        )
      end
    end

    context 'with nested object property having invalid binding syntax' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => 'Hello',
          'shadow' => {
            'color' => '@{shadowColor'
          }
        }
      end

      it 'returns warning for invalid binding syntax in nested property' do
        warnings = validator.validate(component)
        expect(warnings).to include(
          "[Label] Attribute 'shadow.color' in 'Label' has invalid binding syntax (starts with '@{' but doesn't end with '}')"
        )
      end
    end
  end

  # NEW: Tests for weight dimension conflict
  describe '#check_weight_dimension_conflict' do
    let(:validator) { described_class.new(:all) }

    context 'with horizontal parent orientation' do
      it 'warns when component has both weight and width' do
        component = {
          'type' => 'View',
          'width' => 100,
          'height' => 'wrapContent',
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'horizontal')
        expect(warnings.any? { |w| w.include?("'weight' and 'width'") && w.include?('horizontal') }).to be true
      end

      it 'does not warn when component has weight and height (cross direction)' do
        component = {
          'type' => 'View',
          'height' => 100,
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'horizontal')
        expect(warnings.none? { |w| w.include?("'weight' and 'height'") }).to be true
      end
    end

    context 'with vertical parent orientation' do
      it 'warns when component has both weight and height' do
        component = {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 100,
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'vertical')
        expect(warnings.any? { |w| w.include?("'weight' and 'height'") && w.include?('vertical') }).to be true
      end

      it 'does not warn when component has weight and width (cross direction)' do
        component = {
          'type' => 'View',
          'width' => 100,
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'vertical')
        expect(warnings.none? { |w| w.include?("'weight' and 'width'") }).to be true
      end
    end

    context 'with nil parent orientation (include-file root)' do
      # (c)-drift fixed in the W3-2 unification: nil means "orientation
      # unknown" (include-file root — the real parent may provide a valid
      # axis), so no warning. The sjui semantics won over the old
      # rjui/kjui ZStack guess, which false-positived on include roots.
      it 'stays silent — the real parent may provide the axis' do
        component = {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'weight' => 1
        }
        warnings = validator.validate(component, nil, nil)
        expect(warnings.none? { |w| w.include?("'weight'") }).to be true
      end
    end

    context 'with an explicit non-linear orientation (ZStack)' do
      it 'warns that weight is not applicable' do
        component = {
          'type' => 'View',
          'width' => 'wrapContent',
          'height' => 'wrapContent',
          'weight' => 1
        }
        warnings = validator.validate(component, nil, 'zstack')
        expect(warnings.any? { |w| w.include?("'weight'") && w.include?('ZStack') }).to be true
      end
    end

    context 'without weight' do
      it 'does not warn' do
        component = {
          'type' => 'View',
          'width' => 100,
          'height' => 100
        }
        warnings = validator.validate(component, nil, 'horizontal')
        expect(warnings.none? { |w| w.include?('weight') }).to be true
      end
    end
  end

  # NEW: Tests for style merging
  describe 'Style merging validation' do
    let(:styles_dir) { File.join(Dir.pwd, 'spec', 'fixtures', 'styles') }

    before(:all) do
      # Create test styles directory and files
      @styles_dir = File.join(Dir.pwd, 'spec', 'fixtures', 'styles')
      FileUtils.mkdir_p(@styles_dir)

      # Create a test style file
      File.write(File.join(@styles_dir, 'TestStyle.json'), JSON.pretty_generate({
        'width' => 'matchParent',
        'height' => 100,
        'cornerRadius' => 8,
        'background' => '#FFFFFF'
      }))

      # Create a style with nested properties
      File.write(File.join(@styles_dir, 'ShadowStyle.json'), JSON.pretty_generate({
        'width' => 'matchParent',
        'height' => 100,
        'shadow' => {
          'color' => '#000000',
          'offsetX' => 2,
          'offsetY' => 2,
          'radius' => 4
        }
      }))
    end

    after(:all) do
      FileUtils.rm_rf(File.join(Dir.pwd, 'spec', 'fixtures', 'styles'))
    end

    context 'with style reference' do
      subject(:validator) { described_class.new(:all, @styles_dir) }

      it 'merges style attributes into component' do
        component = {
          'type' => 'View',
          'style' => 'TestStyle'
        }
        warnings = validator.validate(component)
        # Should not warn about missing width/height because they come from style
        expect(warnings.none? { |w| w.include?("'width'") && w.include?('missing') }).to be true
        expect(warnings.none? { |w| w.include?("'height'") && w.include?('missing') }).to be true
      end

      it 'allows component attributes to override style attributes' do
        component = {
          'type' => 'View',
          'style' => 'TestStyle',
          'cornerRadius' => 16
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'validates merged style attributes' do
        component = {
          'type' => 'View',
          'style' => 'ShadowStyle'
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end

      it 'ignores non-existent style' do
        component = {
          'type' => 'View',
          'style' => 'NonExistentStyle'
        }
        warnings = validator.validate(component)
        # Should warn about missing required attributes since style doesn't exist
        expect(warnings.any? { |w| w.include?('missing') }).to be true
      end
    end

    context 'without styles_dir' do
      subject(:validator) { described_class.new }

      it 'works without style merging when no styles_dir configured' do
        component = {
          'type' => 'View',
          'style' => 'TestStyle',
          'width' => 'matchParent',
          'height' => 100
        }
        warnings = validator.validate(component)
        expect(warnings).to be_empty
      end
    end

    context 'with normalized (L1) layouts' do
      # `minimumValue` exists ONLY as an alias of Slider `minimum` in the
      # definitions (unlike e.g. `alpha`, which also has a standalone
      # entry), so it is the observable difference between the alias-
      # expanding L0 path and the canonical-only L1 path.
      let(:alias_component) do
        {
          'type' => 'Slider',
          'width' => 'matchParent',
          'height' => 20,
          'minimumValue' => 5
        }
      end

      it 'accepts alias-only spellings on the L0 path' do
        warnings = validator.validate(alias_component)
        expect(warnings.any? { |w| w.include?("Unknown attribute 'minimumValue'") }).to be false
      end

      it 'reports leftover alias-only spellings as unknown on the canonical-only path' do
        validator.normalized = true
        warnings = validator.validate(alias_component)
        expect(warnings.any? { |w| w.include?("Unknown attribute 'minimumValue'") }).to be true
      end

      it 'still accepts canonical spellings on the canonical-only path' do
        validator.normalized = true
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          'opacity' => 0.5
        }
        expect(validator.validate(component)).to be_empty
      end

      it 'still skips the $jui marker key itself' do
        validator.normalized = true
        component = {
          'type' => 'View',
          'width' => 'matchParent',
          'height' => 100,
          '$jui' => { 'normalized' => 'L1', 'schemaVersion' => 1 }
        }
        expect(validator.validate(component)).to be_empty
      end
    end
  end

  describe '#check_spacing_gravity_conflict (regression: jui-validator-spacing-gravity-conflict-fires-on-cross-axis-gravity)' do
    def spacing_gravity_warnings(component)
      v = described_class.new(:all)
      v.send(:check_spacing_gravity_conflict, component, component['type'])
      v.instance_variable_get(:@warnings)
    end

    it 'stays silent for spacing + cross-axis gravity (horizontal row idiom)' do
      component = { 'type' => 'View', 'orientation' => 'horizontal',
                    'spacing' => 12, 'gravity' => 'centerVertical' }
      expect(spacing_gravity_warnings(component)).to be_empty
    end

    it 'stays silent for spacing + main-axis gravity (gap composes with justify)' do
      component = { 'type' => 'View', 'orientation' => 'horizontal',
                    'spacing' => 12, 'gravity' => 'right' }
      expect(spacing_gravity_warnings(component)).to be_empty
    end

    it 'warns for distribution + main-axis gravity' do
      component = { 'type' => 'View', 'orientation' => 'horizontal',
                    'distribution' => 'equalSpacing', 'gravity' => 'right' }
      warnings = spacing_gravity_warnings(component)
      expect(warnings.size).to eq(1)
      expect(warnings.first).to include("'distribution' and main-axis gravity right")
    end

    it 'stays silent for distribution + cross-axis gravity' do
      component = { 'type' => 'View', 'orientation' => 'horizontal',
                    'distribution' => 'equalSpacing', 'gravity' => ['centerVertical'] }
      expect(spacing_gravity_warnings(component)).to be_empty
    end

    it 'detects the main-axis value inside pipe-joined gravity strings' do
      component = { 'type' => 'View', 'orientation' => 'vertical',
                    'distribution' => 'equalSpacing', 'gravity' => 'centerHorizontal|bottom' }
      expect(spacing_gravity_warnings(component).size).to eq(1)
    end

    it 'treats bare center as a main-axis conflict with distribution' do
      component = { 'type' => 'View', 'orientation' => 'horizontal',
                    'distribution' => 'equalSpacing', 'gravity' => 'center' }
      expect(spacing_gravity_warnings(component).size).to eq(1)
    end

    it 'stays silent without a linear orientation (no main axis)' do
      component = { 'type' => 'View',
                    'distribution' => 'equalSpacing', 'gravity' => 'center' }
      expect(spacing_gravity_warnings(component)).to be_empty
    end
  end

  describe 'Radio selectedValue/onValueChange declaration (regression: rjui-radio-selectedvalue-onvaluechange-undeclared)' do
    def unknown_warnings(component)
      v = described_class.new(:all)
      v.validate(component).select { |w| w.include?('Unknown attribute') }
    end

    it 'accepts the converter-wired selection binding attributes' do
      component = {
        'type' => 'Radio', 'group' => 'accountType', 'text' => 'Individual',
        'selectedValue' => '@{accountType}',
        'onValueChange' => '@{onAccountTypeChanged}'
      }
      expect(unknown_warnings(component)).to be_empty
    end
  end

  describe 'Embed params tree grammar (v1.5)' do
    def embed(attrs = {})
      { 'type' => 'Embed', 'id' => 'pane', 'screen' => 'foo' }.merge(attrs)
    end

    it 'accepts isolated navigationMode without enum warnings' do
      warnings = validator.validate(embed('navigationMode' => 'isolated'))
      expect(warnings.select { |w| w.include?('navigationMode') }).to be_empty, warnings.inspect
    end

    it 'accepts nested literal objects with scalar/binding leaves' do
      warnings = validator.validate(embed(
        'params' => { 'profile' => { 'name' => '@{userName}', 'age' => 36 } }
      ))
      expect(warnings.select { |w| w.include?('Embed.params') }).to be_empty, warnings.inspect
    end

    # W3-2 file 5: the params tree grammar (arrays, camelCase, defaults,
    # negation) is the binding validator's job on every platform — the
    # attribute validator no longer reports it.
    it 'leaves array violations in params to the binding validator' do
      warnings = validator.validate(embed(
        'params' => { 'profile' => { 'tags' => %w[a b] } }
      ))
      expect(warnings.none? { |w| w.match?(/params.*array/) }).to be true
    end

    it 'leaves camelCase key violations to the binding validator' do
      warnings = validator.validate(embed(
        'params' => { 'profile' => { 'UserName' => 'x' } }
      ))
      expect(warnings.none? { |w| w.include?('camelCase') }).to be true
    end
  end
end
