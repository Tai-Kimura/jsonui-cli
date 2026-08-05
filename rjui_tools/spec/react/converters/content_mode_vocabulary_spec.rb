# frozen_string_literal: true

require 'json'
require_relative '../../spec_helper'
require 'react/converters/image_converter'
require 'react/converters/network_image_converter'

# `contentMode` used to be answered by FOUR tables — ImageConverter's `case`,
# NetworkImageConverter's class map, its prop map, and the bound path's — and no
# two accepted the same spellings. `aspect_fit` was only in the first;
# `centerCrop` / `fitCenter` / `fitXY` only in the others, which were also
# case-SENSITIVE, so a lowercase `aspectfill` fell through to an
# `object-#{value}` fallback and emitted a class that matches nothing. The same
# declaration got a different answer on `<img>` than on `<NetworkImage>`.
#
# These pins are driven from the SSoT DECLARATION rather than from the table, so
# a value that attribute_definitions.json offers an author can never again be a
# value the converters do not answer.
RSpec.describe 'contentMode vocabulary' do
  # spec/react/converters -> react -> spec -> rjui_tools -> repo root.
  # The vendored per-tool copy (`rjui_tools/shared/core`) is checked first so a
  # deployed tool tree still resolves, mirroring FontSpecHelper's lookup.
  DEFINITIONS = %w[
    ../../../shared/core/attribute_definitions.json
    ../../../../shared/core/attribute_definitions.json
  ].map { |rel| File.expand_path(rel, __dir__) }.find { |path| File.exist?(path) }

  let(:config) { { 'use_tailwind' => true } }

  def declared_enum(component)
    defs = JSON.parse(File.read(DEFINITIONS))
    section = defs.fetch(component)
    (section['attributes'] || section).fetch('contentMode').fetch('enum')
  end

  # The CSS the canon asks for, per shared/core/attribute_semantics.json:
  # fill = stretch (scaleToFill's synonym), AspectFill is the crop, fit is the
  # default. Written out here rather than read from the converter's table —
  # a pin that reads the implementation proves nothing.
  EXPECTED_FIT = {
    'fit' => 'contain', 'aspectfit' => 'contain', 'aspect_fit' => 'contain',
    'scaleaspectfit' => 'contain', 'fitcenter' => 'contain',
    'fill' => 'fill', 'scaletofill' => 'fill', 'scale_to_fill' => 'fill', 'fitxy' => 'fill',
    'aspectfill' => 'cover', 'aspect_fill' => 'cover',
    'scaleaspectfill' => 'cover', 'centercrop' => 'cover',
    'center' => 'none', 'top' => 'none', 'bottom' => 'none',
    'left' => 'none', 'right' => 'none'
  }.freeze

  it 'has a definitions file to read' do
    expect(DEFINITIONS).not_to be_nil
  end

  describe 'every DECLARED value reaches the right object-fit' do
    it 'Image — <img> takes the class' do
      declared_enum('Image').each do |value|
        out = RjuiTools::React::Converters::ImageConverter.new(
          { 'type' => 'Image', 'src' => 'a.png', 'contentMode' => value }, config
        ).convert_node(2)
        want = EXPECTED_FIT.fetch(value.downcase)
        expect(out).to include("object-#{want}"), "Image contentMode: #{value.inspect}"
      end
    end

    it 'NetworkImage — the component takes the prop, and the class agrees with it' do
      declared_enum('NetworkImage').each do |value|
        out = RjuiTools::React::Converters::NetworkImageConverter.new(
          { 'type' => 'NetworkImage', 'src' => 'a.png', 'contentMode' => value }, config
        ).convert_node(2)
        want = EXPECTED_FIT.fetch(value.downcase)
        expect(out).to include("contentMode=\"#{want}\""), "NetworkImage prop: #{value.inspect}"
        expect(out).to include("object-#{want}"), "NetworkImage class: #{value.inspect}"
      end
    end
  end

  # The bug the unification closes: the same declaration answered differently
  # depending on which component it was written on.
  describe 'the two components answer a shared declaration the same way' do
    it 'agrees on every value both of them declare' do
      shared = declared_enum('Image') & declared_enum('NetworkImage')
      expect(shared).not_to be_empty

      shared.each do |value|
        img = RjuiTools::React::Converters::ImageConverter.new(
          { 'type' => 'Image', 'src' => 'a.png', 'contentMode' => value }, config
        ).convert_node(2)[/object-[a-z]+/]
        net = RjuiTools::React::Converters::NetworkImageConverter.new(
          { 'type' => 'NetworkImage', 'src' => 'a.png', 'contentMode' => value }, config
        ).convert_node(2)[/object-[a-z]+/]
        expect(img).to eq(net), "#{value.inspect} differs: <img> #{img} vs <NetworkImage> #{net}"
      end
    end

    # The iOS/Android long forms are not in either declared enum, but layouts
    # written against those runtimes carry them and both components used to
    # accept a DIFFERENT subset.
    it 'agrees on the tolerated iOS/Android long forms too' do
      %w[scaleAspectFit scaleAspectFill scaleToFill centerCrop fitCenter fitXY aspect_fit].each do |value|
        img = RjuiTools::React::Converters::ImageConverter.new(
          { 'type' => 'Image', 'src' => 'a.png', 'contentMode' => value }, config
        ).convert_node(2)[/object-[a-z]+/]
        net = RjuiTools::React::Converters::NetworkImageConverter.new(
          { 'type' => 'NetworkImage', 'src' => 'a.png', 'contentMode' => value }, config
        ).convert_node(2)[/object-[a-z]+/]
        want = "object-#{EXPECTED_FIT.fetch(value.downcase)}"
        expect(img).to eq(want), "<img> #{value.inspect}"
        expect(net).to eq(want), "<NetworkImage> #{value.inspect}"
      end
    end

    it 'is case-insensitive on both — the maps used to be case-sensitive' do
      %w[AspectFill aspectfill ASPECTFILL].each do |value|
        net = RjuiTools::React::Converters::NetworkImageConverter.new(
          { 'type' => 'NetworkImage', 'src' => 'a.png', 'contentMode' => value }, config
        ).convert_node(2)
        expect(net).to include('object-cover'), value
        expect(net).not_to match(/object-[A-Za-z]*[A-Z]/), "#{value}: interpolated the raw value"
      end
    end
  end

  describe 'an unrecognised value' do
    it 'falls back to the declared default rather than becoming a class name' do
      out = RjuiTools::React::Converters::NetworkImageConverter.new(
        { 'type' => 'NetworkImage', 'src' => 'a.png', 'contentMode' => 'nonsense' }, config
      ).convert_node(2)
      expect(out).to include('object-contain')
      expect(out).not_to include('object-nonsense')
      expect(out).to include('contentMode="contain"')
    end
  end
end
