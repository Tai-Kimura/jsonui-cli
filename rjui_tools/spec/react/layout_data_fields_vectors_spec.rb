# frozen_string_literal: true

require 'tmpdir'
require 'fileutils'
require 'json'

require_relative '../spec_helper'
require 'react/data_model_generator'

# shared/core/layout_data_fields_vectors.json is the Data a layout DECLARES,
# per platform. shared/core/layout_data_fields.py reads it (the collector
# validate uses to check initialState keys); this runs rjui's own steps on the
# same files — styles, includes, extract_data_properties, as process_json_file
# does — and keeps what it marks as declared, with the class the layout wrote
# (before the TypeScript conversion). The web column is this generator's.
LAYOUT_DATA_FIELDS_VECTORS = JSON.parse(
  File.read(File.expand_path('../../../shared/core/layout_data_fields_vectors.json', __dir__))
)

RSpec.describe 'layout data fields vectors (rjui)' do
  LAYOUT_DATA_FIELDS_VECTORS['cases'].each do |vector|
    it vector['id'] do
      Dir.mktmpdir('layout_data_fields') do |dir|
        vector['files'].each do |path, body|
          target = File.join(dir, path.sub(%r{\Alayouts/}, 'Layouts/').sub(%r{\Astyles/}, 'Styles/'))
          FileUtils.mkdir_p(File.dirname(target))
          File.write(target, JSON.generate(body))
        end
        layouts_dir = File.join(dir, 'Layouts')
        styles_dir = File.join(dir, 'Styles')

        generator = RjuiTools::React::DataModelGenerator.new
        written_class = {}.compare_by_identity
        allow(generator).to receive(:normalize_declared_data).and_wrap_original do |original, item, bindings|
          property = original.call(item, bindings)
          written_class[property] = item['class']
          property
        end

        file = File.join(layouts_dir, "#{vector['screen']}.json")
        tree = RjuiTools::React::StyleLoader.load_and_merge(JSON.parse(File.read(file)), styles_dir)
        tree = RjuiTools::React::IncludeExpander.process_includes(tree, File.dirname(file), nil, layouts_dir)
        generator.instance_variable_set(:@declared_data_properties, {}.compare_by_identity)
        generator.instance_variable_set(:@data_class_conflicts, JsonUIShared::DataClassConflict.new(vector['screen']))
        properties = generator.send(:extract_data_properties, tree, [], true, {})
        declared = properties.select { |p| generator.send(:declared_data_properties).key?(p) }

        expect(declared.map { |p| [p['name'], written_class[p]] }).to eq(vector['expected']['web'])

        # The Data type rjui writes from these properties — the declared
        # fields plus the test bridge's table and functions over them —
        # compiles beside the emitted helper.
        model = generator.send(:generate_typescript_content, 'Screen', properties)
        expect(model.scan(/^      case (".*"):$/).flatten).to eq(declared.map { |p| p['name'].to_json })
        expect(model).to compile_as_typescript
      end
    end
  end
end
