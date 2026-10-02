# frozen_string_literal: true

require 'swiftui/views/image_converter'
require 'swiftui/view_registry'
require 'swiftui/converter_factory'
require_relative '../../support/emitted_swift'

# An image is drawn inside its frame, whatever its contentMode. AspectFill is
# the crop (attribute_semantics.json image.ruling), but SwiftUI's
# `.aspectRatio(contentMode: .fill)` is fill-and-overflow, and sjui emitted it
# with no clip: a texture in a 16pt book spine covered the whole page on iOS
# (ticket sjui-aspectfill-image-is-not-cropped-to-its-frame). A positional
# mode (center, top, …) with a frame that is not two numbers drew the
# unscaled image whole, past the frame, too.
#
# The drawn arm is AspectFillProbeUITests in SwiftJsonUI's ConformanceHost
# (pixels just outside each frame, Dynamic and generated): it failed before
# this and passes after. Here: the emit, and that it compiles.
RSpec.describe 'sjui: an image stays inside its frame' do
  include EmittedSwift

  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  def emit(extra)
    factory = SjuiTools::SwiftUI::ConverterFactory.new
    factory.create_converter({ 'type' => 'Image', 'id' => 'img', 'src' => 'cover' }.merge(extra), 0, nil, factory).convert.to_s
  end

  def fill_frame
    '.frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity, alignment: .center)'
  end

  it 'AspectFill on a sized frame takes the offered size and is clipped after the frame' do
    out = emit('contentMode' => 'AspectFill', 'width' => 'matchParent', 'height' => 'matchParent')
    expect(out).to include('.aspectRatio(contentMode: .fill)', fill_frame, '.clipped()')
    expect(out.index('.clipped()')).to be > out.index('.frame(maxWidth: .infinity, maxHeight: .infinity')
  end

  it 'AspectFill keeps a wrapContent axis at the image size' do
    out = emit('contentMode' => 'AspectFill', 'width' => 16, 'height' => 'wrapContent')
    expect(out).to include('.frame(minWidth: 0, maxWidth: .infinity, alignment: .center)', '.clipped()')
    expect(out).not_to include('minHeight: 0')
  end

  it 'a positional mode on a frame that is not two numbers is placed and cropped' do
    out = emit('contentMode' => 'center', 'width' => 16, 'height' => 'matchParent')
    expect(out).to include('.frame(minWidth: 0, maxWidth: .infinity, minHeight: 0, maxHeight: .infinity, alignment: .center)',
                           '.clipped()')
    expect(out).not_to include('.resizable()')
  end

  it 'control: AspectFit and the stretch are not cropped, and a numeric positional frame is as before' do
    %w[AspectFit fill].each do |mode|
      out = emit('contentMode' => mode, 'width' => 'matchParent', 'height' => 'matchParent')
      expect(out).not_to include('minWidth: 0', '.clipped()'), mode
    end
    out = emit('contentMode' => 'center', 'width' => 120, 'height' => 60)
    expect(out).to include('.frame(width: 120, height: 60, alignment: .center)')
    expect(out).not_to include('minWidth: 0')
  end

  it 'type-checks', :swift_compile do
    codes = [emit('contentMode' => 'AspectFill', 'width' => 'matchParent', 'height' => 'matchParent'),
             emit('contentMode' => 'center', 'width' => 16, 'height' => 'matchParent')]
    expect(compilable_view("VStack {\n#{codes.join("\n")}\n}")).to compile_as_swift
  end
end
