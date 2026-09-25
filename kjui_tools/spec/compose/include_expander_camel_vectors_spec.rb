# frozen_string_literal: true

require 'json'
require 'compose/include_expander'

# shared/core/camel_case_vectors.json is what this module answers (with
# sjui's): the ids a generated screen has. The normalizer, the web include-id
# helper and the dynamic expanders read the same table.
RSpec.describe 'include ids in camelCase — shared vectors (kjui)' do
  vectors = JSON.parse(File.read(File.expand_path('../../../shared/core/camel_case_vectors.json', __dir__)))
  expander = KjuiTools::Compose::IncludeExpander

  vectors['cases'].each do |c|
    it "spells #{c['input'].inspect} as the table does" do
      expect([expander.to_camel_case(c['input']),
              expander.combine_with_prefix(vectors['prefix'], c['input']),
              expander.combine_with_prefix(nil, c['input'])])
        .to eq([c['camel'], c['combined'], c['unprefixed']])
    end
  end
end
