# frozen_string_literal: true

require 'json'
require_relative '../spec_helper'

# Data-level test for the TabView `tabs[*].iconType` enum. rjui_tools loads
# `attribute_definitions.json` from `lib/core/`, but the canonical source of
# truth is `shared/core/attribute_definitions.json` (bootstrap.sh copies it
# into each tool at install time). We verify the canonical file directly so
# this test is robust against the dev checkout not having the copy in place.
RSpec.describe 'TabView iconType enum' do
  let(:shared_defs_path) do
    File.expand_path('../../../shared/core/attribute_definitions.json', __dir__)
  end

  let(:defs) { JSON.parse(File.read(shared_defs_path)) }

  it 'has shared/core/attribute_definitions.json present' do
    expect(File).to exist(shared_defs_path)
  end

  it 'declares `lucide` as a valid TabView iconType alongside system and resource' do
    tabs_item = defs.dig('TabView', 'tabs', 'items', 'properties', 'iconType')
    expect(tabs_item).not_to be_nil,
      'Expected TabView > tabs > items > properties > iconType in the schema'
    expect(tabs_item['enum']).to include('system', 'resource', 'lucide')
  end

  it 'documents the `lucide` value in the iconType description' do
    description = defs.dig('TabView', 'tabs', 'items', 'properties', 'iconType', 'description')
    expect(description).to include('lucide')
  end
end
