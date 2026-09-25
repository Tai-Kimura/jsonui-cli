# frozen_string_literal: true

require 'compose/generators/converter_generator'
require 'core/config_manager'
require 'core/project_finder'
require 'core/logger'
require 'fileutils'
require 'json'

RSpec.describe KjuiTools::Compose::Generators::ConverterGenerator do
  let(:temp_dir) { Dir.mktmpdir('converter_gen_test') }

  before do
    @original_dir = Dir.pwd
    Dir.chdir(temp_dir)
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
      '_config_dir' => temp_dir,
      'source_directory' => 'src/main',
      'package_name' => 'com.example.app'
    })
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_package_name).and_return('com.example.app')
    allow(KjuiTools::Core::Logger).to receive(:info)
    allow(KjuiTools::Core::Logger).to receive(:warn)
    allow(KjuiTools::Core::Logger).to receive(:success)
  end

  after do
    Dir.chdir(@original_dir)
    FileUtils.rm_rf(temp_dir)
  end

  describe '#initialize' do
    it 'creates generator with name' do
      generator = described_class.new('TestCard')
      expect(generator).to be_a(described_class)
    end

    it 'creates generator with options' do
      generator = described_class.new('TestCard', { attributes: { 'title' => 'String' } })
      expect(generator).to be_a(described_class)
    end
  end

  describe 'private helper methods' do
    let(:generator) { described_class.new('TestCard') }

    describe '#to_snake_case' do
      it 'converts PascalCase to snake_case' do
        result = generator.send(:to_snake_case, 'TestCard')
        expect(result).to eq('test_card')
      end

      it 'converts camelCase to snake_case' do
        result = generator.send(:to_snake_case, 'testCard')
        expect(result).to eq('test_card')
      end

      it 'handles multiple capitals' do
        result = generator.send(:to_snake_case, 'XMLParser')
        expect(result).to eq('xml_parser')
      end

      it 'handles simple lowercase' do
        result = generator.send(:to_snake_case, 'test')
        expect(result).to eq('test')
      end
    end

    describe '#converter_template' do
      it 'generates valid Ruby class' do
        template = generator.send(:converter_template)
        expect(template).to include('module KjuiTools')
        expect(template).to include('class TestCardComponent')
        expect(template).to include('def self.generate')
      end

      it 'includes component name' do
        template = generator.send(:converter_template)
        expect(template).to include('TestCard(')
      end

      it 'includes modifier building' do
        template = generator.send(:converter_template)
        expect(template).to include('ModifierBuilder.build_size')
        expect(template).to include('ModifierBuilder.build_padding')
      end

      # 🚨 Reported 2026-09-08. The template listed size / offset / padding /
      # margins / background and NOT `build_test_tag`, so every custom
      # component generated from it emitted no `testTag` — and with no
      # testTag there is no resource-id, so Android UI tests cannot find the
      # node at all. One consumer face measured 63 nodes becoming reachable
      # (none lost) after adding the call to their eight converters by hand.
      #
      # ⚠️ The gap was invisible to every existing arm here because they
      # assert what the template DOES contain. Nothing counted what the
      # built-in components contain that the template does not — which is the
      # comparison that finds an omission.
      it 'emits a testTag, as 27 of the 28 built-in components do' do
        template = generator.send(:converter_template)
        expect(template).to include('ModifierBuilder.build_test_tag')
      end

      it 'builds the testTag before the geometry modifiers' do
        # Same order the built-ins use (see button_component.rb). Asserted
        # because a modifier list is order-sensitive and "present somewhere"
        # is a weaker claim than the built-ins actually satisfy.
        template = generator.send(:converter_template)
        expect(template.index('ModifierBuilder.build_test_tag'))
          .to be < template.index('ModifierBuilder.build_size')
      end
    end

    describe '#generate_parameter_collection' do
      it 'returns empty string when no attributes' do
        result = generator.send(:generate_parameter_collection)
        expect(result).to eq('')
      end

      it 'generates parameter collection code for attributes' do
        generator_with_attrs = described_class.new('Test', { attributes: { 'title' => 'String' } })
        result = generator_with_attrs.send(:generate_parameter_collection)
        expect(result).to include("json_data['title']")
        expect(result).to include('format_value.call')
      end

      it 'handles binding attributes' do
        generator_with_attrs = described_class.new('Test', { attributes: { '@name' => 'String' } })
        result = generator_with_attrs.send(:generate_parameter_collection)
        expect(result).to include("json_data['name']")
        expect(result).to include('binding')
      end
    end

    describe '#map_type_to_json_type' do
      it 'maps string types to string with binding support' do
        result = generator.send(:map_type_to_json_type, 'String')
        expect(result).to eq(['string', 'binding'])
      end

      it 'maps text type to binding (custom types require binding syntax)' do
        result = generator.send(:map_type_to_json_type, 'Text')
        expect(result).to eq('binding')
      end

      it 'maps Color to string with binding support (semantic key or @{binding})' do
        result = generator.send(:map_type_to_json_type, 'Color')
        expect(result).to eq(['string', 'binding'])
      end

      it 'maps lowercase color the same way' do
        result = generator.send(:map_type_to_json_type, 'color')
        expect(result).to eq(['string', 'binding'])
      end

      it 'maps int to number with binding support' do
        result = generator.send(:map_type_to_json_type, 'Int')
        expect(result).to eq(['number', 'binding'])
      end

      it 'maps integer to number with binding support' do
        result = generator.send(:map_type_to_json_type, 'Integer')
        expect(result).to eq(['number', 'binding'])
      end

      it 'maps float to number with binding support' do
        result = generator.send(:map_type_to_json_type, 'Float')
        expect(result).to eq(['number', 'binding'])
      end

      it 'maps double to number with binding support' do
        result = generator.send(:map_type_to_json_type, 'Double')
        expect(result).to eq(['number', 'binding'])
      end

      it 'maps bool to boolean with binding support' do
        result = generator.send(:map_type_to_json_type, 'Bool')
        expect(result).to eq(['boolean', 'binding'])
      end

      it 'maps boolean to boolean with binding support' do
        result = generator.send(:map_type_to_json_type, 'Boolean')
        expect(result).to eq(['boolean', 'binding'])
      end

      it 'defaults unknown types to binding (custom types require binding syntax)' do
        result = generator.send(:map_type_to_json_type, 'UnknownType')
        expect(result).to eq('binding')
      end
    end

    describe '#generate_debug_initializer_content' do
      it 'generates debug initializer with package' do
        result = generator.send(:generate_debug_initializer_content, 'com.example.app')
        expect(result).to include('package com.example.app')
        expect(result).to include('DynamicComponentInitializer')
        expect(result).to include('Configuration.customComponentHandler')
      end
    end

    describe '#generate_release_initializer_content' do
      it 'generates release initializer with no-op' do
        result = generator.send(:generate_release_initializer_content, 'com.example.app')
        expect(result).to include('package com.example.app')
        expect(result).to include('DynamicComponentInitializer')
        expect(result).to include('No-op')
      end
    end

    describe '#create_initial_mappings_file' do
      it 'creates initial mappings file' do
        generator.send(:create_initial_mappings_file)

        extensions_dir = File.join(File.dirname(__FILE__), '..', '..', '..', 'lib', 'compose', 'components', 'extensions')
        mappings_file = File.expand_path(File.join(extensions_dir, 'component_mappings.rb'))

        expect(File.exist?(mappings_file)).to be true
        content = File.read(mappings_file)
        expect(content).to include('COMPONENT_MAPPINGS')
        expect(content).to include('TestCard')

        # Cleanup
        FileUtils.rm_f(mappings_file)
      end
    end
  end

  # jui-g-converter-drops-spec-prop-descriptions: until 1.8.113 every
  # regeneration wrote "<key> attribute" over the spec's descriptions.
  # attr_defs_dir resolves into the tool copy, so it is pointed at the example's
  # temp dir here instead of writing (and cleaning) under lib/.
  describe "#generate_attribute_definition_file with the component spec's descriptions" do
    it 'writes the descriptions handed down by jui g converter --from / --all' do
      generator = described_class.new('DescribedCard', {
        attributes: { 'title' => 'String', '@value' => 'String', 'count' => 'Int' },
        attribute_descriptions: { 'title' => '見出し', 'value' => '入力値' }
      })
      defs_dir = File.join(temp_dir, 'attribute_definitions')
      allow(generator).to receive(:attr_defs_dir).and_return(defs_dir)
      generator.send(:generate_attribute_definition_file)

      content = JSON.parse(File.read(File.join(defs_dir, 'DescribedCard.json'), encoding: 'UTF-8'))
      expect(content['DescribedCard']['title']['description']).to eq('見出し')
      expect(content['DescribedCard']['value']['description']).to eq('入力値')   # the spec names it without "@"
      expect(content['DescribedCard']['count']['description']).to eq('count attribute')
    end
  end

  describe '#generate with attribute definition file' do
    let(:generator) { described_class.new('MyCustomCard', { attributes: { 'title' => 'String', 'count' => 'Int', 'active' => 'Boolean' } }) }

    before do
      # Stub the generators that get called
      allow_any_instance_of(KjuiTools::Compose::Generators::KotlinComponentGenerator).to receive(:generate)
      allow_any_instance_of(KjuiTools::Compose::Generators::DynamicComponentGenerator).to receive(:generate)

      # Allow file operations to stdin for overwrite prompt
      allow($stdin).to receive(:gets).and_return('n')
    end

    after do
      # Clean up generated files
      extensions_dir = File.join(File.dirname(__FILE__), '..', '..', '..', 'lib', 'compose', 'components', 'extensions')
      extensions_dir = File.expand_path(extensions_dir)

      FileUtils.rm_f(File.join(extensions_dir, 'my_custom_card_component.rb'))
      FileUtils.rm_f(File.join(extensions_dir, 'component_mappings.rb'))

      definitions_dir = File.join(extensions_dir, 'attribute_definitions')
      FileUtils.rm_f(File.join(definitions_dir, 'MyCustomCard.json'))
    end

    it 'generates attribute definition file' do
      generator.generate

      extensions_dir = File.join(File.dirname(__FILE__), '..', '..', '..', 'lib', 'compose', 'components', 'extensions')
      definitions_dir = File.join(extensions_dir, 'attribute_definitions')
      definition_file = File.expand_path(File.join(definitions_dir, 'MyCustomCard.json'))

      expect(File.exist?(definition_file)).to be true

      # Read and parse the JSON
      definition_content = JSON.parse(File.read(definition_file))

      # Check structure
      expect(definition_content).to have_key('MyCustomCard')
      expect(definition_content['MyCustomCard']).to have_key('title')
      expect(definition_content['MyCustomCard']).to have_key('count')
      expect(definition_content['MyCustomCard']).to have_key('active')

      # Check type mapping (with binding support)
      expect(definition_content['MyCustomCard']['title']['type']).to eq(['string', 'binding'])
      expect(definition_content['MyCustomCard']['count']['type']).to eq(['number', 'binding'])
      expect(definition_content['MyCustomCard']['active']['type']).to eq(['boolean', 'binding'])

      # Check descriptions
      expect(definition_content['MyCustomCard']['title']['description']).to eq('title attribute')
      expect(definition_content['MyCustomCard']['count']['description']).to eq('count attribute')
      expect(definition_content['MyCustomCard']['active']['description']).to eq('active attribute')
    end

    it 'handles binding attributes correctly' do
      generator_with_binding = described_class.new('BindingCard', { attributes: { '@userName' => 'String', 'staticValue' => 'Int' } })

      # Stub generators
      allow_any_instance_of(KjuiTools::Compose::Generators::KotlinComponentGenerator).to receive(:generate)
      allow_any_instance_of(KjuiTools::Compose::Generators::DynamicComponentGenerator).to receive(:generate)
      allow($stdin).to receive(:gets).and_return('n')

      generator_with_binding.generate

      extensions_dir = File.join(File.dirname(__FILE__), '..', '..', '..', 'lib', 'compose', 'components', 'extensions')
      definitions_dir = File.join(extensions_dir, 'attribute_definitions')
      definition_file = File.expand_path(File.join(definitions_dir, 'BindingCard.json'))

      expect(File.exist?(definition_file)).to be true

      definition_content = JSON.parse(File.read(definition_file))

      # Should strip @ prefix
      expect(definition_content['BindingCard']).to have_key('userName')
      expect(definition_content['BindingCard']).not_to have_key('@userName')
      expect(definition_content['BindingCard']).to have_key('staticValue')

      # Cleanup
      FileUtils.rm_f(File.join(extensions_dir, 'binding_card_component.rb'))
      FileUtils.rm_f(File.join(extensions_dir, 'component_mappings.rb'))
      FileUtils.rm_f(definition_file)
    end

    # Since 1.8.121 the file is written with no attributes too: it is where the
    # build reads whether the component takes children (child / children for
    # the default). Until then a component with no attributes had none.
    # Ticket sjui-leaf-custom-component-cannot-reject-children.
    it 'writes only whether the component takes children when there are no attributes' do
      generator_no_attrs = described_class.new('SimpleCard', {})

      # Stub generators
      allow_any_instance_of(KjuiTools::Compose::Generators::KotlinComponentGenerator).to receive(:generate)
      allow_any_instance_of(KjuiTools::Compose::Generators::DynamicComponentGenerator).to receive(:generate)
      allow($stdin).to receive(:gets).and_return('n')

      extensions_dir = File.join(File.dirname(__FILE__), '..', '..', '..', 'lib', 'compose', 'components', 'extensions')
      definitions_dir = File.join(extensions_dir, 'attribute_definitions')
      definition_file = File.expand_path(File.join(definitions_dir, 'SimpleCard.json'))
      begin
        generator_no_attrs.generate
        expect(JSON.parse(File.read(definition_file))['SimpleCard'].keys).to contain_exactly('child', 'children')
      ensure
        # Written into the tool's own tree: cleaned whether or not the
        # expectation holds (a failure here used to leave it behind).
        FileUtils.rm_f(definition_file)
        FileUtils.rm_f(File.join(extensions_dir, 'simple_card_component.rb'))
        FileUtils.rm_f(File.join(extensions_dir, 'component_mappings.rb'))
      end
    end
  end

  describe '#generate' do
    let(:generator) { described_class.new('StatusBadge', { attributes: { 'text' => 'String', 'color' => 'Color' } }) }

    before do
      # Stub the generators that get called
      allow_any_instance_of(KjuiTools::Compose::Generators::KotlinComponentGenerator).to receive(:generate)
      allow_any_instance_of(KjuiTools::Compose::Generators::DynamicComponentGenerator).to receive(:generate)

      # Allow file operations to stdin for overwrite prompt
      allow($stdin).to receive(:gets).and_return('n')
    end

    after do
      # Cleanup
      extensions_dir = File.join(File.dirname(__FILE__), '..', '..', '..', 'lib', 'compose', 'components', 'extensions')
      extensions_dir = File.expand_path(extensions_dir)

      FileUtils.rm_f(File.join(extensions_dir, 'status_badge_component.rb'))
      FileUtils.rm_f(File.join(extensions_dir, 'component_mappings.rb'))

      definitions_dir = File.join(extensions_dir, 'attribute_definitions')
      FileUtils.rm_f(File.join(definitions_dir, 'StatusBadge.json'))
    end

    it 'creates converter files' do
      # Clean up any existing files first
      extensions_dir = File.join(File.dirname(__FILE__), '..', '..', '..', 'lib', 'compose', 'components', 'extensions')
      extensions_dir = File.expand_path(extensions_dir)
      status_badge_file = File.join(extensions_dir, 'status_badge_component.rb')
      mappings_file = File.join(extensions_dir, 'component_mappings.rb')

      FileUtils.rm_f(status_badge_file)
      FileUtils.rm_f(mappings_file)

      # Run generator
      generator.generate

      # Check files were created
      expect(File.exist?(status_badge_file)).to be true
      expect(File.exist?(mappings_file)).to be true

      # Check content
      converter_content = File.read(status_badge_file)
      expect(converter_content).to include('class StatusBadgeComponent')
      expect(converter_content).to include('StatusBadge(')
    end

    it 'creates dynamic initializer files' do
      generator.generate

      debug_dir = File.join(temp_dir, 'src/debug/kotlin/com/example/app')
      release_dir = File.join(temp_dir, 'src/release/kotlin/com/example/app')

      expect(File.exist?(File.join(debug_dir, 'DynamicComponentInitializer.kt'))).to be true
      expect(File.exist?(File.join(release_dir, 'DynamicComponentInitializer.kt'))).to be true
    end
  end

  describe 'converter template with container' do
    let(:generator) { described_class.new('CardContainer', { is_container: true }) }

    it 'generates container-aware template' do
      template = generator.send(:converter_template)
      expect(template).to include('children')
      expect(template).to include('is_container')
    end
  end

  describe 'converter template with multiple attributes' do
    let(:generator) { described_class.new('MyWidget', { attributes: { 'title' => 'String', 'count' => 'Int', 'active' => 'Boolean' } }) }

    it 'includes all attributes in template' do
      params = generator.send(:generate_parameter_collection)
      expect(params).to include("json_data['title']")
      expect(params).to include("json_data['count']")
      expect(params).to include("json_data['active']")
    end
  end
end
