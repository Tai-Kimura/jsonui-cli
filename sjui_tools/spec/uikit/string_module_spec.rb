# frozen_string_literal: true

require 'uikit/string_module'

RSpec.describe String do
  describe '#camelize' do
    it 'camelizes snake_case string' do
      expect('my_view'.camelize).to eq('MyView')
    end

    it 'camelizes multiple underscores' do
      expect('my_test_view'.camelize).to eq('MyTestView')
    end

    it 'handles single word' do
      expect('view'.camelize).to eq('View')
    end

    it 'handles empty string' do
      expect(''.camelize).to eq('')
    end

    it 'handles string with leading underscore' do
      expect('_private'.camelize).to eq('Private')
    end

    it 'handles string with trailing underscore' do
      expect('view_'.camelize).to eq('View')
    end

    it 'handles string with consecutive underscores' do
      expect('my__view'.camelize).to eq('MyView')
    end

    it 'handles already capitalized parts' do
      expect('MY_VIEW'.camelize).to eq('MYVIEW')
    end
  end
end
