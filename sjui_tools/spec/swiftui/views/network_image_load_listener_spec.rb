# frozen_string_literal: true

require 'swiftui/views/network_image_converter'
require_relative '../../support/emitted_swift'

# Ticket jui-networkimage-load-listener: loadingRenderer, loadingDelay,
# transitionDuration and onLoadStateChange are the last NetworkImage
# initializer arguments, after headers, in that order (Swift matches labels
# positionally). An image that writes none of them emits what it did before.
RSpec.describe SjuiTools::SwiftUI::Views::NetworkImageConverter do
  include EmittedSwift

  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  after { SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {} }

  def generated(component)
    described_class.new({ 'type' => 'NetworkImage', 'id' => 'photo', 'url' => '@{photoUrl}' }.merge(component), 0, nil).convert
  end

  def header_of(code)
    code.split("\n").take_while { |line| !line.start_with?(')') }.join("\n")
  end

  it 'emits no new argument and no library floor when none of the four is written' do
    code = generated({ 'placeholder' => 'dots' })
    expect(code).not_to include('Requires SwiftJsonUI')
    expect(code).not_to match(/loadingRenderer|loadingDelay|transitionDuration|onLoadStateChange/)
    expect(header_of(code)).to eq("NetworkImage(\n    url: data.photoUrl,\n    placeholder: \"dots\"")
  end

  it 'passes a written renderer name, delay and fade as literals, with the library floor' do
    code = generated({ 'loadingRenderer' => 'fill_meter', 'loadingDelay' => 200, 'transitionDuration' => 240 })
    expect(code.lines.first.chomp).to eq('// Requires SwiftJsonUI >= 10.41.0 (NetworkImage loadingRenderer / loadingDelay / transitionDuration / onLoadStateChange)')
    expect(code).to include("    loadingRenderer: \"fill_meter\",\n    loadingDelay: 200,\n    transitionDuration: 240\n)")
  end

  it 'passes a bound renderer name as the data value' do
    code = generated({ 'loadingRenderer' => '@{loadingRenderer}' })
    expect(code).to include('loadingRenderer: data.loadingRenderer')
  end

  it 'puts the four after headers, the last argument with no trailing comma' do
    code = generated({ 'headers' => { 'X-A' => '1' }, 'loadingRenderer' => 'fill_meter' })
    expect(code).to include("    headers: [\n        \"X-A\": \"1\"\n    ],\n    loadingRenderer: \"fill_meter\"\n)")
  end

  it 'keeps the headers block unchanged when none of the four is written' do
    code = generated({ 'headers' => { 'X-A' => '1' } })
    expect(code).to include("    headers: [\n        \"X-A\": \"1\"\n    ]\n)")
  end

  it 'rounds a fractional delay and clamps one outside its range, with a WARN' do
    expect(SjuiTools::Core::Logger).to receive(:warn).with(/'loadingDelay' 5000 is outside 0-2000 ms; 2000 is used/)
    expect(generated({ 'loadingDelay' => 5000 })).to include('loadingDelay: 2000')
    expect(generated({ 'transitionDuration' => 120.4 })).to include('transitionDuration: 120')
  end

  it 'leaves out a delay that is not a number, with a WARN' do
    expect(SjuiTools::Core::Logger).to receive(:warn).with(/'loadingDelay' is "soon", not a number of milliseconds/)
    code = generated({ 'loadingDelay' => 'soon' })
    expect(code).not_to include('loadingDelay')
    expect(code).not_to include('Requires SwiftJsonUI')
  end

  # SwiftJsonUI 10.41.0's NetworkImage init, as far as these arguments go:
  # the labels in order and their types (ticket jui-networkimage-load-listener).
  NETWORK_IMAGE_STUB = <<~SWIFT
    struct NetworkImage: View {
        enum ContentMode { case fit, fill, center, stretch, top, bottom, left, right }
        init(url: String? = nil, placeholder: String? = nil, defaultImage: String? = nil,
             errorImage: String? = nil, loadingImage: String? = nil, contentMode: ContentMode = .fit,
             renderingMode: Image.TemplateRenderingMode? = nil, headers: [String: String] = [:],
             loadingRenderer: String? = nil, loadingDelay: Int? = nil, transitionDuration: Int? = nil,
             onLoadStateChange: ((String) -> Void)? = nil) {}
        var body: some View { EmptyView() }
    }
  SWIFT

  it 'compiles with every argument and every handler shape' do
    SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = {
      'onState1' => { 'class' => '((String) -> Void)?' },
      'onState2' => { 'class' => '((String, String) -> Void)?' },
      'onState0' => { 'class' => '(() -> Void)?' }
    }
    codes = [
      generated({ 'placeholder' => 'dots' }),
      generated({ 'headers' => { 'X-A' => '1' }, 'loadingRenderer' => 'fill_meter', 'loadingDelay' => 200, 'transitionDuration' => 240 }),
      generated({ 'loadingRenderer' => '@{renderer}' }),
      generated({ 'onLoadStateChange' => '@{onState1}' }),
      generated({ 'onLoadStateChange' => '@{onState2}' }),
      generated({ 'onLoadStateChange' => '@{onState0}' })
    ]
    data = ['var photoUrl: String = ""', 'var renderer: String? = nil',
            'var onState1: ((String) -> Void)? = nil', 'var onState2: ((String, String) -> Void)? = nil',
            'var onState0: (() -> Void)? = nil']
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}", data: data, stubs: NETWORK_IMAGE_STUB)).to compile_as_swift
  end

  describe 'onLoadStateChange' do
    it 'hands the state to a one-parameter handler' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = { 'onPhotoState' => { 'class' => '((String) -> Void)?' } }
      expect(generated({ 'onLoadStateChange' => '@{onPhotoState}' }))
        .to include('onLoadStateChange: { state in data.onPhotoState?(state) }')
    end

    it 'hands the view id and the state to a two-parameter handler' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = { 'onPhotoState' => { 'class' => '((String, String) -> Void)?' } }
      expect(generated({ 'onLoadStateChange' => '@{onPhotoState}' }))
        .to include('onLoadStateChange: { state in data.onPhotoState?("photo", state) }')
    end

    it 'calls a no-parameter handler with nothing' do
      SjuiTools::SwiftUI::Views::ColorHelper.data_definitions = { 'onPhotoState' => { 'class' => '(() -> Void)?' } }
      expect(generated({ 'onLoadStateChange' => '@{onPhotoState}' }))
        .to include('onLoadStateChange: { state in data.onPhotoState?() }')
    end

    it 'emits nothing for a bare string, which names no handler' do
      code = generated({ 'onLoadStateChange' => 'onPhotoState' })
      expect(code).not_to include('onLoadStateChange')
      expect(code).not_to include('Requires SwiftJsonUI')
    end
  end
end
