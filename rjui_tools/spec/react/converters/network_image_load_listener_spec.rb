# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/network_image_converter'
require_relative '../../support/typescript_compiler'

# Ticket jui-networkimage-load-listener: the web face takes transitionDuration
# (a CSS opacity fade) and onLoadStateChange; loadingRenderer and loadingDelay
# are not declared for react, so the web draws placeholder.
RSpec.describe RjuiTools::React::Converters::NetworkImageConverter do
  def converted(extra, classes = {})
    config = { 'use_tailwind' => true, '_data_classes' => classes }
    described_class.new({ 'type' => 'NetworkImage', 'id' => 'photo', 'src' => '@{photoUrl}' }.merge(extra), config).convert
  end

  it 'passes nothing new when none is written' do
    expect(converted({ 'placeholder' => 'dots.png' })).not_to match(/transitionDuration|onLoadStateChange/)
  end

  it 'passes transitionDuration as a number, clamped with a WARN' do
    expect(converted({ 'transitionDuration' => 240 })).to include(' transitionDuration={240}')
    expect(RjuiTools::Core::Logger).to receive(:warn).with(/'transitionDuration' 4000 is outside 0-1000 ms; 1000 is used/)
    expect(converted({ 'transitionDuration' => 4000 })).to include(' transitionDuration={1000}')
  end

  it 'leaves out a transitionDuration that is not a number' do
    expect(converted({ 'transitionDuration' => 'slow' })).not_to include('transitionDuration')
  end

  it 'draws no renderer on the web: loadingRenderer and loadingDelay pass nothing' do
    code = converted({ 'loadingRenderer' => 'fill_meter', 'loadingDelay' => 200, 'placeholder' => 'dots.png' })
    expect(code).not_to match(/loadingRenderer|loadingDelay/)
    expect(code).to include('placeholder="dots.png"')
  end

  # The emits above, type-checked against the props the NetworkImage template
  # declares (transitionDuration: number, onLoadStateChange: (state: string) => void).
  it 'compiles as TypeScript with every handler shape', :typescript_compile do
    classes = { 'onState1' => '((String) -> Void)?', 'onState2' => '((String, String) -> Void)?', 'onState0' => '(() -> Void)?' }
    elements = [
      converted({ 'transitionDuration' => 240 }),
      converted({ 'onLoadStateChange' => '@{onState1}' }, classes),
      converted({ 'onLoadStateChange' => '@{onState2}' }, classes),
      converted({ 'onLoadStateChange' => '@{onState0}' }, classes)
    ]
    ambient = TypeScriptCompiler::AMBIENT + <<~TS
      declare const data: {
        photoUrl: string; onState1?: (state: string) => void;
        onState2?: (id: string, state: string) => void; onState0?: () => void
      };
      declare namespace React {
        type CSSProperties = { [property: string]: string | number | undefined };
        type MouseEvent<T> = { target: T }; type KeyboardEvent<T> = { target: T };
      }
      #{TypeScriptCompiler.template_declarations('network_image.tsx', 'NetworkImageProps')}
      declare const NetworkImage: (props: NetworkImageProps) => JSX.Element;
    TS
    expect(TypeScriptCompiler.component(*elements)).to compile_as_typescript.with_ambient(ambient)
  end

  describe 'onLoadStateChange' do
    it 'hands the state to a one-parameter handler' do
      expect(converted({ 'onLoadStateChange' => '@{onPhotoState}' }, { 'onPhotoState' => '((String) -> Void)?' }))
        .to include(' onLoadStateChange={(state) => data.onPhotoState?.(state)}')
    end

    it 'hands the view id and the state to a two-parameter handler' do
      expect(converted({ 'onLoadStateChange' => '@{onPhotoState}' }, { 'onPhotoState' => '((String, String) -> Void)?' }))
        .to include(' onLoadStateChange={(state) => data.onPhotoState?.("photo", state)}')
    end

    it 'calls a no-parameter or undeclared handler with nothing' do
      expect(converted({ 'onLoadStateChange' => '@{onPhotoState}' }, { 'onPhotoState' => '(() -> Void)?' }))
        .to include(' onLoadStateChange={() => data.onPhotoState?.()}')
      expect(converted({ 'onLoadStateChange' => '@{onPhotoState}' })).to include(' onLoadStateChange={() => data.onPhotoState?.()}')
    end

    it 'emits nothing for a bare string' do
      expect(converted({ 'onLoadStateChange' => 'onPhotoState' })).not_to include('onLoadStateChange')
    end
  end
end
