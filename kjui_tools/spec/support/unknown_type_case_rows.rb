# frozen_string_literal: true

require 'json'
require 'tmpdir'
require_relative '../../lib/core/attribute_validator'

# The `case_only` section of shared/core/unknown_component_type_vectors.json,
# written by the Ruby validator: `known` is its types with no project around
# it (the SSoT's sections and the type synonyms), and each row a spelling it
# does not know — one of those types in another case — with the sentence it
# says. A path that names an unknown type compares its own sentence with a
# row's `expect`, byte for byte (4f's ruling: the words are a machine's, not
# copied by hand). Regenerate after the SSoT or the synonyms change:
#
#   ruby -r ./kjui_tools/spec/support/unknown_type_case_rows -e 'UnknownTypeCaseRows.write!'
module UnknownTypeCaseRows
  module_function

  VECTORS = File.expand_path('../../../shared/core/unknown_component_type_vectors.json', __dir__)
  METADATA = File.expand_path('../../../shared/core/component_metadata.json', __dir__)

  DESCRIPTION = "Written by kjui_tools/spec/support/unknown_type_case_rows.rb (UnknownTypeCaseRows.write!) from the Ruby " \
                'validator, not by hand: `known` is its types with no project (the SSoT\'s sections and the type synonyms), ' \
                'and each row a spelling it does not know — one of them in another case — with the sentence it says. ' \
                'A path compares its own sentence for `written` with `expect`, byte for byte. `not_drawn` is, per ' \
                'platform, the types component_metadata.json declares it does not draw (`platforms.<facet>: false`): ' \
                'a path does not offer them, and its rows naming one are not its words.'

  # [known types, their sentences by spelling], from a validator in an empty
  # directory (no extension definitions, no registry) with no app types.
  def table
    saved = JsonUIShared::TypeSynonyms.app_types
    JsonUIShared::TypeSynonyms.app_types = []
    Dir.mktmpdir('unknown_type_rows') do |dir|
      Dir.chdir(dir) do
        validator = Class.new(KjuiTools::Core::AttributeValidator) do
          def registered_component_types
            []
          end
        end.new(:compose)
        known = validator.send(:known_component_types).sort
        spellings = (known.flat_map { |t| [t.downcase, t.upcase, t.swapcase, t.capitalize] }.uniq - known).sort
        [known, spellings.map { |w| { 'written' => w, 'expect' => validator.unknown_component_type_message(w) } }]
      end
    end
  ensure
    JsonUIShared::TypeSynonyms.app_types = saved
  end

  # Per platform facet, the known types component_metadata.json declares it
  # does not draw.
  def not_drawn(known)
    metadata = JSON.parse(File.read(METADATA, encoding: 'UTF-8')).reject { |name, _| name.start_with?('_') }
    facets = metadata.values.flat_map { |entry| entry.fetch('platforms', {}).keys }.uniq.sort
    facets.to_h do |facet|
      [facet, known.select { |type| metadata.dig(type, 'platforms', facet) == false }]
    end
  end

  def render
    data = JSON.parse(File.read(VECTORS, encoding: 'UTF-8'))
    known, rows = table
    data['case_only'] = { '_description' => DESCRIPTION, 'known' => known, 'not_drawn' => not_drawn(known), 'rows' => rows }
    "#{JSON.pretty_generate(data)}\n"
  end

  def write!
    File.write(VECTORS, render)
  end
end
