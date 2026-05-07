# frozen_string_literal: true

require 'core/template_engine'

RSpec.describe SjuiTools::Core::TemplateEngine do
  describe '.render' do
    it 'renders ERB template with variables' do
      template = 'Hello <%= name %>!'
      result = described_class.render(template, name: 'World')

      expect(result).to eq('Hello World!')
    end

    it 'renders template with multiple variables' do
      template = '<%= greeting %>, <%= name %>!'
      result = described_class.render(template, greeting: 'Hi', name: 'User')

      expect(result).to eq('Hi, User!')
    end

    it 'handles empty variables' do
      template = 'Static content'
      result = described_class.render(template, {})

      expect(result).to eq('Static content')
    end
  end

  describe '.capitalize_first' do
    it 'capitalizes first letter' do
      expect(described_class.capitalize_first('hello')).to eq('Hello')
    end

    it 'keeps rest of string unchanged' do
      expect(described_class.capitalize_first('helloWorld')).to eq('HelloWorld')
    end

    it 'returns empty string for nil' do
      expect(described_class.capitalize_first(nil)).to eq('')
    end

    it 'returns empty string for empty string' do
      expect(described_class.capitalize_first('')).to eq('')
    end
  end

  describe '.snake_to_camel' do
    it 'converts snake_case to PascalCase' do
      expect(described_class.snake_to_camel('user_name')).to eq('UserName')
    end

    it 'handles multiple underscores' do
      expect(described_class.snake_to_camel('first_name_last_name')).to eq('FirstNameLastName')
    end

    it 'handles single word' do
      expect(described_class.snake_to_camel('name')).to eq('Name')
    end
  end

  describe '.camel_to_snake' do
    it 'converts PascalCase to snake_case' do
      expect(described_class.camel_to_snake('UserName')).to eq('user_name')
    end

    it 'handles consecutive capitals' do
      expect(described_class.camel_to_snake('HTMLParser')).to eq('html_parser')
    end

    it 'handles mixed case' do
      expect(described_class.camel_to_snake('getHTTPResponseCode')).to eq('get_http_response_code')
    end
  end

  describe '.indent' do
    it 'indents content' do
      content = "line1\nline2"
      result = described_class.indent(content, 1)

      expect(result).to include('    line1')
      expect(result).to include('    line2')
    end

    it 'preserves empty lines' do
      content = "line1\n\nline2"
      result = described_class.indent(content, 1)

      lines = result.lines
      expect(lines[1]).to eq("\n")
    end

    it 'handles multiple indent levels' do
      result = described_class.indent('code', 2)

      expect(result).to include('        code')
    end

    it 'returns empty string for nil' do
      expect(described_class.indent(nil)).to eq('')
    end

    it 'returns empty string for empty content' do
      expect(described_class.indent('')).to eq('')
    end
  end

  describe '.format_array' do
    it 'returns [] for nil' do
      expect(described_class.format_array(nil)).to eq('[]')
    end

    it 'returns [] for empty array' do
      expect(described_class.format_array([])).to eq('[]')
    end

    it 'formats single item inline' do
      result = described_class.format_array(['item'])

      expect(result).to eq('[item]')
    end

    it 'formats multiple items with newlines' do
      result = described_class.format_array(%w[item1 item2])

      expect(result).to include("[\n")
      expect(result).to include('item1')
      expect(result).to include('item2')
    end
  end

  describe '.format_hash' do
    it 'returns {} for nil' do
      expect(described_class.format_hash(nil)).to eq('{}')
    end

    it 'returns {} for empty hash' do
      expect(described_class.format_hash({})).to eq('{}')
    end

    it 'formats single pair inline for short values' do
      result = described_class.format_hash({ key: 'value' })

      expect(result).to include('key:')
      expect(result).to include('"value"')
    end

    it 'formats string values with quotes' do
      result = described_class.format_hash({ name: 'test' })

      expect(result).to include('"test"')
    end

    it 'formats symbol values with colon' do
      result = described_class.format_hash({ type: :button })

      expect(result).to include(':button')
    end

    it 'formats nested hashes' do
      result = described_class.format_hash({ outer: { inner: 'value' } })

      expect(result).to include('inner:')
    end

    it 'formats arrays' do
      result = described_class.format_hash({ items: %w[a b] })

      expect(result).to include('"a"')
      expect(result).to include('"b"')
    end
  end
end
