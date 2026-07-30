# frozen_string_literal: true

require 'swiftui/views/checkbox_converter'

RSpec.describe SjuiTools::SwiftUI::Views::CheckboxConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  def generated(component)
    described_class.new(component, 0, nil).convert
  end

  describe 'iconColor' do
    it 'passes the tint through to CheckBoxView' do
      code = generated({ 'type' => 'CheckBox', 'iconColor' => '#FF0000' })
      expect(code).to include('iconColor:')
      expect(code).to include('#FF0000')
    end

    # Swift resolves argument labels positionally: they must appear in the
    # initializer's declaration order or the generated code will not compile.
    it 'emits iconColor after iconSize' do
      code = generated({ 'type' => 'CheckBox', 'iconSize' => 32, 'iconColor' => '#FF0000' })
      expect(code.index('iconSize:')).to be < code.index('iconColor:')
    end

    it 'emits nothing when absent' do
      expect(generated({ 'type' => 'CheckBox' })).not_to include('iconColor:')
    end
  end

  describe 'selectedIcon' do
    # `onSrc` is an alias of selectedIcon, rewritten by the L1 canonicalizer, so
    # the converter only ever sees the canonical spelling. The raw read stays as
    # the fallback for un-normalized layouts.
    it 'accepts the canonical spelling and the raw alias alike' do
      canonical = generated({ 'type' => 'CheckBox', 'selectedIcon' => 'on_img' })
      raw_alias = generated({ 'type' => 'CheckBox', 'onSrc' => 'on_img' })

      expect(canonical).to include('selectedIcon: "on_img"')
      expect(raw_alias).to include('selectedIcon: "on_img"')
    end
  end
end
