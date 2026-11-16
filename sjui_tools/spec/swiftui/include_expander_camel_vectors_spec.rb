# frozen_string_literal: true

require 'json'
require 'swiftui/include_expander'

# shared/core/camel_case_vectors.json is what this module answers: the ids a
# generated screen has. The normalizer, the web include-id helper and the
# SwiftJsonUI / KotlinJsonUI dynamic expanders read the same table, so a
# change here that is not a change there turns this red first.
RSpec.describe 'include ids in camelCase — shared vectors (sjui)' do
  vectors = JSON.parse(File.read(File.expand_path('../../../shared/core/camel_case_vectors.json', __dir__)))
  expander = SjuiTools::SwiftUI::IncludeExpander

  vectors['cases'].each do |c|
    it "spells #{c['input'].inspect} as the table does" do
      expect([expander.to_camel_case(c['input']),
              expander.combine_with_prefix(vectors['prefix'], c['input']),
              expander.combine_with_prefix(nil, c['input'])])
        .to eq([c['camel'], c['combined'], c['unprefixed']])
    end
  end
end
