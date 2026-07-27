# frozen_string_literal: true

require 'spec_helper'
require 'tmpdir'
require_relative '../../lib/swiftui/view_updater'

# Screen marker emission (screen-identity track, Phase 4).
#
# The static path has no conformance coverage on iOS — the ConformanceHost is
# Dynamic-mode only — so the generated string IS the regression test.
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

  describe 'screen marker' do
    it 'applies the marker to the outer Group so both rendering modes carry it' do
      Dir.mktmpdir do |dir|
        path = write_stub(dir)
        updater.update_generated_body(path, 'Text("base")', screen_marker: '__screen_home')
        content = File.read(path)

        expect(content).to include('.jsonUIScreenMarker("__screen_home")')

        # The marker must sit OUTSIDE the DEBUG dynamic/static switch: a
        # mode-dependent marker would split test results by rendering mode.
        marker_index = content.index('.jsonUIScreenMarker')
        static_index = content.index('private var generatedBody')
        expect(marker_index).to be < static_index
      end
    end

    it 'names the minimum library version so a stale pin fails loudly' do
      Dir.mktmpdir do |dir|
        path = write_stub(dir)
        updater.update_generated_body(path, 'Text("base")', screen_marker: '__screen_home')

        expect(File.read(path)).to include(
          "// Requires SwiftJsonUI >= #{described_class::SCREEN_MARKER_MIN_LIBRARY_VERSION} (screen marker)"
        )
      end
    end

    it 'emits nothing for a non-screen layout' do
      Dir.mktmpdir do |dir|
        path = write_stub(dir)
        updater.update_generated_body(path, 'Text("base")')

        expect(File.read(path)).not_to include('jsonUIScreenMarker')
      end
    end

    it 'leaves unmarked output byte-identical to the pre-marker generator' do
      # Separate directories so both files can carry the SAME struct name —
      # the updater keys off `struct <Name>GeneratedView: View`.
      Dir.mktmpdir do |a|
        Dir.mktmpdir do |b|
          without = write_stub(a)
          explicit_nil = write_stub(b)

          updater.update_generated_body(without, 'Text("base")')
          updater.update_generated_body(explicit_nil, 'Text("base")', screen_marker: nil)

          expect(File.read(explicit_nil)).to eq(File.read(without))
        end
      end
    end

    it 'is idempotent — regenerating twice produces the same file' do
      Dir.mktmpdir do |dir|
        path = write_stub(dir)
        updater.update_generated_body(path, 'Text("base")', screen_marker: '__screen_home')
        first = File.read(path)
        updater.update_generated_body(path, 'Text("base")', screen_marker: '__screen_home')

        expect(File.read(path)).to eq(first)
      end
    end
  end
end
