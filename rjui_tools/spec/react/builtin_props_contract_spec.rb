# frozen_string_literal: true

require_relative '../spec_helper'
require_relative '../support/typescript_compiler'
require 'react/converters/network_image_converter'
require 'react/converters/embed_converter'
require 'react/converters/label_converter'

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

  # React manages these itself: `ref` reaches the template through
  # forwardRef, `key` never reaches the component at all. Neither can be
  # declared in a props interface, so the subset check ignores them.
  REACT_MANAGED_ATTRS = %w[ref key].freeze

  def props_interface_keys(template_file, interface_name)
    source = File.read(File.join(TEMPLATES_DIR, template_file))
    body = source[/interface #{interface_name}\s*\{(.*?)\n\}/m, 1]
    raise "interface #{interface_name} not found in #{template_file}" unless body

    body.scan(/^\s*(?:'([^']+)'|([A-Za-z_]\w*))\??:/).map { |q, plain| q || plain }
  end

  # The data a generated component reads these from: the handlers as the
  # data model declares them once the layout declares them (the build's
  # binding warning says to: `{ "class": "(() -> Void)?" }`), and an Embed
  # event's handler as the data model declares it by itself, taking the
  # event's payload.
  BUILTIN_AMBIENT = <<~TS
    declare namespace React { type CSSProperties = { [property: string]: string | number | undefined } }
    declare const data: {
      imageUrl?: string; onImageLoaded?: () => void; onImageFailed?: () => void; onImageTapped?: () => void;
      notesText?: string; onNotesTapped?: () => void; selectedId?: string;
      onEmbedClosed?: (value: Record<string, unknown>) => void;
    };
  TS

  # The attribute names of the component's opening tag, read attribute by
  # attribute: a value is a string or a braced expression, which can hold `>`
  # (an arrow function — the keys a tap takes, keyboard_tap_attrs).
  def emitted_attribute_names(jsx, component)
    start = jsx =~ /<#{component}\b/
    raise "<#{component}> tag not found in emitted JSX" unless start

    i = start + component.length + 1
    names = []
    loop do
      i += 1 while jsx[i]&.match?(/\s/)
      break if jsx[i].nil? || jsx[i] == '>' || jsx[i, 2] == '/>'

      if jsx[i] == '{' # a spread
        depth = 0
        loop do
          depth += 1 if jsx[i] == '{'
          depth -= 1 if jsx[i] == '}'
          i += 1
          break if depth.zero?
        end
        next
      end
      name = jsx[i..][/\A[A-Za-z][\w-]*/] or raise "unreadable attribute at #{jsx[i, 40].inspect}"
      names << name
      i += name.length
      next unless jsx[i] == '='

      i += 1
      if jsx[i] == '"'
        i = jsx.index('"', i + 1) + 1
      else
        depth = 0
        loop do
          depth += 1 if jsx[i] == '{'
          depth -= 1 if jsx[i] == '}'
          i += 1
          break if depth.zero?
        end
      end
    end
    names.uniq
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
        'tag' => 'hero',
        # a tap the rule makes a button (annotate! writes it): role, tab
        # stop and keys (keyboard_tap_attrs)
        '_tapShape' => 'button'
      }
    end

    let(:jsx) do
      RjuiTools::React::Converters::NetworkImageConverter
        .new(maximal_node, { 'use_tailwind' => true }).convert
    end

    it 'pins the emit surface exactly (a new emit must extend this pin AND the props)' do
      expect(emitted_attribute_names(jsx, 'NetworkImage').sort).to eq(
        %w[alt className contentMode defaultImage data-tag data-testid errorImage id
           loading onClick onError onKeyDown onLoad placeholder role src tabIndex].sort
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

    # The names above are a subset; this is the types: `contentMode` is one
    # of the template's union, the handlers take what the data holds.
    it 'compiles against NetworkImageProps', :typescript_compile do
      expect(TypeScriptCompiler.component(jsx)).to compile_as_typescript.with_ambient(<<~TS)
        #{BUILTIN_AMBIENT}
        #{TypeScriptCompiler.template_declarations('network_image.tsx', 'NetworkImageProps')}
        declare const NetworkImage: (props: NetworkImageProps) => JSX.Element;
      TS
    end
  end

  describe 'LinkifyText (Label linkable)' do
    let(:maximal_node) do
      {
        'type' => 'Label',
        'id' => 'notes_label',
        'linkable' => true,
        'text' => '@{notesText}',
        'onClick' => '@{onNotesTapped}',
        'autoShrink' => true, # rides the measurement ref on the root
        'testId' => 'notes-label',
        'tag' => 'notes',
        '_tapShape' => 'button'
      }
    end

    let(:jsx) do
      RjuiTools::React::Converters::LabelConverter
        .new(maximal_node, { 'use_tailwind' => true }).convert
    end

    it 'pins the emit surface exactly (a new emit must extend this pin AND the props)' do
      surface = emitted_attribute_names(jsx, 'LinkifyText') - REACT_MANAGED_ATTRS
      expect(surface.sort).to eq(
        %w[className data-tag data-testid id onClick onKeyDown role tabIndex text].sort
      )
    end

    it 'declares every emittable attribute in LinkifyTextProps' do
      declared = props_interface_keys('linkify_text.tsx', 'LinkifyTextProps')
      undeclared = emitted_attribute_names(jsx, 'LinkifyText') - declared - REACT_MANAGED_ATTRS
      expect(undeclared).to eq([]),
        "converter can emit #{undeclared.join(', ')} but LinkifyTextProps does not declare them"
    end

    it 'declares the bound-style channel (style) even though the maximal node does not bind one' do
      expect(props_interface_keys('linkify_text.tsx', 'LinkifyTextProps')).to include('style')
    end

    # The template is `React.forwardRef<HTMLSpanElement, LinkifyTextProps>`,
    # so its props are the interface and a ref to a span; the component's own
    # shrink ref is `useRef<HTMLElement | null>` (react_generator).
    it 'compiles against LinkifyTextProps', :typescript_compile do
      expect(TypeScriptCompiler.component(jsx)).to compile_as_typescript.with_ambient(<<~TS)
        #{BUILTIN_AMBIENT}
        #{TypeScriptCompiler.template_declarations('linkify_text.tsx', 'LinkifyTextProps')}
        declare const LinkifyText: (props: LinkifyTextProps & { ref?: { current: HTMLSpanElement | null } }) => JSX.Element;
        declare const notesLabelShrinkRef: { current: HTMLElement | null };
      TS
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

    # The handler as the SSoT declares it (a parent VM method's name). Until
    # 1.9.0 the bridge called `viewModel.onEmbedClosed(…)`, and a generated
    # web component has `data`, no `viewModel` — TS2304 (ticket
    # rjui-embed-event-bridge-calls-an-undeclared-view-model); this arm was
    # pending under that id until the bridge called `data`.
    it 'compiles against EmbedContainerProps', :typescript_compile do
      node = maximal_node.merge('events' => { 'onClose' => 'onEmbedClosed' })
      emitted = RjuiTools::React::Converters::EmbedConverter.new(node, { 'use_tailwind' => true }).convert
      expect(TypeScriptCompiler.component(emitted)).to compile_as_typescript.with_ambient(<<~TS)
        #{BUILTIN_AMBIENT}
        declare namespace React {
          type ReactNode = unknown;
          type ComponentType<P> = (props: P) => JSX.Element;
        }
        #{TypeScriptCompiler.template_declarations('EmbedContainer.tsx', 'EmbedContainerProps', 'EmbedNavigationMode',
                                'EmbedScreenResolver', 'EmbeddedEvent', 'EmbedStackEntry')}
        declare const EmbedContainer: (props: EmbedContainerProps) => JSX.Element;
        declare function buildEmbedScreenResolver(
          table: Record<string, React.ComponentType<{ data?: Record<string, unknown> }>>
        ): EmbedScreenResolver;
        declare const ItemDetail: (props: { data?: Record<string, unknown> }) => JSX.Element;
      TS
    end
  end
end
