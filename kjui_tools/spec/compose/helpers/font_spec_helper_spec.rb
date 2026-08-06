# frozen_string_literal: true

require 'json'
require 'tmpdir'
require 'compose/helpers/font_spec_helper'

RSpec.describe KjuiTools::Compose::Helpers::FontSpecHelper do
  describe '.weight_mapping' do
    it 'reads kotlin column from shared/core/font_weight_mapping.json' do
      mapping = described_class.weight_mapping
      expect(mapping['bold']).to eq('FontWeight.Bold')
      expect(mapping['regular']).to eq('FontWeight.Normal')
      expect(mapping['semibold']).to eq('FontWeight.SemiBold')
      expect(mapping['heavy']).to eq('FontWeight.Black')
    end
  end

  describe '.weight_mapping candidate paths' do
    # Every developer machine with a ~/.jsonui-cli install resolves candidate
    # 3, so a wrong depth in candidates 1/2 is invisible locally and only CI
    # sees the empty table (84a5cb8: numbers fell to FontWeight(n) because
    # only the css index starved — the names were caught by the fallback).
    # This asserts the checkout's own layout resolves WITHOUT the global
    # install, so the hidden-by-environment failure cannot come back.
    it 'resolves a real file from the repo checkout, before the global install' do
      local = described_class.weight_mapping_candidates.reject { |p| p.include?('.jsonui-cli') }
      expect(local.any? { |p| File.exist?(p) }).to be(true),
        "no repo-local candidate exists: #{local.inspect}"
    end
  end

  describe '.weight_mapping resolution chain' do
    after { described_class.weight_mapping_candidates = nil }

    it 'loads the kotlin column from the first existing candidate path' do
      Dir.mktmpdir do |dir|
        path = File.join(dir, 'font_weight_mapping.json')
        File.write(path, JSON.generate('weights' => { 'bold' => { 'kotlin' => 'FontWeight.CustomBold' } }))
        described_class.weight_mapping_candidates = [path]

        expect(described_class.weight_mapping['bold']).to eq('FontWeight.CustomBold')
      end
    end

    it 'prefers an earlier candidate over a later one' do
      Dir.mktmpdir do |dir|
        first = File.join(dir, 'first.json')
        second = File.join(dir, 'second.json')
        File.write(first, JSON.generate('weights' => { 'bold' => { 'kotlin' => 'FontWeight.First' } }))
        File.write(second, JSON.generate('weights' => { 'bold' => { 'kotlin' => 'FontWeight.Second' } }))
        described_class.weight_mapping_candidates = [first, second]

        expect(described_class.weight_mapping['bold']).to eq('FontWeight.First')
      end
    end

    it 'falls back to the built-in full table (medium included) when no file resolves' do
      described_class.weight_mapping_candidates = ['/nonexistent/font_weight_mapping.json']

      mapping = described_class.weight_mapping
      expect(mapping['medium']).to eq('FontWeight.Medium')
      expect(mapping['semibold']).to eq('FontWeight.SemiBold')
      expect(mapping['bold']).to eq('FontWeight.Bold')
    end

    it 'falls back to the built-in table when the file has an empty weights map' do
      Dir.mktmpdir do |dir|
        path = File.join(dir, 'font_weight_mapping.json')
        File.write(path, JSON.generate('weights' => {}))
        described_class.weight_mapping_candidates = [path]

        expect(described_class.weight_mapping['bold']).to eq('FontWeight.Bold')
      end
    end

    it 'falls back to the built-in table when the file is malformed JSON' do
      Dir.mktmpdir do |dir|
        path = File.join(dir, 'font_weight_mapping.json')
        File.write(path, 'not json {')
        described_class.weight_mapping_candidates = [path]

        expect(described_class.weight_mapping['bold']).to eq('FontWeight.Bold')
      end
    end
  end

  describe '.weight_literal_for' do
    it 'returns FontWeight literal for known weight string' do
      expect(described_class.weight_literal_for('bold')).to eq('FontWeight.Bold')
      expect(described_class.weight_literal_for('SemiBold')).to eq('FontWeight.SemiBold')
    end

    it 'maps the legacy "normal" alias onto regular' do
      expect(described_class.weight_literal_for('normal')).to eq('FontWeight.Normal')
    end

    it 'maps the legacy "extralight" alias onto ultraLight' do
      expect(described_class.weight_literal_for('extralight')).to eq('FontWeight.ExtraLight')
    end

    it 'returns nil for binding expressions' do
      expect(described_class.weight_literal_for('@{boldness}')).to be_nil
    end

    it 'returns nil for nil input' do
      expect(described_class.weight_literal_for(nil)).to be_nil
    end

    it 'falls back to FontWeight.Normal with a warning for unknown values' do
      expect { described_class.weight_literal_for('superduper') }.to output(/Unknown font weight/).to_stderr
      expect(described_class.weight_literal_for('superduper')).to eq('FontWeight.Normal')
    end
  end

  describe '.weight_name?' do
    it 'detects shared-mapping keys' do
      expect(described_class.weight_name?('bold')).to be true
      expect(described_class.weight_name?('semibold')).to be true
    end

    it 'detects legacy aliases' do
      expect(described_class.weight_name?('normal')).to be true
    end

    it 'returns false for arbitrary family names' do
      expect(described_class.weight_name?('Roboto-Regular')).to be false
    end

    it 'returns false for binding expressions' do
      expect(described_class.weight_name?('@{whatever}')).to be false
    end

    it 'returns false for nil' do
      expect(described_class.weight_name?(nil)).to be false
    end
  end

  describe '.build_font_spec_args' do
    it 'returns "null" placeholders when no font attrs are present' do
      args = described_class.build_font_spec_args({})
      expect(args[:family]).to eq('null')
      expect(args[:weight]).to eq('null')
      expect(args[:size]).to eq('null')
      expect(args[:italic]).to eq('false')
      expect(args[:has_any]).to be false
    end

    it 'extracts fontFamily as a quoted Kotlin string literal' do
      args = described_class.build_font_spec_args({ 'fontFamily' => 'Inter' })
      expect(args[:family]).to eq('"Inter"')
      expect(args[:has_any]).to be true
    end

    it 'extracts font (weight) into FontSpec.weight' do
      args = described_class.build_font_spec_args({ 'font' => 'bold' })
      expect(args[:weight]).to eq('FontWeight.Bold')
      expect(args[:family]).to eq('null')
    end

    it 'extracts fontSize into FontSpec.size as .sp literal' do
      args = described_class.build_font_spec_args({ 'fontSize' => 18 })
      expect(args[:size]).to eq('18.sp')
    end

    it 'treats font (custom family name) as FontSpec.family' do
      args = described_class.build_font_spec_args({ 'font' => 'Roboto-Regular' })
      expect(args[:family]).to eq('"Roboto-Regular"')
      expect(args[:weight]).to eq('null')
    end

    it 'treats fontFamily binding as a data.* expression' do
      args = described_class.build_font_spec_args({ 'fontFamily' => '@{customFamily}' })
      expect(args[:family]).to eq('data.customFamily')
    end

    it 'treats font binding as inline if-expression for weight' do
      args = described_class.build_font_spec_args({ 'font' => '@{weightVar}' })
      expect(args[:weight]).to include('data.weightVar')
      expect(args[:weight]).to include('FontWeight.Bold')
    end

    it 'records :font_weight import when weight is emitted' do
      imports = Set.new
      described_class.build_font_spec_args({ 'fontWeight' => 'medium' }, imports)
      expect(imports).to include(:font_weight)
    end
  end

  describe '.emit_resolve_block' do
    it 'emits the FontSpec(...) constructor call with the requested fields' do
      args = {
        family: '"Inter"',
        weight: 'FontWeight.Bold',
        size: '16.sp',
        italic: 'false',
        has_any: true
      }
      block = described_class.emit_resolve_block('resolved_text1', args, 0, Set.new)
      expect(block).to include('val resolved_text1 = Configuration.Font.resolve(FontSpec(')
      expect(block).to include('family = "Inter",')
      expect(block).to include('weight = FontWeight.Bold,')
      expect(block).to include('size = 16.sp,')
      expect(block).to include('italic = false')
      expect(block).to include('))')
    end

    it 'records :configuration and :font_spec imports' do
      imports = Set.new
      args = described_class.build_font_spec_args({ 'fontSize' => 14 }, imports)
      described_class.emit_resolve_block('resolved_text1', args, 0, imports)
      expect(imports).to include(:configuration)
      expect(imports).to include(:font_spec)
    end
  end

  describe '.weight_literal_for (static numeric)' do
    # The SSoT declares fontWeight ["string", "number"] on all three
    # platforms, and a static 600 fell through the name table into
    # warn+Normal — ios drew SemiBold where android drew Normal (run 6
    # cross_effect fontWeight__600, ruled a cross-platform divergence to
    # fix). Numbers resolve through the SHARED table's css column first, so
    # the numeric vocabulary cannot drift from the name one.
    it 'resolves a table number through the shared css column' do
      expect(described_class.weight_literal_for(600)).to eq('FontWeight.SemiBold')
      expect(described_class.weight_literal_for('500')).to eq('FontWeight.Medium')
      expect(described_class.weight_literal_for('100')).to eq('FontWeight.Thin')
    end

    it 'passes an in-range number outside the table straight to FontWeight(n)' do
      expect(described_class.weight_literal_for(450)).to eq('FontWeight(450)')
    end

    it 'drops an out-of-range number to Normal like an unknown name' do
      expect(described_class.weight_literal_for(0)).to eq('FontWeight.Normal')
      expect(described_class.weight_literal_for(1200)).to eq('FontWeight.Normal')
    end
  end

  describe '.weight_expression (bound numeric)' do
    # `FontWeight(n)` throws outside [1, 1000], and a non-nullable Int
    # property composes first with its default 0 — the unguarded emit took
    # the codegen host down for Button.fontWeight__binding (the one missing
    # screenshot of the 5th round). Out-of-range falls to 400, which is what
    # the fallback already meant; the dynamic path resolves weights through
    # a name table and cannot throw.
    before do
      allow(KjuiTools::Compose::Helpers::ResourceResolver)
        .to receive(:get_property_class).with('boundFontWeight').and_return('Int')
      allow(KjuiTools::Compose::Helpers::BindingExpression)
        .to receive(:property_nullable?).with('boundFontWeight').and_return(false)
    end

    it 'guards the runtime range instead of emitting a bare constructor' do
      expr = described_class.weight_expression('@{boundFontWeight}')
      expect(expr).to eq('FontWeight(data.boundFontWeight.let { if (it in 1..1000) it else 400 })')
    end
  end

  describe '.text_arg_lines' do
    it 'emits four destructured Text args with proper fallbacks' do
      lines = described_class.text_arg_lines('resolved_text7', 0, Set.new)
      expect(lines).to include('fontFamily = resolved_text7.family,')
      expect(lines).to include('fontWeight = resolved_text7.weight,')
      expect(lines).to include('fontSize = resolved_text7.size ?: TextUnit.Unspecified,')
      expect(lines).to include('fontStyle = resolved_text7.style ?: FontStyle.Normal,')
    end

    it 'records :font_style and :text_unit imports' do
      imports = Set.new
      described_class.text_arg_lines('resolved_text7', 0, imports)
      expect(imports).to include(:font_style)
      expect(imports).to include(:text_unit)
    end
  end

  describe '.style_arg_fragments' do
    it 'returns four key=value fragments without trailing commas' do
      fragments = described_class.style_arg_fragments('resolved_text2', Set.new)
      expect(fragments).to be_an(Array)
      expect(fragments.size).to eq(4)
      expect(fragments).to include('fontFamily = resolved_text2.family')
      expect(fragments).to include('fontWeight = resolved_text2.weight')
      expect(fragments).to include('fontSize = (resolved_text2.size ?: TextUnit.Unspecified)')
      expect(fragments).to include('fontStyle = (resolved_text2.style ?: FontStyle.Normal)')
    end
  end
end
