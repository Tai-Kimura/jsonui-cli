# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/react_generator'
require 'react/converters/view_converter'
require 'react/converters/button_converter'

# Regressions: rjui-view-flexwrap-attribute-dropped
#              rjui-button-image-attribute-dropped
#
# Both attributes were present in the generated attribute tables — so the
# unknown-attribute validation passed them — and no converter ever read them.
# The build stayed at 0 warnings while the layout silently lost a wrap and a
# button lost its only visible content.
RSpec.describe 'attributes that were defined but never emitted' do
  let(:config) { { 'use_tailwind' => true } }

  def view(json)
    RjuiTools::React::Converters::ViewConverter.new(json, config).convert_node
  end

  def button(json)
    RjuiTools::React::Converters::ButtonConverter.new(
      { 'type' => 'Button' }.merge(json), config
    ).convert_node
  end

  describe 'View#flexWrap' do
    it 'emits flex-wrap' do
      expect(view('type' => 'View', 'orientation' => 'horizontal',
                  'flexWrap' => 'wrap')).to include('flex-wrap')
    end

    it 'emits flex-nowrap' do
      expect(view('type' => 'View', 'flexWrap' => 'nowrap')).to include('flex-nowrap')
    end

    it 'emits flex-wrap-reverse' do
      expect(view('type' => 'View', 'flexWrap' => 'wrap-reverse'))
        .to include('flex-wrap-reverse')
    end

    it 'leaves a View without the attribute untouched' do
      expect(view('type' => 'View', 'orientation' => 'horizontal'))
        .not_to include('flex-wrap')
    end

    it 'honours a responsive override with the breakpoint prefix' do
      jsx = view('type' => 'View', 'orientation' => 'horizontal',
                 'flexWrap' => 'nowrap',
                 'responsive' => { 'compact' => { 'flexWrap' => 'wrap' } })
      expect(jsx).to include('flex-nowrap')
      expect(jsx).to match(/max-md:flex-wrap/)
    end
  end

  describe 'Button#image' do
    it 'renders the icon instead of an empty button' do
      jsx = button('image' => 'menu', 'width' => 40, 'height' => 40)
      expect(jsx).to include('/images/menu.svg')
      # The reported symptom, verbatim: a button with nothing between the tags.
      expect(jsx).not_to match(/<button[^>]*><\/button>/)
    end

    it 'lays the icon out inside the button box' do
      expect(button('image' => 'menu')).to include('inline-flex items-center justify-center')
    end

    it 'gives an icon-only button an accessible name' do
      # A <button> whose only child is alt="" has no accessible name at all.
      expect(button('image' => 'menu_open')).to include('alt="menu open"')
    end

    it 'treats the icon as decorative when a label is present' do
      jsx = button('image' => 'menu', 'text' => 'Menu')
      expect(jsx).to include('alt=""')
      expect(jsx).to include('Menu')
      expect(jsx).to include('gap-2')
    end

    it 'masks a tinted icon so fontColor actually colours it' do
      # An <img> cannot take the button's colour: a currentColor SVG on a
      # dark toolbar would stay black.
      jsx = button('image' => 'menu', 'fontColor' => '#FFFFFF')
      expect(jsx).to include('bg-current')
      expect(jsx).to include('maskImage')
      expect(jsx).to include('WebkitMaskImage')
      expect(jsx).not_to include('<img')
    end

    it 'resolves a bound image through the binding, not the string table' do
      jsx = button('image' => '@{iconName}')
      expect(jsx).to include('/images/${data.iconName}')
    end

    it 'leaves a text-only button exactly as before' do
      jsx = button('text' => 'Save')
      expect(jsx).not_to include('<img')
      expect(jsx).not_to include('inline-flex')
    end
  end
end
