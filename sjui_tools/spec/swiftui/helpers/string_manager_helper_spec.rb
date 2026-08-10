# frozen_string_literal: true

require 'swiftui/helpers/string_manager_helper'

RSpec.describe SjuiTools::SwiftUI::Helpers::StringManagerHelper do
  # Create a test class that includes the helper
  let(:helper_instance) do
    Class.new do
      include SjuiTools::SwiftUI::Helpers::StringManagerHelper
    end.new
  end

  describe '#get_text_with_string_manager' do
    context 'with snake_case text' do
      it 'returns localized string for simple snake_case' do
        result = helper_instance.get_text_with_string_manager('"hello_world"')
        expect(result).to eq('"hello_world".localized()')
      end

      it 'returns localized string for snake_case with numbers' do
        result = helper_instance.get_text_with_string_manager('"item_count_3"')
        expect(result).to eq('"item_count_3".localized()')
      end

      it 'returns localized string for single word' do
        result = helper_instance.get_text_with_string_manager('"settings"')
        expect(result).to eq('"settings".localized()')
      end
    end

    context 'with regular text (not snake_case)' do
      it 'returns original text for CamelCase' do
        result = helper_instance.get_text_with_string_manager('"HelloWorld"')
        expect(result).to eq('"HelloWorld"')
      end

      it 'returns original text with spaces' do
        result = helper_instance.get_text_with_string_manager('"Hello World"')
        expect(result).to eq('"Hello World"')
      end

      it 'returns original text with uppercase' do
        result = helper_instance.get_text_with_string_manager('"HELLO"')
        expect(result).to eq('"HELLO"')
      end

      it 'returns original text starting with uppercase' do
        result = helper_instance.get_text_with_string_manager('"Hello_world"')
        expect(result).to eq('"Hello_world"')
      end
    end

    context 'with binding expression' do
      it 'returns original binding' do
        result = helper_instance.get_text_with_string_manager('"@{userName}"')
        expect(result).to eq('"@{userName}"')
      end

      it 'handles binding without quotes' do
        result = helper_instance.get_text_with_string_manager('@{userName}')
        expect(result).to eq('@{userName}')
      end
    end

    context 'with single quotes' do
      it 'processes single-quoted snake_case' do
        result = helper_instance.get_text_with_string_manager("'hello_world'")
        expect(result).to eq('"hello_world".localized()')
      end
    end

    # A cell under a screen directory owns two section spellings (sjui
    # names sections by basename, kjui by relative path), so the same
    # text can be declared twice. Scanning strings.json in file order made
    # the winner depend on how the SSoT happened to be sorted.
    context 'when more than one strings.json section declares the text' do
      let(:strings) do
        {
          'hero_section_cell' => { 'rating' => 'RATING' },
          'item_detail_hero_section_cell' => { 'rating' => 'RATING', 'imported_by' => 'Imported by ' }
        }
      end

      before do
        allow(helper_instance).to receive(:load_strings_json).and_return(strings)
        described_class.current_namespaces = []
      end

      after { described_class.current_namespaces = [] }

      it 'prefers the section the layout owns, not the first one in the file' do
        described_class.current_namespaces = %w[hero_section_cell item_detail_hero_section_cell]
        expect(helper_instance.get_text_with_string_manager('"RATING"'))
          .to eq('StringManager.HeroSectionCell.rating()')

        described_class.current_namespaces = %w[item_detail_hero_section_cell]
        expect(helper_instance.get_text_with_string_manager('"RATING"'))
          .to eq('StringManager.ItemDetailHeroSectionCell.rating()')
      end

      it 'is not swayed by the order of sections in strings.json' do
        described_class.current_namespaces = %w[item_detail_hero_section_cell]
        reordered = { 'hero_section_cell' => strings['hero_section_cell'] }
        allow(helper_instance).to receive(:load_strings_json)
          .and_return(strings.to_a.reverse.to_h, reordered.merge(strings))

        first = helper_instance.get_text_with_string_manager('"RATING"')
        second = helper_instance.get_text_with_string_manager('"RATING"')
        expect(first).to eq(second)
      end

      it 'falls back to a section the layout does not own rather than inventing one' do
        described_class.current_namespaces = %w[hero_section_cell]
        expect(helper_instance.get_text_with_string_manager('"Imported by "'))
          .to eq('StringManager.ItemDetailHeroSectionCell.importedBy()')
      end

      it 'keeps file order when the layout owns no declared section' do
        expect(helper_instance.get_text_with_string_manager('"RATING"'))
          .to eq('StringManager.HeroSectionCell.rating()')
      end

      it 'leaves a text no section declares alone instead of minting a key' do
        expect(helper_instance.get_text_with_string_manager('"Undeclared text"'))
          .to eq('"Undeclared text"')
      end

      it 'prefers an owned section for a bare key lookup too' do
        described_class.current_namespaces = %w[item_detail_hero_section_cell]
        expect(helper_instance.get_text_with_string_manager('"rating"'))
          .to eq('StringManager.ItemDetailHeroSectionCell.rating()')
      end
    end

    # The extractor truncates long ASCII text to 31 chars, which can leave a
    # trailing underscore ("dont_have_an_account_apply_for_"). Such a key is
    # as declared as any other; the old snake_case gate rejected the spelling
    # and the emit fell through to the raw literal — or worse, to a legacy
    # poison entry whose VALUE is the raw key (downstream login screen, 2026-08-09).
    context 'with a declared key the snake_case gate used to reject' do
      let(:strings) do
        {
          'login' => {
            'dont_have_an_account_apply_for_' => {
              'en' => "Don't have an account? Apply for Membership",
              'ja' => 'アカウントをお持ちでない方は会員登録'
            },
            # Legacy poison: a key whose value IS the other key's spelling.
            'dont_have_an_account_apply_for' => 'dont_have_an_account_apply_for_'
          }
        }
      end

      before do
        allow(helper_instance).to receive(:load_strings_json).and_return(strings)
        described_class.current_namespaces = %w[login]
      end

      after { described_class.current_namespaces = [] }

      it 'resolves a declared trailing-underscore key as the key itself' do
        expect(helper_instance.get_text_with_string_manager('"dont_have_an_account_apply_for_"'))
          .to eq('StringManager.Login.dontHaveAnAccountApplyFor()')
      end

      it 'prefers key membership over a value reverse-lookup hit' do
        # Without key-first ordering the poison entry's value match wins and
        # the emit resolves the poison key instead of the declared key.
        allow(helper_instance).to receive(:lookup_string_manager_by_value)
          .and_return('StringManager.Login.poison()')
        expect(helper_instance.get_text_with_string_manager('"dont_have_an_account_apply_for_"'))
          .to eq('StringManager.Login.dontHaveAnAccountApplyFor()')
      end

      it 'falls back to .localized() for an UNDECLARED trailing-underscore key' do
        expect(helper_instance.get_text_with_string_manager('"undeclared_key_"'))
          .to eq('"undeclared_key_".localized()')
      end
    end

    context 'edge cases' do
      it 'handles empty string' do
        result = helper_instance.get_text_with_string_manager('""')
        expect(result).to eq('""')
      end

      it 'handles string with only underscores' do
        result = helper_instance.get_text_with_string_manager('"___"')
        expect(result).to eq('"___"')
      end

      it 'handles numbers only' do
        result = helper_instance.get_text_with_string_manager('"123"')
        expect(result).to eq('"123"')
      end
    end
  end
end
