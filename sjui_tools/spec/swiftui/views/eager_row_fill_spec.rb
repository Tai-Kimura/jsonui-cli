# frozen_string_literal: true

require 'swiftui/views/collection_converter'
require_relative '../../support/emitted_swift'

# A horizontal eager Collection fills a declared height, as a lazy one does.
# A horizontal ScrollView is as tall as its content, and an HStack is its
# cells' height where a LazyHStack takes the height it is offered: until
# jsonui-cli 1.9.0 an eager row in a 40pt frame was 28pt — its cells' — and a
# drag in the 12pt below them scrolled nothing, where the lazy row was 40
# (measured 2026-09-27 on the ConformanceHost, generated and Dynamic alike).
# CollectionStackView(fillsCrossAxis:) (SwiftJsonUI 10.29.0) fills the row;
# sjui passes it where the height is declared and the mode can be eager. A
# wrapContent height keeps the row its cells' height.
#
# The drawn arm is EagerRowFillProbeUITests in SwiftJsonUI's ConformanceHost.
RSpec.describe SjuiTools::SwiftUI::Views::CollectionConverter do
  include EmittedSwift

  before(:all) { described_class.superclass.validation_enabled = false }
  after(:all) { described_class.superclass.validation_enabled = true }

  def emit(extra)
    described_class.new({ 'type' => 'Collection', 'id' => 'list', 'layout' => 'horizontal', 'width' => 'matchParent',
                          'items' => '@{rows}', 'sections' => [{ 'cell' => 'ACell' }] }.merge(extra).compact).convert.to_s
  end

  it 'a horizontal eager row of a fixed or matchParent height fills it' do
    expect(emit('lazy' => 'eager', 'height' => 40)).to include('fillsCrossAxis: true')
    expect(emit('lazy' => 'eager', 'height' => 'matchParent')).to include('fillsCrossAxis: true')
  end

  it 'a bound mode can be eager: the row is told to fill' do
    expect(emit('lazy' => '@{mode}', 'height' => 40)).to include('fillsCrossAxis: true')
  end

  it 'control: a wrapContent or undeclared height, a lazy or none row, and a vertical column are as before' do
    expect(emit('lazy' => 'eager', 'height' => 'wrapContent')).not_to include('fillsCrossAxis')
    expect(emit('lazy' => 'eager', 'height' => nil)).not_to include('fillsCrossAxis')
    expect(emit('lazy' => 'lazy', 'height' => 40)).not_to include('fillsCrossAxis')
    expect(emit('height' => 40)).not_to include('fillsCrossAxis')
    expect(emit('lazy' => 'none', 'height' => 40)).not_to include('fillsCrossAxis')
    expect(emit('layout' => 'vertical', 'lazy' => 'eager', 'height' => 40)).not_to include('fillsCrossAxis')
  end

  it 'type-checks the argument against the library signature', :swift_compile do
    stubs = EmittedSwift::COLLECTION_DATA_SOURCE_STUB + EmittedSwift::COLLECTION_STACK_VIEW_STUB + cell_view_stub('ACellView')
    codes = [emit('lazy' => 'eager', 'height' => 40), emit('lazy' => 'eager', 'height' => 'matchParent')]
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: ['var rows: CollectionDataSource? = nil'], stubs: stubs))
      .to compile_as_swift
  end
end
