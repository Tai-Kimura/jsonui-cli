# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/converters/network_image_converter'
require 'react/converters/embed_converter'

# Built-in props contract: every JSX attribute a converter can emit onto a
# built-in component (templates/*.tsx) must be declared in that component's
# props interface. The gap this closes: a declaration that is valid per the
# SSoT (common attributes like onClick pass `jui build` with 0 warnings) but
# breaks tsc in the consumer because the built-in never declared the prop —
# the zero-warning gate cannot see it, so it surfaces at compile time
# (rjui-network-image-onclick-not-forwarded).
#
# Mechanics: each converter runs on a MAXIMAL node (every attribute that
# triggers an emit branch), the emitted attribute names are pinned exactly,
# and the pinned surface is asserted to be a subset of the parsed props
# interface. Adding a new emit therefore fails the pin, forcing the author
# to extend the template's props (and the pin) in the same change.
#
# This contract is static per tool version — it does not vary by consumer
# project — so it lives here in the suite rather than in `jui build`.
RSpec.describe 'built-in props contract' do
  TEMPLATES_DIR = File.expand_path('../../lib/react/templates', __dir__)

  def props_interface_keys(template_file, interface_name)
    source = File.read(File.join(TEMPLATES_DIR, template_file))
    body = source[/interface #{interface_name}\s*\{(.*?)\n\}/m, 1]
    raise "interface #{interface_name} not found in #{template_file}" unless body

    body.scan(/^\s*(?:'([^']+)'|([A-Za-z_]\w*))\??:/).map { |q, plain| q || plain }
  end

  def emitted_attribute_names(jsx, component)
    tag = jsx[/<#{component}\b(.*?)\/?>/m, 1]
    raise "<#{component}> tag not found in emitted JSX" unless tag

    tag.scan(/\s([A-Za-z][\w-]*)=/).flatten.uniq
  end

  describe 'NetworkImage' do
    # Every attribute that triggers an emit branch in the converter.
    # If you add a new emit, this node (and the pin below) must grow with it.
    let(:maximal_node) do
      {
        'type' => 'NetworkImage',
        'id' => 'hero_image',
        'src' => '@{imageUrl}',
        'contentMode' => 'cover',
        'placeholder' => 'https://example.invalid/loading.png',
        'defaultImage' => 'https://example.invalid/default.png',
        'errorImage' => 'https://example.invalid/error.png',
        'alt' => 'hero',
        'loading' => 'lazy',
        'onLoad' => '@{onImageLoaded}',
        'onError' => '@{onImageFailed}',
        'onClick' => '@{onImageTapped}',
        'cornerRadius' => '8',
        'testId' => 'hero-image',
        'tag' => 'hero'
      }
    end

    let(:jsx) do
      RjuiTools::React::Converters::NetworkImageConverter
        .new(maximal_node, { 'use_tailwind' => true }).convert
    end

    it 'pins the emit surface exactly (a new emit must extend this pin AND the props)' do
      expect(emitted_attribute_names(jsx, 'NetworkImage').sort).to eq(
        %w[alt className contentMode defaultImage data-tag data-testid errorImage id
           loading onClick onError onLoad placeholder src].sort
      )
    end

    it 'declares every emittable attribute in NetworkImageProps' do
      declared = props_interface_keys('network_image.tsx', 'NetworkImageProps')
      undeclared = emitted_attribute_names(jsx, 'NetworkImage') - declared
      expect(undeclared).to eq([]),
        "converter can emit #{undeclared.join(', ')} but NetworkImageProps does not declare " \
        'them — a valid declaration would pass jui build and then fail tsc in the consumer'
    end

    it 'declares the bound-style channel (style) even though the maximal node does not bind one' do
      # build_style_attr fires only for bound/dynamic styles; keep the channel
      # declared so a bound width/margin cannot reopen the class.
      expect(props_interface_keys('network_image.tsx', 'NetworkImageProps')).to include('style')
    end
  end

  describe 'EmbedContainer' do
    let(:maximal_node) do
      {
        'type' => 'Embed',
        'id' => 'detail_embed',
        'screen' => 'item_detail',
        'navigationMode' => 'isolated',
        'params' => { 'itemId' => '@{selectedId}' },
        'events' => { 'onClose' => '@{onEmbedClosed}' },
        'background' => '#FFFFFF'
      }
    end

    let(:jsx) do
      RjuiTools::React::Converters::EmbedConverter
        .new(maximal_node, { 'use_tailwind' => true }).convert
    end

    it 'declares every emittable attribute in EmbedContainerProps' do
      declared = props_interface_keys('EmbedContainer.tsx', 'EmbedContainerProps')
      undeclared = emitted_attribute_names(jsx, 'EmbedContainer') - declared
      expect(undeclared).to eq([]),
        "converter can emit #{undeclared.join(', ')} but EmbedContainerProps does not declare them"
    end
  end
end
