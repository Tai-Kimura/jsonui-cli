# frozen_string_literal: true

require 'core/plural_validator'
require 'fileutils'
require 'tmpdir'
require 'json'

RSpec.describe JsonUIShared::PluralValidator do
  let(:valid_plural) do
    {
      'home' => {
        'items_count' => {
          'en' => { 'plural' => { 'one' => '{count} item', 'other' => '{count} items' } },
          'ja' => { 'plural' => { 'other' => '{count}件' } }
        },
        'title' => { 'en' => 'Home', 'ja' => 'ホーム' },
        'plain' => 'Just text'
      }
    }
  end

  describe '.plural_value?' do
    it 'detects plural entries and leaves flat/multi-language values alone' do
      expect(described_class.plural_value?(valid_plural['home']['items_count'])).to be true
      expect(described_class.plural_value?(valid_plural['home']['title'])).to be false
      expect(described_class.plural_value?('text')).to be false
    end
  end

  describe '.plural_forms' do
    it 'resolves with lang -> default -> first fallback' do
      value = valid_plural['home']['items_count']
      expect(described_class.plural_forms(value, 'ja')).to eq({ 'other' => '{count}件' })
      expect(described_class.plural_forms(value, 'fr')['other']).to eq('{count} items')
    end
  end

  describe '.substitute_count' do
    it 'uses the plain token for a single occurrence' do
      expect(described_class.substitute_count('{count} items', token: '%ld', positional_token: '%1$ld'))
        .to eq('%ld items')
    end

    it 'switches every occurrence to the positional token when repeated' do
      expect(described_class.substitute_count('{count} of {count}', token: '%d', positional_token: '%1$d'))
        .to eq('%1$d of %1$d')
    end
  end

  describe '.validate_strings' do
    it 'accepts a valid plural entry' do
      expect(described_class.validate_strings(valid_plural)).to be_empty
    end

    it 'rejects a category the language CLDR rules never select (en zero)' do
      data = { 'home' => { 'k' => { 'en' => { 'plural' => { 'zero' => 'none', 'other' => '{count}' } } } } }
      errors = described_class.validate_strings(data)
      expect(errors.join).to include("'zero'").and include('CLDR')
    end

    it "requires the 'other' category" do
      data = { 'home' => { 'k' => { 'en' => { 'plural' => { 'one' => '{count} item' } } } } }
      expect(described_class.validate_strings(data).join).to include("'other' category is required")
    end

    it 'rejects unknown categories' do
      data = { 'home' => { 'k' => { 'en' => { 'plural' => { 'other' => 'x', 'dual' => 'y' } } } } }
      expect(described_class.validate_strings(data).join).to include('unknown plural categories')
    end

    it "rejects a top-level 'plural' that is not wrapped in language codes" do
      data = { 'home' => { 'k' => { 'plural' => { 'other' => '{count}' } } } }
      expect(described_class.validate_strings(data).join).to include('nested under language codes')
    end

    it 'rejects mixing plural and plain values across languages' do
      data = { 'home' => { 'k' => {
        'en' => { 'plural' => { 'other' => '{count}' } },
        'ja' => '件'
      } } }
      expect(described_class.validate_strings(data).join).to include('mixing plural and plain values')
    end

    it 'rejects placeholders other than {count}' do
      data = { 'home' => { 'k' => { 'en' => { 'plural' => { 'other' => '{n} items' } } } } }
      expect(described_class.validate_strings(data).join).to include("unsupported placeholder '{n}'")
    end

    it 'rejects printf-style specifiers inside plural forms' do
      data = { 'home' => { 'k' => { 'en' => { 'plural' => { 'other' => '%d items' } } } } }
      expect(described_class.validate_strings(data).join).to include('printf-style specifiers')
    end

    it 'skips the CLDR category check for unknown languages but keeps structural checks' do
      data = { 'home' => { 'k' => { 'xx' => { 'plural' => { 'two' => 'x', 'other' => 'y' } } } } }
      expect(described_class.validate_strings(data)).to be_empty
    end
  end

  describe '.validate_layout_references' do
    around do |example|
      Dir.mktmpdir do |dir|
        @dir = dir
        example.run
      end
    end

    def write_layout(name, json)
      path = File.join(@dir, name)
      File.write(path, JSON.generate(json))
      path
    end

    it 'flags a text attribute referencing the full plural key' do
      layout = write_layout('home.json', { 'type' => 'Text', 'text' => 'home_items_count' })
      errors = described_class.validate_layout_references(valid_plural, [layout])
      expect(errors.join).to include("'home_items_count'").and include('VM-only')
    end

    it 'flags a bare plural key reference in nested children and items arrays' do
      layout = write_layout('home.json', {
        'type' => 'View',
        'child' => [{ 'type' => 'Text', 'text' => 'items_count' }],
        'children' => [{ 'type' => 'Segment', 'items' => ['items_count'] }]
      })
      errors = described_class.validate_layout_references(valid_plural, [layout])
      expect(errors.length).to eq(2)
    end

    it 'ignores bindings and non-plural keys' do
      layout = write_layout('home.json', {
        'type' => 'Text', 'text' => '@{itemsCountText}',
        'child' => [{ 'type' => 'Text', 'text' => 'home_title' }]
      })
      expect(described_class.validate_layout_references(valid_plural, [layout])).to be_empty
    end

    it 'returns nothing when strings.json has no plural keys' do
      layout = write_layout('home.json', { 'type' => 'Text', 'text' => 'anything' })
      data = { 'home' => { 'title' => 'Home' } }
      expect(described_class.validate_layout_references(data, [layout])).to be_empty
    end
  end

  describe 'copy consistency' do
    it 'stays byte-identical to the canonical shared/core copy' do
      tool_copy = File.expand_path('../../lib/core/plural_validator.rb', __dir__)
      shared_copy = File.expand_path('../../../shared/core/plural_validator.rb', __dir__)
      skip 'shared/core copy not present in this layout' unless File.exist?(shared_copy)
      expect(File.read(tool_copy)).to eq(File.read(shared_copy))
    end
  end
end
