# frozen_string_literal: true

require_relative '../../lib/core/enum_spelling'

# `canonical`: a declared valueAliases key is its target, anything else is
# itself — what a converter keyed by canonical spellings looks values up by.
RSpec.describe 'JsonUIShared::EnumSpelling.canonical' do
  spelling = JsonUIShared::EnumSpelling

  it 'resolves each declared alias of TextField.contentType' do
    expect(spelling.canonical('phone', 'TextField', 'contentType')).to eq('telephoneNumber')
    expect(spelling.canonical('tel', 'TextField', 'contentType')).to eq('telephoneNumber')
    expect(spelling.canonical('emailAddress', 'TextField', 'contentType')).to eq('email')
  end

  it 'leaves a canonical spelling, an undeclared one and a non-string alone' do
    expect(spelling.canonical('email', 'TextField', 'contentType')).to eq('email')
    expect(spelling.canonical('Phone', 'TextField', 'contentType')).to eq('Phone')
    expect(spelling.canonical(nil, 'TextField', 'contentType')).to be_nil
  end

  it 'reads common for an attribute the section does not declare' do
    expect(spelling.canonical('systemMaterial', 'View', 'effectStyle')).to eq('Regular')
  end
end
