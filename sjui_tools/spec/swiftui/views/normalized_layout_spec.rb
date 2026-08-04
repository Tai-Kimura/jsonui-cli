# frozen_string_literal: true

require 'core/normalization'
require 'core/attribute_validator'
require 'swiftui/view_registry'
require 'swiftui/views/view_converter'
require 'swiftui/views/slider_converter'
require 'swiftui/views/tab_view_converter'
require 'swiftui/views/button_converter'
require 'swiftui/views/collection_converter'

# Stage A (renderer SSoT): converters take the canonical-only attribute
# lookup path when the layout carried the `$jui` L1 marker
# (BaseViewConverter.layout_normalized set by JsonToSwiftUIConverter),
# and keep the legacy alias-fallback path for raw (L0) layouts.
RSpec.describe 'L1-normalized layout consumption' do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
    SjuiTools::SwiftUI::Views::BaseViewConverter.layout_normalized = false
  end

  after(:each) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.layout_normalized = false
  end

  def normalized!
    SjuiTools::SwiftUI::Views::BaseViewConverter.layout_normalized = true
  end

  describe SjuiTools::Core::Normalization do
    it 'detects the L1 marker' do
      expect(described_class.canonicalized?(
        '$jui' => { 'normalized' => 'L1', 'schemaVersion' => 1 }
      )).to be true
    end

    it 'accepts L2 (includes L1 canonicalization)' do
      expect(described_class.canonicalized?('$jui' => { 'normalized' => 'L2' })).to be true
    end

    it 'rejects raw layouts and malformed markers' do
      expect(described_class.canonicalized?({})).to be false
      expect(described_class.canonicalized?('$jui' => 'L1')).to be false
      expect(described_class.canonicalized?(nil)).to be false
    end
  end

  describe SjuiTools::SwiftUI::Views::ViewConverter do
    it 'reads the alpha alias on L0 layouts' do
      code = described_class.new({ 'type' => 'View', 'alpha' => 0.5 }).convert
      expect(code).to include('.opacity(0.5)')
    end

    it 'prefers canonical opacity over the alias' do
      code = described_class.new({ 'type' => 'View', 'opacity' => 0.3, 'alpha' => 0.5 }).convert
      expect(code).to include('.opacity(0.3)')
      expect(code).not_to include('.opacity(0.5)')
    end

    it 'ignores the alias on L1 layouts (canonical-only path)' do
      normalized!
      code = described_class.new({ 'type' => 'View', 'alpha' => 0.5 }).convert
      expect(code).not_to include('.opacity(0.5)')
    end

    it 'reads canonical opacity on L1 layouts' do
      normalized!
      code = described_class.new({ 'type' => 'View', 'opacity' => 0.5 }).convert
      expect(code).to include('.opacity(0.5)')
    end
  end

  describe SjuiTools::SwiftUI::Views::SliderConverter do
    it 'reads canonical minimum/maximum' do
      code = described_class.new({ 'type' => 'Slider', 'minimum' => 5, 'maximum' => 50 }).convert
      expect(code).to include('in: 5...50')
    end

    it 'falls back to the minimumValue/maximumValue aliases on L0' do
      code = described_class.new(
        { 'type' => 'Slider', 'minimumValue' => 5, 'maximumValue' => 50 }
      ).convert
      expect(code).to include('in: 5...50')
    end

    it 'ignores the aliases on L1 (defaults apply)' do
      normalized!
      code = described_class.new(
        { 'type' => 'Slider', 'minimumValue' => 5, 'maximumValue' => 50 }
      ).convert
      expect(code).to include('in: 0...1')
    end
  end

  describe SjuiTools::SwiftUI::Views::TabViewConverter do
    def convert(json)
      described_class.new(json).convert
    end

    it 'falls back to the selectedTabIndex alias on L0' do
      code = convert({ 'type' => 'TabView', 'tabs' => [], 'selectedTabIndex' => '@{tab}' })
      expect(code).to include('TabView(selection: $data.tab)')
    end

    it 'ignores selectedTabIndex on L1 (canonical selectedIndex only)' do
      normalized!
      code = convert({ 'type' => 'TabView', 'tabs' => [], 'selectedTabIndex' => '@{tab}' })
      expect(code).not_to include('selection: $data.tab')
    end

    it 'reads the onTabChange alias on L0 and skips it on L1' do
      json = { 'type' => 'TabView', 'tabs' => [], 'onTabChange' => '@{tabChanged}' }
      expect(convert(json)).to include('data.tabChanged?(newValue)')
      normalized!
      expect(convert(json)).not_to include('data.tabChanged?(newValue)')
    end

    it 'reads canonical onValueChange on both L0 and L1' do
      json = { 'type' => 'TabView', 'tabs' => [], 'onValueChange' => '@{tabChanged}' }
      expect(convert(json)).to include('data.tabChanged?(newValue)')
      normalized!
      expect(convert(json)).to include('data.tabChanged?(newValue)')
    end
  end

  describe SjuiTools::SwiftUI::Views::ButtonConverter do
    it 'reads the hilightColor typo alias on L0 and skips it on L1' do
      json = { 'type' => 'Button', 'text' => 'Tap', 'hilightColor' => '#00FF00' }
      expect(described_class.new(json).convert).to include('highlightColor:')
      normalized!
      expect(described_class.new(json).convert).not_to include('highlightColor:')
    end
  end

  describe SjuiTools::Core::AttributeValidator do
    let(:validator) { described_class.new(:swiftui) }

    it 'accepts alias spellings on L0 input' do
      warnings = validator.validate(
        { 'type' => 'Slider', 'width' => 100, 'height' => 100, 'minimumValue' => 1 }, 'Slider'
      )
      expect(warnings.join).not_to include('minimumValue')
    end

    it 'rejects pure alias spellings on L1 input (canonical-only)' do
      validator.normalized = true
      warnings = validator.validate(
        { 'type' => 'Slider', 'width' => 100, 'height' => 100, 'minimumValue' => 1 }, 'Slider'
      )
      expect(warnings.join).to include("Unknown attribute 'minimumValue'")
    end

    # `alpha` used to be exempt from the rule above: it was declared BOTH as
    # an alias of `opacity` and as an attribute in its own right, and the
    # standalone declaration is what made it survive the canonical-only pass.
    # That double declaration also cancelled the alias redirect entirely
    # (alias_map skips a spelling that is also declared), so 49-E removed it
    # along with six others. `alpha` is now a pure alias and is rejected on
    # L1 exactly like `minimumValue`.
    it 'rejects alpha on L1 too, now that it is a pure alias of opacity' do
      validator.normalized = true
      warnings = validator.validate(
        { 'type' => 'View', 'width' => 100, 'height' => 100, 'alpha' => 0.5 }, 'View'
      )
      expect(warnings.join).to include("Unknown attribute 'alpha'")
    end

    it 'accepts canonical names and the $jui marker on L1 input' do
      validator.normalized = true
      warnings = validator.validate(
        { '$jui' => { 'normalized' => 'L1', 'schemaVersion' => 1 },
          'type' => 'View', 'width' => 100, 'height' => 100, 'opacity' => 0.5 }, 'View'
      )
      expect(warnings).to be_empty
    end
  end
end
