# frozen_string_literal: true

require 'json'
require 'swiftui/views/image_converter'
require 'swiftui/views/network_image_converter'

# An image with no contentMode draws the declared default. The default is
# declared once, in shared/core/attribute_semantics.json
# (`semantics.image.defaultContentMode`, the 2026-08-03 user ruling), and
# every path's no-contentMode drawing is bound to it here: the value is read
# from the file, so a changed ruling moves the expectation and turns this red
# until the converter follows (4f ruling, 2026-09-26; ticket
# image-content-mode-default-differs-by-path).
RSpec.describe 'sjui SwiftUI codegen: an image with no contentMode' do
  shared_core = File.expand_path('../../../../shared/core', __dir__)
  declared = JSON.parse(File.read(File.join(shared_core, 'attribute_semantics.json'), encoding: 'UTF-8'))
                 .fetch('semantics').fetch('image').fetch('defaultContentMode')

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(type, mode)
    node = { 'type' => type, 'id' => 'img', 'width' => 100, 'height' => 60 }
    node[type == 'NetworkImage' ? 'url' : 'src'] = type == 'NetworkImage' ? 'https://example.invalid/a.png' : 'probe_asset'
    node['contentMode'] = mode if mode
    klass = type == 'NetworkImage' ? SjuiTools::SwiftUI::Views::NetworkImageConverter : SjuiTools::SwiftUI::Views::ImageConverter
    klass.new(node, 0).convert
  end

  it "emits for Image and CircleImage exactly what the declared default (#{declared}) emits" do
    %w[Image CircleImage].each do |type|
      expect(emit(type, nil)).to eq(emit(type, declared)), type
    end
  end

  it 'emits something else for another mode — the comparison can tell them apart' do
    other = declared.casecmp?('AspectFill') ? 'fit' : 'AspectFill'
    expect(emit('Image', other)).not_to eq(emit('Image', nil))
  end

  # NetworkImage passes no contentMode argument, so SwiftJsonUI's
  # NetworkImage.init default draws: `.fit` (NetworkImage.swift, `contentMode:
  # ContentMode = .fit`; SwiftJsonUI binds that default to this same file in
  # its own tests). The declared default has to emit that same case.
  it 'passes NetworkImage no contentMode, and the declared default emits the case NetworkImage.init defaults to' do
    expect(emit('NetworkImage', nil)).not_to include('contentMode:')
    expect(emit('NetworkImage', declared)).to match(/contentMode: \.fit\b/)
  end

  # NetworkImage mirrored from SwiftJsonUI (Classes/SwiftUI/NetworkImage.swift):
  # its ContentMode cases and the init's defaulted parameters, so a wrong
  # argument fails here as it would in a consumer build. The default drawn is
  # not asserted through this stub — a stub's default says nothing about the
  # library's; SwiftJsonUI's own test reads it.
  network_image_stub = <<~SWIFT
    struct NetworkImage: View {
        enum ContentMode { case fit, fill, center, stretch, top, bottom, left, right }
        init(url: String? = nil, placeholder: String? = nil, defaultImage: String? = nil,
             errorImage: String? = nil, loadingImage: String? = nil, contentMode: ContentMode = .fit,
             renderingMode: Image.TemplateRenderingMode? = nil, headers: [String: String] = [:]) {}
        var body: some View { Color.clear }
    }
  SWIFT

  %w[Image CircleImage NetworkImage].each do |type|
    it "#{type}: what it emits with no contentMode, and with the declared default, compiles" do
      [nil, declared].each do |mode|
        expect(compilable_view(emit(type, mode), stubs: network_image_stub)).to compile_as_swift
      end
    end
  end
end
