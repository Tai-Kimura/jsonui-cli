# frozen_string_literal: true

require 'set'
require_relative '../../../lib/compose/components/networkimage_component'
require_relative '../../../lib/compose/helpers/resource_resolver'

# Ticket jui-networkimage-load-listener. Every NetworkImage is KotlinJsonUI's
# KjuiNetworkImage (2.60.0) with its state images as resource ids; the load
# listener's four attributes follow them, in KjuiNetworkImage's order, only
# when written.
RSpec.describe KjuiTools::Compose::Components::NetworkImageComponent do
  after { KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {} }

  def generated(extra, depth = 0)
    imports = Set.new
    code = described_class.generate({ 'type' => 'NetworkImage', 'id' => 'photo', 'url' => '@{photoUrl}' }.merge(extra), depth, imports)
    [code, imports]
  end

  it 'draws every NetworkImage with KjuiNetworkImage, imported, with the library floor' do
    code, imports = generated({})
    expect(code.lines.first.chomp).to eq('// Requires KotlinJsonUI >= 2.60.0 (KjuiNetworkImage)')
    expect(code).to include('KjuiNetworkImage(')
    expect(code).not_to include('AsyncImage(')
    expect(imports).to include(:kjui_network_image)
    expect(imports).not_to include(:async_image)
  end

  it 'passes the state images as resource ids, not painters' do
    code, imports = generated({ 'placeholder' => 'dots', 'errorImage' => 'broken.png', 'defaultImage' => 'empty' })
    expect(code).to include('placeholder = R.drawable.dots,')
    expect(code).to include('error = R.drawable.broken')
    expect(code).to include('fallback = R.drawable.empty')
    expect(code).not_to include('painterResource')
    expect(imports).not_to include(:painter_resource)
  end

  it 'looks a bound state image up by name at run time, 0 for none' do
    code, = generated({ 'errorImage' => '@{brokenName}' })
    expect(code).to include('error = LocalContext.current.let { ctx -> ctx.resources.getIdentifier(')
    expect(code).not_to include('painterResource')
  end

  it 'writes no second comma after the last argument when no modifier is emitted' do
    code = described_class.generate({ 'type' => 'NetworkImage', 'errorImage' => 'broken' }, 0, Set.new)
    expect(code).not_to include(',,')
    expect(code).to include("    contentDescription = null,\n    error = R.drawable.broken\n)")
  end

  it 'adds none of the four when none is written' do
    code, = generated({ 'placeholder' => 'dots' })
    expect(code).not_to match(/loadingRenderer|loadingDelayMillis|transitionMillis|onLoadStateChange/)
  end

  it 'passes a written renderer, delay and fade after the state images' do
    code, = generated({ 'errorImage' => 'broken', 'loadingRenderer' => 'fill_meter', 'loadingDelay' => 200, 'transitionDuration' => 240 })
    expect(code).to include("error = R.drawable.broken,\n    loadingRenderer = \"fill_meter\",\n    loadingDelayMillis = 200,\n    transitionMillis = 240\n)")
  end

  it 'passes a bound renderer name as a non-null String' do
    code, = generated({ 'loadingRenderer' => '@{renderer}' })
    expect(code).to match(/loadingRenderer = \(?data\.renderer/)
  end

  it 'clamps a delay outside its range with a WARN, and leaves out one that is not a number' do
    expect(KjuiTools::Core::Logger).to receive(:warn).with(/'transitionDuration' 4000 is outside 0-1000 ms; 1000 is used/)
    expect(generated({ 'transitionDuration' => 4000 }).first).to include('transitionMillis = 1000')
    expect(KjuiTools::Core::Logger).to receive(:warn).with(/'loadingDelay' is "soon", not a number/)
    expect(generated({ 'loadingDelay' => 'soon' }).first).not_to include('loadingDelayMillis')
  end

  describe 'onLoadStateChange' do
    def with_handler(klass)
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = { 'onPhotoState' => { 'class' => klass } }
      generated({ 'onLoadStateChange' => '@{onPhotoState}' }).first
    end

    it 'hands the state to a one-parameter handler' do
      expect(with_handler('((String) -> Unit)?')).to include('onLoadStateChange = { state -> data.onPhotoState?.invoke(state) }')
    end

    it 'hands the view id and the state to a two-parameter handler' do
      expect(with_handler('((String, String) -> Unit)?')).to include('onLoadStateChange = { state -> data.onPhotoState?.invoke("photo", state) }')
    end

    it 'names the unused parameter _ for a handler that takes nothing (a warning is an error)' do
      expect(with_handler('(() -> Unit)?')).to include('onLoadStateChange = { _ -> data.onPhotoState?.invoke() }')
    end

    it 'emits nothing for a bare string' do
      expect(generated({ 'onLoadStateChange' => 'onPhotoState' }).first).not_to include('onLoadStateChange')
    end
  end
end
