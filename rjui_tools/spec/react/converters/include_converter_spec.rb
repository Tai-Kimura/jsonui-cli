# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/include_converter'

RSpec.describe RjuiTools::React::Converters::IncludeConverter do
  # Regression: rjui-include-data-partial-call-convention-missing —
  # partials receive one `data` prop (Partial<XxxData>), so include-site
  # shared_data/data maps must emit a single object literal with bindings
  # resolved to the PARENT's data (add_viewmodel_data_prefix).
  let(:default_config) { { 'use_tailwind' => true, 'typescript' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    it 'renders a bare include without props' do
      converter = create_converter({ 'include' => 'common/admin_topbar' })
      expect(converter.convert).to include('<AdminTopbar />')
    end

    it 'emits shared_data as a single data object literal with parent-data bindings' do
      converter = create_converter({
        'include' => 'common/admin_topbar',
        'shared_data' => { 'onMenuTap' => '@{onMenuTap}', 'title' => 'Dashboard' }
      })
      result = converter.convert
      expect(result).to include('<AdminTopbar data={{ onMenuTap: data.onMenuTap, title: "Dashboard" }} />')
    end

    it 'merges data over shared_data' do
      converter = create_converter({
        'include' => 'footer',
        'shared_data' => { 'label' => 'A' },
        'data' => { 'label' => '@{footerLabel}' }
      })
      expect(converter.convert).to include('<Footer data={{ label: data.footerLabel }} />')
    end

    it 'strips this. prefix in bindings' do
      converter = create_converter({
        'include' => 'nav',
        'data' => { 'onTap' => '@{this.onTap}' }
      })
      expect(converter.convert).to include('data={{ onTap: data.onTap }}')
    end

    it 'renders interpolated bindings as template literals' do
      converter = create_converter({
        'include' => 'banner',
        'data' => { 'message' => 'Hello @{userName}!' }
      })
      expect(converter.convert).to include('data={{ message: `Hello ${data.userName}!` }}')
    end
  end
end
