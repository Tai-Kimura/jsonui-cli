# frozen_string_literal: true

require 'json'
require 'react/converters/base_converter'
require 'react/data_model_generator'
require 'react/react_generator'

# The lowerCamel stem of an id (refs, focus fields) is written in three
# places that must stay in sync (base_converter.rb says so); all three answer
# the `camel` column of shared/core/camel_case_vectors.json, the spelling
# sjui/kjui give an id, so a web id and a native one are the same word.
RSpec.describe 'id stems in camelCase — shared vectors (rjui)' do
  vectors = JSON.parse(File.read(File.expand_path('../../../shared/core/camel_case_vectors.json', __dir__)))
  owners = [RjuiTools::React::Converters::BaseConverter,
            RjuiTools::React::DataModelGenerator,
            RjuiTools::React::ReactGenerator]

  vectors['cases'].each do |c|
    it "spells #{c['input'].inspect} as the table does, in all three" do
      got = owners.map { |k| k.allocate.send(:snake_to_camel_id, c['input']) }
      expect(got).to eq([c['camel']] * owners.size)
    end
  end
end
