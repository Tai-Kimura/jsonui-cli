# frozen_string_literal: true

require 'swiftui/view_updater'
require 'json'
require 'fileutils'

RSpec.describe SjuiTools::SwiftUI::ViewUpdater, 'responsive support' do
  let(:updater) { described_class.new }
  # Per-example directory, not a fixed name shared by concurrent rspec
  # processes (see converter_generator_spec).
  let(:temp_dir) { File.realpath(Dir.mktmpdir('view_updater_responsive_test')) }

  before do
    FileUtils.mkdir_p(temp_dir)
  end

  after do
    FileUtils.rm_rf(temp_dir)
  end

  describe '#update_generated_body with responsive_functions' do
    let(:swift_file_path) { File.join(temp_dir, 'ResponsiveTestGeneratedView.swift') }

    before do
      content = <<~SWIFT
        import SwiftUI

        struct ResponsiveTestGeneratedView: View {
            @Binding var data: ResponsiveTestData

            var body: some View {
                Text("Old content")
            }
        }
      SWIFT
      File.write(swift_file_path, content)
    end

    it 'includes responsive functions in the generated file' do
      responsive_func = <<~FUNC
    @ViewBuilder private func responsive0<Content: View>(
        @ViewBuilder content: () -> Content
    ) -> some View {
        if horizontalSizeClass == .regular {
            HStack(alignment: .leading, spacing: 24) {
                content()
            }
        } else {
            VStack(alignment: .leading, spacing: 8) {
                content()
            }
        }
    }
      FUNC

      updater.update_generated_body(
        swift_file_path,
        "responsive0 {\n    Text(\"Hello\")\n}",
        state_variables: [
          '@Environment(\.horizontalSizeClass) private var horizontalSizeClass',
          '@Environment(\.verticalSizeClass) private var verticalSizeClass'
        ],
        responsive_functions: [responsive_func]
      )

      content = File.read(swift_file_path)

      # Should include the responsive function
      expect(content).to include('func responsive0<Content: View>')
      expect(content).to include('content()')

      # Should include @Environment variables
      expect(content).to include('@Environment')
      expect(content).to include('horizontalSizeClass')
      expect(content).to include('verticalSizeClass')

      # Should include the body code
      expect(content).to include('responsive0 {')
    end

    it 'works with empty responsive_functions array' do
      result = updater.update_generated_body(
        swift_file_path,
        'Text("Hello")',
        responsive_functions: []
      )
      expect(result).to be true

      content = File.read(swift_file_path)
      expect(content).to include('Text("Hello")')
    end

    it 'handles both section functions and responsive functions' do
      # Create a large body that triggers section splitting
      large_body = (1..150).map { |i| "Text(\"Line #{i}\")" }.join("\n")

      responsive_func = <<~FUNC
    @ViewBuilder private func responsive0<Content: View>(
        @ViewBuilder content: () -> Content
    ) -> some View {
        content()
    }
      FUNC

      updater.update_generated_body(
        swift_file_path,
        large_body,
        responsive_functions: [responsive_func]
      )

      content = File.read(swift_file_path)

      # Should include responsive function
      expect(content).to include('func responsive0<Content: View>')
    end
  end
end
