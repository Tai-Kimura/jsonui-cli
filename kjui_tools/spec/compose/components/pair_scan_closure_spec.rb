# frozen_string_literal: true

# 2026-07-31 pair-scan closure — Compose behaviours added when the
# component-aware coverage scan exposed silently-dropped attributes.
require_relative '../../spec_helper'
require 'compose/components/scrollview_component'
require 'compose/components/collection_component'
require 'compose/components/progress_component'
require 'compose/components/slider_component'
require 'compose/components/radio_component'
require 'compose/components/selectbox_component'
require 'compose/components/textfield_component'
require 'compose/helpers/resource_resolver'

RSpec.describe 'pair-scan closure (compose)' do
  before { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  it 'ScrollView paging: per-child items with a snap fling on the list state' do
    result = KjuiTools::Compose::Components::ScrollViewComponent.generate(
      { 'type' => 'ScrollView', 'id' => 'pager', 'paging' => true,
        'child' => [{ 'type' => 'View' }, { 'type' => 'View' }] },
      0, Set.new
    )
    expect(result[:code]).to include('val scrollPagingStatepager = rememberLazyListState()')
    expect(result[:code]).to include('flingBehavior = rememberSnapFlingBehavior(lazyListState = scrollPagingStatepager)')
    # children get their own item scopes (the wrapper), not one shared item
    expect(result[:code]).not_to include("item {")
    expect(result[:child_wrapper]).to eq(open: 'item {', close: '}')
  end

  it 'ScrollView without paging keeps the single shared item' do
    result = KjuiTools::Compose::Components::ScrollViewComponent.generate(
      { 'type' => 'ScrollView', 'child' => [{ 'type' => 'View' }] }, 0, Set.new
    )
    expect(result[:code]).to include('item {')
    expect(result[:child_wrapper]).to be_nil
  end

  it 'Collection: horizontalScroll flips the layout direction' do
    imports = Set.new
    code = KjuiTools::Compose::Components::CollectionComponent.generate(
      { 'type' => 'Collection', 'horizontalScroll' => true, 'items' => '@{rows}',
        'sections' => [] }, 0, imports
    )
    text = code.is_a?(Hash) ? code[:code] : code
    expect(text).to match(/LazyRow|LazyHorizontalGrid|HorizontalPager/)
  end

  it 'Progress: tintColor is the UIKit spelling of the indicator colour' do
    code = KjuiTools::Compose::Components::ProgressComponent.generate(
      { 'type' => 'Progress', 'progress' => 0.5, 'tintColor' => '#FF0000' }, 0, Set.new
    )
    expect(code).to include('color = Color(android.graphics.Color.parseColor("#FF0000"))')
  end

  it 'Slider: tintColor colours the thumb and active track; specific names win' do
    code = KjuiTools::Compose::Components::SliderComponent.generate(
      { 'type' => 'Slider', 'tintColor' => '#00FF00' }, 0, Set.new
    )
    expect(code).to include('thumbColor =')
    expect(code).to include('activeTrackColor =')

    specific = KjuiTools::Compose::Components::SliderComponent.generate(
      { 'type' => 'Slider', 'tintColor' => '#00FF00', 'thumbTintColor' => '#0000FF' }, 0, Set.new
    )
    expect(specific).to match(/thumbColor = .*0000FF/)
  end

  it 'Radio: label is the row text alias, uncheckedColor maps to unselectedColor' do
    code = KjuiTools::Compose::Components::RadioComponent.generate(
      { 'type' => 'Radio', 'label' => 'Pick me', 'group' => 'g1',
        'uncheckedColor' => '#123456' }, 0, Set.new
    )
    expect(code).to include('Pick me')
    expect(code).to include('unselectedColor =')
  end

  it 'SelectBox: selectedValue is the selectedItem alias; labelAttributes wins the label styling' do
    code = KjuiTools::Compose::Components::SelectBoxComponent.generate(
      { 'type' => 'SelectBox', 'items' => %w[A B],
        'selectedValue' => '@{picked}', 'fontColor' => '#111111', 'fontSize' => 14,
        'labelAttributes' => { 'fontColor' => '#222222', 'fontSize' => 18 } }, 0, Set.new
    )
    expect(code).to include('value = data.picked')
    expect(code).to match(/textColor = .*222222/)
    expect(code).to include('fontSize = 18')
  end

  it 'TextField: tintColor forwards to CustomTextField cursorColor' do
    code = KjuiTools::Compose::Components::TextFieldComponent.generate(
      { 'type' => 'TextField', 'id' => 'field', 'text' => '@{value}',
        'tintColor' => '#ABCDEF' }, 0, Set.new
    )
    expect(code).to match(/cursorColor = .*ABCDEF/)
  end
end

# Group-2 backlog closure (2026-07-31).
RSpec.describe 'backlog closure group 2 (compose)' do
  before { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  it 'GradientView: locations selects the colorStops overload' do
    require 'compose/components/gradientview_component'
    code = KjuiTools::Compose::Components::GradientviewComponent.generate(
      { 'type' => 'GradientView', 'colors' => ['#000000', '#FFFFFF'],
        'locations' => [0.0, 0.7] }, 0, Set.new
    )
    text = code.is_a?(Hash) ? code[:code] : code
    expect(text).to include('0.0f to Color(')
    expect(text).to include('0.7f to Color(')

    plain = KjuiTools::Compose::Components::GradientviewComponent.generate(
      { 'type' => 'GradientView', 'colors' => ['#000000', '#FFFFFF'] }, 0, Set.new
    )
    ptext = plain.is_a?(Hash) ? plain[:code] : plain
    expect(ptext).to include('listOf(')
  end

  it 'Image/NetworkImage: loadingImage joins the fallback/placeholder chain' do
    require 'compose/components/image_component'
    require 'compose/components/networkimage_component'
    img = KjuiTools::Compose::Components::ImageComponent.generate(
      { 'type' => 'Image', 'loadingImage' => 'spinner_art' }, 0, Set.new
    )
    itext = img.is_a?(Hash) ? img[:code] : img
    expect(itext).to include('spinner_art')

    net = KjuiTools::Compose::Components::NetworkImageComponent.generate(
      { 'type' => 'NetworkImage', 'src' => 'https://x/y.png', 'loadingImage' => 'loading_art' }, 0, Set.new
    )
    expect(net).to include('loading_art')
  end

  it 'View.highlighted swaps the background (literal pins, binding is conditional)' do
    mods = KjuiTools::Compose::Helpers::ModifierBuilder.build_background(
      { 'highlighted' => true, 'highlightBackground' => '#FFEEDD', 'background' => '#FFFFFF' }, Set.new
    )
    expect(mods.join).to match(/background\(Color\(.*FFEEDD.*\)\)/)

    bound = KjuiTools::Compose::Helpers::ModifierBuilder.build_background(
      { 'highlighted' => '@{isPressed}', 'highlightBackground' => '#FFEEDD', 'background' => '#FFFFFF' }, Set.new
    )
    expect(bound.join).to include('if (data.isPressed)')

    no_base = KjuiTools::Compose::Helpers::ModifierBuilder.build_background(
      { 'highlighted' => '@{isPressed}', 'highlightBackground' => '#FFEEDD' }, Set.new
    )
    expect(no_base.join).to include('else Color.Transparent')
  end

  it 'Segment: legacy valueChange selector calls the named method' do
    require 'compose/components/segment_component'
    code = KjuiTools::Compose::Components::SegmentComponent.generate(
      { 'type' => 'Segment', 'items' => %w[A B], 'valueChange' => 'on_tab_change' }, 0, Set.new
    )
    text = code.is_a?(Hash) ? code[:code] : code
    expect(text).to include('onTabChange')
  end
end
