# frozen_string_literal: true

require 'spec_helper'
require 'tmpdir'
require_relative '../../lib/swiftui/view_updater'

RSpec.describe SjuiTools::SwiftUI::ViewUpdater do
  let(:updater) { described_class.new }

  def write_stub(dir, struct: 'HomeGeneratedView', data: 'HomeData')
    path = File.join(dir, "#{struct}.swift")
    File.write(path, <<~SWIFT)
      import SwiftUI

      struct #{struct}: View {
          @SwiftUI.Binding var data: #{data}

          var body: some View {
              // >>> GENERATED_CODE_START
              Text("Placeholder")
              // >>> GENERATED_CODE_END
          }
      }
    SWIFT
    path
  end

  describe 'variant dispatch on the base GeneratedView' do
    it 'emits a size-class dispatch with the base body in the uncovered branch' do
      Dir.mktmpdir do |dir|
        path = write_stub(dir)
        updater.update_generated_body(
          path, 'Text("base")',
          variant_dispatch: { 'regular' => 'HomeRegularVariantGeneratedView' },
          force_typed_view_model: true
        )
        content = File.read(path)

        expect(content).to include('@Environment(\.horizontalSizeClass) private var horizontalSizeClass')
        expect(content).to include('if horizontalSizeClass == .regular {')
        expect(content).to include('HomeRegularVariantGeneratedView(data: $data, viewModel: viewModel)')
        expect(content).to include('Text("base")')
        expect(content).to include('@ObservedObject var viewModel: HomeViewModel')
      end
    end

    it 'folds @medium into the compact branch with @compact taking precedence' do
      Dir.mktmpdir do |dir|
        path = write_stub(dir)
        updater.update_generated_body(
          path, 'Text("base")',
          variant_dispatch: {
            'compact' => 'HomeCompactVariantGeneratedView',
            'medium' => 'HomeMediumVariantGeneratedView',
          },
          force_typed_view_model: true
        )
        content = File.read(path)

        expect(content).to include('HomeCompactVariantGeneratedView(data: $data, viewModel: viewModel)')
        expect(content).not_to include('HomeMediumVariantGeneratedView(')
        # regular branch (no @regular) falls back to the base body
        expect(content).to include('Text("base")')
      end
    end

    it 'drops the base body when every size class resolves to a variant' do
      Dir.mktmpdir do |dir|
        path = write_stub(dir)
        updater.update_generated_body(
          path, 'Text("base")',
          variant_dispatch: {
            'regular' => 'HomeRegularVariantGeneratedView',
            'compact' => 'HomeCompactVariantGeneratedView',
          },
          force_typed_view_model: true
        )
        content = File.read(path)

        expect(content).not_to include('Text("base")')
        expect(content).to include('HomeRegularVariantGeneratedView(data: $data, viewModel: viewModel)')
        expect(content).to include('HomeCompactVariantGeneratedView(data: $data, viewModel: viewModel)')
      end
    end

    it 'does not duplicate an existing horizontalSizeClass declaration' do
      Dir.mktmpdir do |dir|
        path = write_stub(dir)
        updater.update_generated_body(
          path, 'Text("base")',
          state_variables: ['@Environment(\.horizontalSizeClass) private var horizontalSizeClass'],
          variant_dispatch: { 'regular' => 'HomeRegularVariantGeneratedView' },
          force_typed_view_model: true
        )
        content = File.read(path)
        expect(content.scan('horizontalSizeClass) private var').length).to eq(1)
      end
    end
  end

  describe 'variant GeneratedView emission' do
    it 'keeps the base Data type and the overridden ViewModel type and source name' do
      Dir.mktmpdir do |dir|
        path = write_stub(dir, struct: 'HomeRegularVariantGeneratedView', data: 'HomeData')
        updater.update_generated_body(
          path, 'Text("regular tree")',
          force_typed_view_model: true,
          view_model_type: 'HomeViewModel',
          source_name: 'home@regular'
        )
        content = File.read(path)

        expect(content).to include('struct HomeRegularVariantGeneratedView: View')
        expect(content).to include('@SwiftUI.Binding var data: HomeData')
        expect(content).to include('@ObservedObject var viewModel: HomeViewModel')
        expect(content).to include('jsonName: "home@regular"')
        expect(content).to include('home@regular.json')
        expect(content).not_to include('HomeRegularVariantViewModel')
      end
    end
  end

  describe 'non-variant screens' do
    it 'emits byte-identical output with and without the new kwargs left at defaults' do
      Dir.mktmpdir do |dir|
        a = write_stub(dir, struct: 'AGeneratedView', data: 'AData')
        b = write_stub(dir, struct: 'BGeneratedView', data: 'BData')
        updater.update_generated_body(a, 'Text("x")')
        updater.update_generated_body(
          b, 'Text("x")',
          variant_dispatch: nil, force_typed_view_model: false,
          view_model_type: nil, source_name: nil
        )
        normalize = ->(s) { s.gsub(/AGeneratedView|AData|"a"|a_view|a\.json/, 'X').gsub(/BGeneratedView|BData|"b"|b_view|b\.json/, 'X') }
        expect(normalize.call(File.read(a))).to eq(normalize.call(File.read(b)))
      end
    end
  end
end
