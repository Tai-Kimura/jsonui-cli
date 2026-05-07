# frozen_string_literal: true

require 'swiftui/views/template_helper'

RSpec.describe SjuiTools::SwiftUI::Views::TemplateHelper do
  let(:helper_instance) do
    Class.new do
      include SjuiTools::SwiftUI::Views::TemplateHelper
    end.new
  end

  describe '#process_template_value' do
    context 'with numeric value' do
      it 'returns the value unchanged' do
        expect(helper_instance.process_template_value(42)).to eq(42)
        expect(helper_instance.process_template_value(3.14)).to eq(3.14)
      end
    end

    context 'with plain string' do
      it 'returns the string unchanged' do
        expect(helper_instance.process_template_value('Hello')).to eq('Hello')
      end
    end

    context 'with template variable' do
      it 'returns hash with template_var' do
        result = helper_instance.process_template_value('@{userName}')
        expect(result).to eq({ template_var: 'userName' })
      end
    end

    context 'with complex template expression' do
      it 'returns hash with template_var for single template' do
        result = helper_instance.process_template_value("@{icon_type == 'emoji' ? 30 : 12}")
        expect(result).to eq({ template_var: "icon_type == 'emoji' ? 30 : 12" })
      end

      it 'returns hash with template_expression for mixed content' do
        result = helper_instance.process_template_value("Hello @{name}!")
        expect(result).to eq({ template_expression: "Hello @{name}!" })
      end
    end

    context 'with non-string value' do
      it 'returns the value unchanged' do
        expect(helper_instance.process_template_value(nil)).to be_nil
        expect(helper_instance.process_template_value([1, 2, 3])).to eq([1, 2, 3])
      end
    end
  end

  describe '#to_camel_case' do
    it 'converts snake_case to camelCase' do
      expect(helper_instance.to_camel_case('user_name')).to eq('userName')
      expect(helper_instance.to_camel_case('first_name_last_name')).to eq('firstNameLastName')
    end

    it 'handles single word' do
      expect(helper_instance.to_camel_case('name')).to eq('name')
    end
  end

  describe '#infer_type_from_usage' do
    context 'with color attributes' do
      it 'returns Color type' do
        var_info = { used_as: ['background'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('Color')
      end

      it 'recognizes fontColor' do
        var_info = { used_as: ['fontColor'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('Color')
      end

      it 'recognizes borderColor' do
        var_info = { used_as: ['borderColor'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('Color')
      end
    end

    context 'with numeric attributes' do
      it 'returns CGFloat for width' do
        var_info = { used_as: ['width'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('CGFloat')
      end

      it 'returns CGFloat for height' do
        var_info = { used_as: ['height'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('CGFloat')
      end

      it 'returns CGFloat for cornerRadius' do
        var_info = { used_as: ['cornerRadius'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('CGFloat')
      end

      it 'returns CGFloat for fontSize' do
        var_info = { used_as: ['fontSize'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('CGFloat')
      end
    end

    context 'with boolean attributes' do
      it 'returns Bool for hidden' do
        var_info = { used_as: ['hidden'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('Bool')
      end

      it 'returns Bool for enabled' do
        var_info = { used_as: ['enabled'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('Bool')
      end
    end

    context 'with string attributes' do
      it 'returns String for text' do
        var_info = { used_as: ['text'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('String')
      end

      it 'returns String for hint' do
        var_info = { used_as: ['hint'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('String')
      end
    end

    context 'with array attributes for Collection' do
      it 'returns array type for items in Collection' do
        var_info = { used_as: ['items'], component_types: ['Collection'] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('[NotificationItem]')
      end
    end

    context 'with array attributes for SelectBox' do
      it 'returns [String] for items in SelectBox' do
        var_info = { used_as: ['items'], component_types: ['SelectBox'] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('[String]')
      end
    end

    context 'with unknown attributes' do
      it 'returns String as default' do
        var_info = { used_as: ['unknownAttr'], component_types: [] }
        expect(helper_instance.infer_type_from_usage(var_info)).to eq('String')
      end
    end
  end

  describe '#collect_template_vars' do
    context 'with simple template variable' do
      let(:component) do
        {
          'type' => 'Label',
          'text' => '@{userName}'
        }
      end

      it 'collects the variable' do
        vars = helper_instance.collect_template_vars(component)
        expect(vars).to have_key('userName')
        expect(vars['userName'][:used_as]).to include('text')
      end
    end

    context 'with nested component' do
      let(:component) do
        {
          'type' => 'View',
          'child' => [
            {
              'type' => 'Label',
              'text' => '@{title}'
            }
          ]
        }
      end

      it 'collects variables from children' do
        vars = helper_instance.collect_template_vars(component)
        expect(vars).to have_key('title')
      end
    end

    context 'with multiple variables' do
      let(:component) do
        {
          'type' => 'View',
          'background' => '@{bgColor}',
          'child' => [
            {
              'type' => 'Label',
              'text' => '@{message}',
              'fontSize' => '@{textSize}'
            }
          ]
        }
      end

      it 'collects all variables' do
        vars = helper_instance.collect_template_vars(component)
        expect(vars.keys).to contain_exactly('bgColor', 'message', 'textSize')
      end
    end

    context 'with binding object' do
      let(:component) do
        {
          'type' => 'Collection',
          'binding' => {
            'data' => '@{itemsList}'
          }
        }
      end

      it 'collects binding data variable' do
        vars = helper_instance.collect_template_vars(component)
        expect(vars).to have_key('itemsList')
        expect(vars['itemsList'][:used_as]).to include('data')
      end
    end

    context 'with non-hash component' do
      it 'returns empty hash for array' do
        vars = helper_instance.collect_template_vars([1, 2, 3])
        expect(vars).to eq({})
      end

      it 'returns empty hash for nil' do
        vars = helper_instance.collect_template_vars(nil)
        expect(vars).to eq({})
      end
    end
  end

  describe '#generate_property_definition' do
    it 'generates property definitions' do
      vars = {
        'user_name' => { used_as: ['text'], component_types: [] },
        'bg_color' => { used_as: ['background'], component_types: [] }
      }

      props = helper_instance.generate_property_definition(vars)
      expect(props).to include('let userName: String')
      expect(props).to include('let bgColor: Color')
    end
  end
end
