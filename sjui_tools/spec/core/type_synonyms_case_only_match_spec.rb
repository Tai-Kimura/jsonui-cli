# frozen_string_literal: true

require 'core/type_synonyms'

# Type names are their SSoT spellings, case-sensitive (4f's ruling, 1.9.0).
# JsonUIShared::TypeSynonyms.case_only_match is where what names an unknown
# type finds the spelling it offers ("did you mean"): the one that matches
# only when case is ignored — among the types the caller draws, the table's
# synonyms, the declared alias sections and the app's types. A spelling that
# is one of them as written is offered nothing, nor is one no case matches.
RSpec.describe 'JsonUIShared::TypeSynonyms.case_only_match' do
  synonyms = JsonUIShared::TypeSynonyms
  after { synonyms.app_types = [] }

  it 'offers the declared spelling of a type the caller draws, whatever letters differ in case' do
    known = %w[Label Switch SelectBox]
    expect(synonyms.case_only_match('switch', known)).to eq('Switch')
    expect(synonyms.case_only_match('SELECTBOX', known)).to eq('SelectBox')
  end

  it "offers the table's synonyms, the declared alias sections and the app's types too" do
    alias_section = JsonUIShared::ComponentAliases.table.keys.first
    expect(alias_section).to be_a(String) # (control: the definitions declare one)
    expect(synonyms.case_only_match('hstack')).to eq('HStack')
    expect(synonyms.case_only_match(alias_section.swapcase)).to eq(alias_section)
    synonyms.app_types = ['HeaderMenu']
    expect(synonyms.case_only_match('headerMenu')).to eq('HeaderMenu')
  end

  it 'offers nothing for a spelling that is one of them as written, or that no case matches' do
    expect(synonyms.case_only_match('Switch', %w[Switch])).to be_nil
    expect(synonyms.case_only_match('HStack')).to be_nil
    expect(synonyms.case_only_match('Nope', %w[Label Switch])).to be_nil
    expect(synonyms.case_only_match(nil, %w[Label])).to be_nil
  end
end
