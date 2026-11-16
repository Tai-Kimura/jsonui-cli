# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/react_generator'

# Responsive variant-file mechanism (home@regular.json → media-query
# dispatch in the base component + <Base><Class>Variant component),
# 06 variant-file track / 06a-design.md D5.
RSpec.describe RjuiTools::React::ReactGenerator do
  let(:config) { { 'use_tailwind' => true, 'typescript' => true } }
  let(:generator) { described_class.new(config) }

  let(:base_json) do
    {
      'type' => 'View',
      'id' => 'root',
      'data' => [{ 'name' => 'title', 'class' => 'String', 'defaultValue' => 'base' }],
      'child' => [{ 'type' => 'Label', 'id' => 'which', 'text' => '@{title}' }]
    }
  end
  let(:variant_json) do
    {
      'type' => 'View',
      'id' => 'root',
      'child' => [{ 'type' => 'Label', 'id' => 'which', 'text' => '@{title}' }]
    }
  end

  describe 'base component with variants' do
    it 'emits media-query dispatch and variant import' do
      output = generator.generate('Home', base_json,
                                  variants: { 'regular' => 'HomeRegularVariant' })

      expect(output).to include('"use client";')
      expect(output).to include("import { useMediaQuery } from '@/hooks/useMediaQuery';")
      expect(output).to include("import HomeRegularVariant from '@/generated/components/HomeRegularVariant';")
      expect(output).to include("const jsonuiMinLg = useMediaQuery('(min-width: 1024px)');")
      expect(output).to include('if (jsonuiMinLg) { return <HomeRegularVariant data={data} />; }')
      # base JSX still present (compact/medium tiers fall through)
      expect(output).to include('data.title')
    end

    it 'uses exact tier guards for a medium-only variant' do
      output = generator.generate('Home', base_json,
                                  variants: { 'medium' => 'HomeMediumVariant' })

      expect(output).to include("const jsonuiMinMd = useMediaQuery('(min-width: 768px)');")
      expect(output).to include("const jsonuiMinLg = useMediaQuery('(min-width: 1024px)');")
      expect(output).to include('if (jsonuiMinMd && !jsonuiMinLg) { return <HomeMediumVariant data={data} />; }')
    end

    it 'nests variant imports under the base subdir' do
      output = generator.generate('Home', base_json, subdir: 'shop',
                                  variants: { 'compact' => 'HomeCompactVariant' })
      expect(output).to include("import HomeCompactVariant from '@/generated/components/shop/HomeCompactVariant';")
      expect(output).to include('if (!jsonuiMinMd) { return <HomeCompactVariant data={data} />; }')
    end
  end

  describe 'variant component' do
    it 'keeps the base Data type, namespace and source marker' do
      output = generator.generate('HomeRegularVariant', variant_json,
                                  data_type: 'Home',
                                  source_rel: 'Layouts/home@regular.json',
                                  namespace_stem: 'home')

      expect(output).to include('export const HomeRegularVariant = ')
      expect(output).to include("import { type HomeData, createHomeData } from '@/generated/data/HomeData';")
      expect(output).to include('interface HomeRegularVariantProps {')
      expect(output).to include('data?: Partial<HomeData>;')
      expect(output).to include('const data: HomeData = { ...createHomeData(), ...dataProp };')
      expect(output).to include('Layouts/home@regular.json')
      expect(output).not_to include('HomeRegularVariantData')
    end
  end

  describe 'screens without variants' do
    it 'emits no dispatch machinery' do
      output = generator.generate('Home', base_json)
      expect(output).not_to include('useMediaQuery')
      expect(output).not_to include('jsonuiMin')
      expect(output).not_to include('Variant')
    end
  end
end
