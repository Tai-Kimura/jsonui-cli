# frozen_string_literal: true

require 'core/string_manager_core'

# Namespace ownership and reference resolution, the shared half of the
# cell-strings fork: sjui names a strings.json section after the file's
# basename and kjui after the layouts-dir-relative path, so a layout in a
# subdirectory owns two spellings, and a value declared under both used
# to resolve by whichever came first in the file.
RSpec.describe JsonUIShared::StringManagerCore do
  describe '.namespace_candidates' do
    it 'returns both spellings a nested layout owns, caller convention first' do
      expect(described_class.namespace_candidates('item_detail/hero_section_cell.json'))
        .to eq(%w[hero_section_cell item_detail_hero_section_cell])

      expect(described_class.namespace_candidates('item_detail/hero_section_cell.json', preferred: :relative))
        .to eq(%w[item_detail_hero_section_cell hero_section_cell])
    end

    it 'collapses to one spelling for a layout at the root' do
      expect(described_class.namespace_candidates('login.json')).to eq(%w[login])
    end

    it 'folds a variant into the base screen' do
      expect(described_class.namespace_candidates('home@regular.json')).to eq(%w[home])
      expect(described_class.namespace_candidates('tabs/home@landscape.json'))
        .to eq(%w[home tabs_home])
    end

    it 'has no candidates for an empty path' do
      expect(described_class.namespace_candidates('')).to eq([])
    end

    # jsonui-localize writes sections in the builders' snake_case spelling
    # (component-name round-trip), so a kebab-case layout owns the
    # normalized spellings FIRST — matching only the raw path left a
    # kebab-case web consumer unable to own its own sections (840 false
    # foreign findings, 2026-08-11). Raw spellings stay as trailing
    # candidates for sections the sjui extractor named by the raw basename.
    it 'normalizes kebab-case segments to the builders\' snake spelling, keeping raw as fallback' do
      expect(described_class.namespace_candidates('tools/test-runner.json'))
        .to eq(%w[test_runner tools_test_runner test-runner tools_test-runner])
    end

    it 'normalizes camel-case segments the way the component round-trip does' do
      expect(described_class.namespace_candidates('TestRunner.json'))
        .to eq(%w[test_runner TestRunner])
    end

    it 'returns the same spellings as before for conventional snake_case names' do
      expect(described_class.namespace_candidates('item_detail/hero_section_cell.json'))
        .to eq(%w[hero_section_cell item_detail_hero_section_cell])
    end
  end

  describe '.resolve_string_reference' do
    let(:strings) do
      {
        'hero_section_cell' => { 'rating' => 'RATING' },
        'item_detail_hero_section_cell' => { 'rating' => 'RATING', 'imported_by' => 'Imported by ' }
      }
    end

    it 'prefers an owned section over the first one in the file' do
      resolved = described_class.resolve_string_reference(
        strings, 'RATING', %w[item_detail_hero_section_cell]
      )

      expect(resolved['namespace']).to eq('item_detail_hero_section_cell')
      expect(resolved['key']).to eq('rating')
      expect(resolved['foreign']).to be false
      expect(resolved['candidates']).to eq(%w[hero_section_cell item_detail_hero_section_cell])
    end

    it 'follows the caller order when the layout owns both spellings' do
      expect(
        described_class.resolve_string_reference(
          strings, 'RATING', %w[hero_section_cell item_detail_hero_section_cell]
        )['namespace']
      ).to eq('hero_section_cell')
    end

    it 'is independent of the order of sections in strings.json' do
      reordered = strings.to_a.reverse.to_h
      own = %w[item_detail_hero_section_cell]

      expect(described_class.resolve_string_reference(reordered, 'RATING', own))
        .to eq(described_class.resolve_string_reference(strings, 'RATING', own)
                 .merge('candidates' => %w[item_detail_hero_section_cell hero_section_cell]))
    end

    it 'marks a resolution outside the layout as foreign' do
      resolved = described_class.resolve_string_reference(
        strings, 'Imported by ', %w[hero_section_cell]
      )

      expect(resolved['namespace']).to eq('item_detail_hero_section_cell')
      expect(resolved['foreign']).to be true
    end

    it 'returns nil rather than minting a section for an undeclared string' do
      expect(described_class.resolve_string_reference(strings, 'Undeclared', %w[hero_section_cell]))
        .to be_nil
    end

    it 'falls back to file order when the layout has no context' do
      expect(described_class.resolve_string_reference(strings, 'RATING', [])['namespace'])
        .to eq('hero_section_cell')
    end

    it 'ignores non-Hash sections' do
      expect(described_class.resolve_string_reference({ 'junk' => 'RATING' }, 'RATING', [])).to be_nil
    end
  end

  describe '#merge_extracted_strings' do
    let(:merger) do
      Class.new(described_class) do
        public :merge_extracted_strings
      end.new
    end

    let(:logger) { double('logger', warn: nil) }

    it 'registers new strings under the extraction prefix' do
      existing = {}
      added = merger.merge_extracted_strings(existing, { 'login' => { 'title' => 'Sign in' } })

      expect(added).to eq(1)
      expect(existing).to eq({ 'login' => { 'title' => 'Sign in' } })
    end

    it 'never overwrites a hand-edited value' do
      existing = { 'login' => { 'title' => { 'en' => 'Sign in', 'ja' => 'ログイン' } } }
      added = merger.merge_extracted_strings(existing, { 'login' => { 'title' => 'Sign in' } })

      expect(added).to eq(0)
      expect(existing['login']['title']).to be_a(Hash)
    end

    # The fork machine: extracting a screen-scoped cell on the toolchain
    # that spells the section differently used to mint a SECOND section
    # holding the same strings.
    it 'does not mint a second section for a string the sibling spelling declares' do
      existing = { 'item_detail_hero_section_cell' => { 'imported_by' => 'Imported by ' } }
      aliases = { 'hero_section_cell' => %w[hero_section_cell item_detail_hero_section_cell] }

      added = merger.merge_extracted_strings(
        existing, { 'hero_section_cell' => { 'imported_by' => 'Imported by ' } }, aliases, logger
      )

      expect(added).to eq(0)
      expect(existing['hero_section_cell']).to eq({})
      expect(logger).to have_received(:warn).with(/already declared .* item_detail_hero_section_cell/)
    end

    it 'still registers a string the sibling spelling does not declare' do
      existing = { 'item_detail_hero_section_cell' => { 'imported_by' => 'Imported by ' } }
      aliases = { 'hero_section_cell' => %w[hero_section_cell item_detail_hero_section_cell] }

      added = merger.merge_extracted_strings(
        existing, { 'hero_section_cell' => { 'by' => 'by ' } }, aliases, logger
      )

      expect(added).to eq(1)
      expect(existing['hero_section_cell']).to eq({ 'by' => 'by ' })
    end

    it 'leaves an unrelated section alone' do
      existing = { 'common' => { 'ok' => 'OK' } }
      aliases = { 'login' => %w[login] }

      added = merger.merge_extracted_strings(
        existing, { 'login' => { 'ok' => 'OK' } }, aliases, logger
      )

      expect(added).to eq(1)
      expect(existing['login']).to eq({ 'ok' => 'OK' })
    end
  end
end
