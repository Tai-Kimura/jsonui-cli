# frozen_string_literal: true

require 'swiftui/data_model_updater'
require 'core/data_class_conflict'
require 'fileutils'
require 'json'
require 'tmpdir'

# shared/core/layout_data_fields_vectors.json is the Data a layout DECLARES,
# per platform. shared/core/layout_data_fields.py reads it (the collector
# validate uses to check initialState keys); this runs sjui's own steps on the
# same files — styles, includes, extract_data_properties — and keeps what it
# marks as declared, with the class the layout wrote (before the iOS type
# conversion). The ios column is this generator's.
LAYOUT_DATA_FIELDS_VECTORS = JSON.parse(File.read(File.expand_path('../../../shared/core/layout_data_fields_vectors.json', __dir__)))

RSpec.describe 'layout data fields vectors (sjui)' do
  LAYOUT_DATA_FIELDS_VECTORS['cases'].each do |vector|
    it vector['id'] do
      Dir.mktmpdir('layout_data_fields') do |dir|
        vector['files'].each do |path, body|
          target = File.join(dir, path.sub(%r{\Alayouts/}, 'Layouts/').sub(%r{\Astyles/}, 'Styles/'))
          FileUtils.mkdir_p(File.dirname(target))
          File.write(target, JSON.generate(body))
        end
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return(
          'layouts_directory' => 'Layouts', 'data_directory' => 'Data', 'styles_directory' => 'Styles'
        )
        allow(SjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)
        allow(SjuiTools::Core::ProjectFinder).to receive(:setup_paths)

        updater = SjuiTools::SwiftUI::DataModelUpdater.new
        written_class = {}.compare_by_identity
        allow(updater).to receive(:finalize_data_property).and_wrap_original do |original, item, bindings|
          property = original.call(item, bindings)
          written_class[property] = item['class']
          property
        end

        file = File.join(dir, 'Layouts', "#{vector['screen']}.json")
        tree = updater.send(:expand_styles, JSON.parse(File.read(file)), file)
        tree = updater.send(:expand_includes, tree, File.dirname(file))
        updater.instance_variable_set(:@declared_data_properties, {}.compare_by_identity)
        updater.instance_variable_set(:@data_class_conflicts, JsonUIShared::DataClassConflict.new(vector['screen']))
        properties = updater.send(:extract_data_properties, tree, [], {})
        declared = properties.select { |p| updater.send(:declared_data_properties).key?(p) }

        expect(declared.map { |p| [p['name'], written_class[p]] }).to eq(vector['expected']['ios'])
      end
    end
  end
end
