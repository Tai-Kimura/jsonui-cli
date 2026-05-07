# frozen_string_literal: true

require 'swiftui/style_loader'
require 'json'
require 'fileutils'

RSpec.describe SjuiTools::SwiftUI::StyleLoader do
  let(:temp_dir) { File.join(Dir.tmpdir, 'style_loader_test') }
  let(:styles_dir) { File.join(temp_dir, 'Styles') }

  before do
    FileUtils.mkdir_p(styles_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '.load_and_merge' do
    context 'without style attribute' do
      it 'returns component unchanged' do
        component = { 'type' => 'Label', 'text' => 'Hello' }
        result = described_class.load_and_merge(component, styles_dir)

        expect(result).to eq(component)
      end
    end

    context 'with non-hash component' do
      it 'returns input unchanged for array' do
        result = described_class.load_and_merge([1, 2, 3], styles_dir)
        expect(result).to eq([1, 2, 3])
      end

      it 'returns input unchanged for nil' do
        result = described_class.load_and_merge(nil, styles_dir)
        expect(result).to be_nil
      end

      it 'returns input unchanged for string' do
        result = described_class.load_and_merge('test', styles_dir)
        expect(result).to eq('test')
      end
    end

    context 'with style attribute' do
      before do
        style_content = {
          'fontSize' => 16,
          'fontColor' => '#333333',
          'background' => '#FFFFFF'
        }
        File.write(File.join(styles_dir, 'card_style.json'), JSON.generate(style_content))
      end

      it 'merges style file properties' do
        component = {
          'type' => 'Label',
          'style' => 'card_style',
          'text' => 'Hello'
        }

        result = described_class.load_and_merge(component, styles_dir)

        expect(result['fontSize']).to eq(16)
        expect(result['fontColor']).to eq('#333333')
        expect(result['text']).to eq('Hello')
      end

      it 'component properties override style properties' do
        component = {
          'type' => 'Label',
          'style' => 'card_style',
          'fontSize' => 20
        }

        result = described_class.load_and_merge(component, styles_dir)

        expect(result['fontSize']).to eq(20)
      end

      it 'removes style attribute after merge' do
        component = {
          'type' => 'Label',
          'style' => 'card_style'
        }

        result = described_class.load_and_merge(component, styles_dir)

        expect(result['style']).to be_nil
      end
    end

    context 'with style file containing type' do
      before do
        # スタイルファイルにtype: "View"があるケース
        style_content = {
          'type' => 'View',
          'fontSize' => 24,
          'fontColor' => '#000000'
        }
        File.write(File.join(styles_dir, 'view_style.json'), JSON.generate(style_content))
      end

      it 'ignores style file type and preserves component type' do
        component = {
          'type' => 'Label',
          'style' => 'view_style',
          'text' => 'Hello'
        }

        result = described_class.load_and_merge(component, styles_dir)

        # コンポーネントのtype: "Label"が保持される（スタイルのtype: "View"は無視）
        expect(result['type']).to eq('Label')
        # スタイルの他の属性はマージされる
        expect(result['fontSize']).to eq(24)
        expect(result['fontColor']).to eq('#000000')
      end

      it 'uses style type when component has no type' do
        component = {
          'style' => 'view_style',
          'text' => 'Hello'
        }

        result = described_class.load_and_merge(component, styles_dir)

        # コンポーネントにtypeがない場合、スタイルのtypeを使用する
        expect(result['type']).to eq('View')
        # 他の属性はマージされる
        expect(result['fontSize']).to eq(24)
      end
    end

    context 'with missing style file' do
      it 'removes style attribute and continues' do
        component = {
          'type' => 'Label',
          'style' => 'nonexistent_style',
          'text' => 'Hello'
        }

        result = described_class.load_and_merge(component, styles_dir)

        expect(result['style']).to be_nil
        expect(result['text']).to eq('Hello')
      end
    end

    context 'with child array' do
      before do
        style_content = { 'fontSize' => 14 }
        File.write(File.join(styles_dir, 'child_style.json'), JSON.generate(style_content))
      end

      it 'processes children recursively' do
        component = {
          'type' => 'View',
          'child' => [
            {
              'type' => 'Label',
              'style' => 'child_style',
              'text' => 'Child 1'
            },
            {
              'type' => 'Label',
              'text' => 'Child 2'
            }
          ]
        }

        result = described_class.load_and_merge(component, styles_dir)

        expect(result['child'][0]['fontSize']).to eq(14)
        expect(result['child'][1]['text']).to eq('Child 2')
      end
    end

    context 'with single child' do
      before do
        style_content = { 'cornerRadius' => 8 }
        File.write(File.join(styles_dir, 'single_style.json'), JSON.generate(style_content))
      end

      it 'processes single child' do
        component = {
          'type' => 'View',
          'child' => {
            'type' => 'Button',
            'style' => 'single_style'
          }
        }

        result = described_class.load_and_merge(component, styles_dir)

        expect(result['child']['cornerRadius']).to eq(8)
      end
    end

    context 'with children attribute' do
      before do
        style_content = { 'padding' => 10 }
        File.write(File.join(styles_dir, 'children_style.json'), JSON.generate(style_content))
      end

      it 'processes children array' do
        component = {
          'type' => 'View',
          'children' => [
            {
              'type' => 'Label',
              'style' => 'children_style'
            }
          ]
        }

        result = described_class.load_and_merge(component, styles_dir)

        expect(result['children'][0]['padding']).to eq(10)
      end

      it 'processes single children' do
        component = {
          'type' => 'View',
          'children' => {
            'type' => 'Label',
            'style' => 'children_style'
          }
        }

        result = described_class.load_and_merge(component, styles_dir)

        expect(result['children']['padding']).to eq(10)
      end
    end

    context 'with invalid JSON style file' do
      before do
        File.write(File.join(styles_dir, 'invalid.json'), 'not valid json')
      end

      it 'handles parse error gracefully' do
        component = {
          'type' => 'Label',
          'style' => 'invalid'
        }

        result = described_class.load_and_merge(component, styles_dir)

        expect(result['style']).to be_nil
      end
    end
  end

  describe '.deep_merge' do
    it 'merges nested hashes' do
      hash1 = { 'a' => { 'b' => 1, 'c' => 2 } }
      hash2 = { 'a' => { 'c' => 3, 'd' => 4 } }

      result = described_class.send(:deep_merge, hash1, hash2)

      expect(result['a']['b']).to eq(1)
      expect(result['a']['c']).to eq(3)
      expect(result['a']['d']).to eq(4)
    end

    it 'overwrites arrays' do
      hash1 = { 'items' => [1, 2, 3] }
      hash2 = { 'items' => [4, 5] }

      result = described_class.send(:deep_merge, hash1, hash2)

      expect(result['items']).to eq([4, 5])
    end

    it 'handles nil hash1' do
      result = described_class.send(:deep_merge, nil, { 'a' => 1 })
      expect(result).to eq({ 'a' => 1 })
    end

    it 'handles nil hash2' do
      result = described_class.send(:deep_merge, { 'a' => 1 }, nil)
      expect(result).to eq({ 'a' => 1 })
    end

    it 'overwrites non-hash values' do
      hash1 = { 'value' => 'old' }
      hash2 = { 'value' => 'new' }

      result = described_class.send(:deep_merge, hash1, hash2)

      expect(result['value']).to eq('new')
    end
  end
end
