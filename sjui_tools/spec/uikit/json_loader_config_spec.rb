# frozen_string_literal: true

require 'uikit/json_loader_config'

RSpec.describe SjuiTools::UIKit::JsonLoaderConfig do
  after do
    # Clear any loaded ignore sets
    described_class::IGNORE_ID_SET.clear
    described_class::IGNORE_DATA_SET.clear
    described_class::IGNORE_BINDING_SET.clear
  end

  describe 'VIEW_TYPE_SET' do
    it 'contains View type' do
      expect(described_class::VIEW_TYPE_SET[:View]).to eq('SJUIView')
    end

    it 'contains Label type' do
      expect(described_class::VIEW_TYPE_SET[:Label]).to eq('SJUILabel')
    end

    it 'contains Button type' do
      expect(described_class::VIEW_TYPE_SET[:Button]).to eq('SJUIButton')
    end

    it 'contains Image type' do
      expect(described_class::VIEW_TYPE_SET[:Image]).to eq('SJUIImageView')
    end

    it 'contains Table type' do
      expect(described_class::VIEW_TYPE_SET[:Table]).to eq('SJUITableView')
    end

    it 'contains Collection type' do
      expect(described_class::VIEW_TYPE_SET[:Collection]).to eq('SJUICollectionView')
    end

    it 'contains TextField type' do
      expect(described_class::VIEW_TYPE_SET[:TextField]).to eq('SJUITextField')
    end

    it 'contains TextView type' do
      expect(described_class::VIEW_TYPE_SET[:TextView]).to eq('SJUITextView')
    end

    it 'contains Switch type' do
      expect(described_class::VIEW_TYPE_SET[:Switch]).to eq('SJUISwitch')
    end

    it 'contains Web type' do
      expect(described_class::VIEW_TYPE_SET[:Web]).to eq('WKWebView')
    end

    it 'contains NetworkImage type' do
      expect(described_class::VIEW_TYPE_SET[:NetworkImage]).to eq('NetworkImageView')
    end

    it 'contains GradientView type' do
      expect(described_class::VIEW_TYPE_SET[:GradientView]).to eq('GradientView')
    end

    it 'contains SafeAreaView type' do
      expect(described_class::VIEW_TYPE_SET[:SafeAreaView]).to eq('SJUIView')
    end

    it 'contains Blur type' do
      expect(described_class::VIEW_TYPE_SET[:Blur]).to eq('SJUIVisualEffectView')
    end
  end

  describe '.load_ignore_sets_from_config' do
    context 'with ignore_id_set in config' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'ignore_id_set' => ['header_id', 'footer_id']
        })
      end

      it 'loads ignore IDs' do
        described_class.load_ignore_sets_from_config
        expect(described_class::IGNORE_ID_SET['header_id']).to be true
        expect(described_class::IGNORE_ID_SET['footer_id']).to be true
      end
    end

    context 'with ignore_data_set in config' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'ignore_data_set' => ['tempData', 'cacheData']
        })
      end

      it 'loads ignore data sets' do
        described_class.load_ignore_sets_from_config
        expect(described_class::IGNORE_DATA_SET['tempData']).to be true
        expect(described_class::IGNORE_DATA_SET['cacheData']).to be true
      end
    end

    context 'with ignore_binding_set in config' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'ignore_binding_set' => ['OldBinding', 'DeprecatedBinding']
        })
      end

      it 'loads ignore bindings' do
        described_class.load_ignore_sets_from_config
        expect(described_class::IGNORE_BINDING_SET['OldBinding']).to be true
        expect(described_class::IGNORE_BINDING_SET['DeprecatedBinding']).to be true
      end
    end

    context 'with empty config' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
      end

      it 'does not modify ignore sets' do
        described_class.load_ignore_sets_from_config
        expect(described_class::IGNORE_ID_SET).to be_empty
        expect(described_class::IGNORE_DATA_SET).to be_empty
        expect(described_class::IGNORE_BINDING_SET).to be_empty
      end
    end

    context 'with non-array ignore sets' do
      before do
        allow(SjuiTools::Core::ConfigManager).to receive(:load_config).and_return({
          'ignore_id_set' => 'not_an_array'
        })
      end

      it 'ignores non-array values' do
        described_class.load_ignore_sets_from_config
        expect(described_class::IGNORE_ID_SET).to be_empty
      end
    end
  end

  describe 'IGNORE_ID_SET' do
    it 'is empty by default' do
      expect(described_class::IGNORE_ID_SET).to be_a(Hash)
    end
  end

  describe 'IGNORE_DATA_SET' do
    it 'is empty by default' do
      expect(described_class::IGNORE_DATA_SET).to be_a(Hash)
    end
  end

  describe 'IGNORE_BINDING_SET' do
    it 'is empty by default' do
      expect(described_class::IGNORE_BINDING_SET).to be_a(Hash)
    end
  end
end
