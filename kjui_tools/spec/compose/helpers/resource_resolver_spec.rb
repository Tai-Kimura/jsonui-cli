# frozen_string_literal: true

require 'compose/helpers/resource_resolver'
require 'core/config_manager'
require 'core/project_finder'

RSpec.describe KjuiTools::Compose::Helpers::ResourceResolver do
  let(:temp_dir) { Dir.mktmpdir('resource_resolver_test') }
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
      'source_directory' => 'src/main',
      'layouts_directory' => 'assets/Layouts'
    })
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return(temp_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '.process_text' do
    after(:each) do
      # Clean up thread-local storage
      described_class.data_definitions = {}
    end

    context 'with data binding' do
      it 'returns binding with ?: "" for optional property (no defaultValue)' do
        # Property without defaultValue is optional
        described_class.data_definitions = {
          'userName' => { 'name' => 'userName', 'type' => 'String' }
        }
        result = described_class.process_text('@{userName}', required_imports)
        expect(result).to eq('"${data.userName ?: ""}"')
      end

      it 'returns binding without ?: for non-optional property (with defaultValue)' do
        # Property with defaultValue is non-optional
        described_class.data_definitions = {
          'userName' => { 'name' => 'userName', 'type' => 'String', 'defaultValue' => 'Guest' }
        }
        result = described_class.process_text('@{userName}', required_imports)
        expect(result).to eq('"${data.userName}"')
      end
    end

    it 'evaluates the ?? default instead of stripping it (canonical emit)' do
      result = described_class.process_text('@{userName ?? "Guest"}', required_imports)
      expect(result).to eq('"${data.userName ?: "Guest"}"')
    end

    it 'accepts single-quoted ?? defaults (canonical-new spelling)' do
      result = described_class.process_text("@{userName ?? 'Guest'}", required_imports)
      expect(result).to eq('"${data.userName ?: "Guest"}"')
    end

    it 'emits plain access when the property has a data-section defaultValue (inline default is dead)' do
      described_class.data_definitions = {
        'userName' => { 'name' => 'userName', 'class' => 'String', 'defaultValue' => 'X' }
      }
      result = described_class.process_text('@{userName ?? "Guest"}', required_imports)
      expect(result).to eq('"${data.userName}"')
    ensure
      described_class.data_definitions = {}
    end

    it 'quotes plain text' do
      result = described_class.process_text('Hello World', required_imports)
      expect(result).to eq('"Hello World"')
    end

    it 'escapes special characters' do
      result = described_class.process_text('Line1\nLine2', required_imports)
      expect(result).to include('Line1')
    end

    context 'with Resources directory' do
      before do
        resources_dir = File.join(temp_dir, 'src/main/assets/Layouts/Resources')
        FileUtils.mkdir_p(resources_dir)
        File.write(File.join(resources_dir, 'strings.json'), JSON.generate({
          'home' => { 'title' => 'Welcome' }
        }))
      end

      it 'resolves string resource' do
        result = described_class.process_text('Welcome', required_imports)
        expect(result).to include('stringResource')
        expect(required_imports).to include(:string_resource)
      end
    end

    # sjui names a strings.json section after the layout's basename and
    # kjui after its relative path, so a cell under a screen directory
    # ends up declared under both — and scanning the file in order made
    # the winner depend on how the SSoT happened to be sorted.
    context 'when two sections declare the same text' do
      before do
        resources_dir = File.join(temp_dir, 'src/main/assets/Layouts/Resources')
        FileUtils.mkdir_p(resources_dir)
        File.write(File.join(resources_dir, 'strings.json'), JSON.generate({
          'hero_section_cell' => { 'rating' => 'RATING' },
          'item_detail_hero_section_cell' => { 'rating' => 'RATING' }
        }))
      end

      after { described_class.current_namespaces = [] }

      it 'reads the section the layout owns, not the first in the file' do
        described_class.begin_layout('item_detail/hero_section_cell.json')
        expect(described_class.process_text('RATING', required_imports))
          .to include('R.string.item_detail_hero_section_cell_rating')
      end

      it 'keeps file order when the layout owns no declared section' do
        described_class.begin_layout('login.json')
        expect(described_class.process_text('RATING', required_imports))
          .to include('R.string.hero_section_cell_rating')
      end

      it 'folds a variant into the base screen sections' do
        described_class.begin_layout('item_detail/hero_section_cell@regular.json')
        expect(described_class.process_text('RATING', required_imports))
          .to include('R.string.item_detail_hero_section_cell_rating')
      end
    end
  end

  describe '.process_color' do
    after(:each) do
      # Clean up thread-local storage
      described_class.data_definitions = {}
    end

    it 'returns nil for non-string' do
      result = described_class.process_color(nil, required_imports)
      expect(result).to be_nil
    end

    it 'processes hex color' do
      result = described_class.process_color('#FF0000', required_imports)
      expect(result).to include('Color')
      expect(result).to include('parseColor')
    end

    context 'with data binding color' do
      it 'returns data binding with ?: Color.Unspecified for optional property (no defaultValue)' do
        # Property without defaultValue is optional
        described_class.data_definitions = {
          'themeColor' => { 'name' => 'themeColor', 'type' => 'Color' }
        }
        result = described_class.process_color('@{themeColor}', required_imports)
        expect(result).to eq('data.themeColor ?: Color.Unspecified')
      end

      it 'returns data binding without ?: for non-optional property (with defaultValue)' do
        # Property with defaultValue is non-optional
        described_class.data_definitions = {
          'themeColor' => { 'name' => 'themeColor', 'type' => 'Color', 'defaultValue' => '#FF0000' }
        }
        result = described_class.process_color('@{themeColor}', required_imports)
        expect(result).to eq('data.themeColor')
      end

      it 'returns data binding with ?: Color.Unspecified when property not in definitions' do
        # Property not in definitions is treated as optional
        described_class.data_definitions = {}
        result = described_class.process_color('@{unknownColor}', required_imports)
        expect(result).to eq('data.unknownColor ?: Color.Unspecified')
      end
    end

    context 'with Resources directory' do
      before do
        resources_dir = File.join(temp_dir, 'src/main/assets/Layouts/Resources')
        FileUtils.mkdir_p(resources_dir)
        File.write(File.join(resources_dir, 'colors.json'), JSON.generate({
          'primary' => '#FF0000'
        }))
      end

      it 'resolves color by key' do
        result = described_class.process_color('primary', required_imports)
        expect(result).to include('colorResource')
        expect(required_imports).to include(:color_resource)
      end

      it 'resolves color by value' do
        result = described_class.process_color('#FF0000', required_imports)
        expect(result).to include('colorResource')
      end
    end

    context 'with colors.xml' do
      before do
        res_dir = File.join(temp_dir, 'src/main/res/values')
        FileUtils.mkdir_p(res_dir)
        File.write(File.join(res_dir, 'colors.xml'), '<resources><color name="accent">#00FF00</color></resources>')
      end

      it 'checks colors.xml for color names' do
        result = described_class.process_color('accent', required_imports)
        # Without Resources dir, won't resolve to colorResource
        expect(result).not_to be_nil
      end
    end
  end

  describe '.drawable_name' do
    it 'strips image extensions' do
      expect(described_class.drawable_name('photo.png')).to eq('photo')
    end

    it 'sanitizes SF-Symbol style dotted names' do
      expect(described_class.drawable_name('star.fill')).to eq('star_fill')
    end

    it 'lowercases and replaces invalid identifier chars' do
      expect(described_class.drawable_name('My Image-2')).to eq('my_image_2')
    end

    it 'prefixes names that do not start with a letter' do
      expect(described_class.drawable_name('9patch')).to eq('img_9patch')
    end
  end
end
