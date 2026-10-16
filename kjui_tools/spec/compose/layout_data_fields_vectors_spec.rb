# frozen_string_literal: true

require 'compose/data_model_updater'
require 'core/config_manager'
require 'core/project_finder'
require 'core/data_class_conflict'
require 'fileutils'
require 'json'
require 'tmpdir'

# shared/core/layout_data_fields_vectors.json is the Data a layout DECLARES,
# per platform. shared/core/layout_data_fields.py reads it (the collector
# validate uses to check initialState keys); this runs kjui's own steps on the
# same files — styles, includes, extract_data_properties — and keeps what it
# marks as declared, with the class the layout wrote (before the Kotlin type
# conversion). The android column is this generator's (mode compose).
LAYOUT_DATA_FIELDS_VECTORS = JSON.parse(
  File.read(File.expand_path('../../../shared/core/layout_data_fields_vectors.json', __dir__))
)

RSpec.describe 'layout data fields vectors (kjui)' do
  before(:context) { @kept_process_state = ProcessStateGuard.keep(KjuiTools::Core::TypeConverter) }
  after(:context) { ProcessStateGuard.put_back(@kept_process_state) }

  LAYOUT_DATA_FIELDS_VECTORS['cases'].each do |vector|
    it vector['id'] do
      Dir.mktmpdir('layout_data_fields') do |dir|
        vector['files'].each do |path, body|
          target = File.join(dir, 'src/main', path.sub(%r{\Alayouts/}, 'assets/Layouts/').sub(%r{\Astyles/}, 'assets/Styles/'))
          FileUtils.mkdir_p(File.dirname(target))
          File.write(target, JSON.generate(body))
        end
        allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return(
          'source_directory' => 'src/main', 'layouts_directory' => 'assets/Layouts',
          'styles_directory' => 'assets/Styles', 'data_directory' => 'kotlin/com/example/app/data',
          'package_name' => 'com.example.app'
        )
        allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(dir)

        updater = KjuiTools::Compose::DataModelUpdater.new
        written_class = {}.compare_by_identity
        allow(updater).to receive(:finalize_data_property).and_wrap_original do |original, item, bindings|
          property = original.call(item, bindings)
          written_class[property] = item['class']
          property
        end

        file = File.join(dir, 'src/main/assets/Layouts', "#{vector['screen']}.json")
        tree = updater.send(:expand_styles, JSON.parse(File.read(file)), file)
        tree = updater.send(:expand_includes, tree, File.dirname(file))
        updater.instance_variable_set(:@declared_data_properties, {}.compare_by_identity)
        updater.instance_variable_set(:@data_class_conflicts, JsonUIShared::DataClassConflict.new(vector['screen']))
        properties = updater.send(:extract_data_properties, tree, [], {})
        declared = properties.select { |p| updater.send(:declared_data_properties).key?(p) }

        expect(declared.map { |p| [p['name'], written_class[p]] }).to eq(vector['expected']['android'])
      end
    end
  end
end
