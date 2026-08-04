# frozen_string_literal: true

require 'spec_helper'
require 'react/converters/base_converter'
require 'react/converters/view_converter'
require 'react/converters/label_converter'
require 'react/converters/button_converter'
require 'react/converters/image_converter'
require 'react/converters/slider_converter'
require 'react/converters/switch_converter'
require 'react/converters/text_view_converter'
require 'react/converters/text_field_converter'
require 'react/converters/collection_converter'

# The bound-value emitter series (plan 49 lane A).
#
# A Tailwind class is a compile-time string and cannot carry a value that only
# exists at runtime. Every defect plan 41 classified as bound-literal-leak /
# bound-uncompilable / bound-frozen was that one mistake in a different place.
# These pins hold the two halves of the fix: the binding reaches a CSS property
# (or a JSX expression), and the STATIC form is untouched.
RSpec.describe 'bound value emitters' do
  let(:config) { { 'use_tailwind' => true } }

  def convert(node, klass)
    klass.new(node, config).convert_node(2)
  end

  def view(attrs)
    convert({ 'type' => 'View' }.merge(attrs), RjuiTools::React::Converters::ViewConverter)
  end

  def label(attrs)
    convert({ 'type' => 'Label', 'text' => 'x' }.merge(attrs), RjuiTools::React::Converters::LabelConverter)
  end

  describe 'the leak family — a binding must never reach a class name' do
    it 'sends a bound fontSize to the inline style instead of text-[@{v}px]' do
      out = label('fontSize' => '@{size}')
      expect(out).not_to include('@{')
      expect(out).to include('fontSize: `${data.size}px`')
    end

    it 'sends a bound cornerRadius to borderRadius instead of rounded-[@{v}px]' do
      out = view('cornerRadius' => '@{r}')
      expect(out).not_to include('@{')
      expect(out).to include('borderRadius: `${data.r}px`')
    end

    it 'sends a bound spacing to gap instead of gap-@{v}' do
      out = view('orientation' => 'horizontal', 'spacing' => '@{gap}')
      expect(out).not_to include('@{')
      expect(out).to include('gap: `${data.gap}px`')
    end
  end

  describe 'the frozen family — Ruby truthiness must not decide a runtime flag' do
    it 'does not bake mx-auto for a bound centerHorizontal' do
      out = label('centerHorizontal' => '@{c}')
      expect(out).not_to include('mx-auto')
      expect(out).to include("marginInline: data.c ? 'auto' : undefined")
    end

    it 'does not bake overflow-hidden for a bound clipToBounds' do
      out = view('clipToBounds' => '@{clip}')
      expect(out).not_to include('overflow-hidden')
      expect(out).to include("overflow: data.clip ? 'hidden' : undefined")
    end

    it 'does not freeze a bound weight to flex-none via to_f' do
      out = view('weight' => '@{w}')
      expect(out).not_to include('flex-none')
      expect(out).to include('flexGrow: data.w')
    end

    it 'does not freeze a bound lineSpacing to a 1.0 multiplier via to_f' do
      out = label('lineSpacing' => '@{s}', 'fontSize' => 16)
      expect(out).to include('lineHeight: ((16) + (data.s)) / (16)')
    end

    it 'lets a bound Collection lazy still reach the none shape' do
      out = convert({ 'type' => 'Collection', 'id' => 'c', 'lazy' => '@{mode}' },
                    RjuiTools::React::Converters::CollectionConverter)
      expect(out).to include("overflowY: data.mode === 'none' ? 'visible' : 'auto'")
    end
  end

  describe 'the uncompilable family — the emit has to be a program' do
    # `step` is deliberately absent: the SSoT declares it `number` with no
    # `binding`, so the typed read drops a bound value before the converter
    # ever sees one. The emitter is still on that call site, which costs
    # nothing and is already correct if the declaration ever gains `binding`.
    it 'emits a bound Slider bound as a JSX expression, not min={@{v}}' do
      out = convert({ 'type' => 'Slider', 'minimum' => '@{lo}', 'maximum' => '@{hi}', 'step' => 5 },
                    RjuiTools::React::Converters::SliderConverter)
      expect(out).not_to include('@{')
      expect(out).to include('min={data.lo}')
      expect(out).to include('max={data.hi}')
      expect(out).to include('step={5}')
    end

    it 'does not raise when autoShrink meets a bound minimumScaleFactor' do
      expect { label('autoShrink' => true, 'minimumScaleFactor' => '@{f}', 'fontSize' => 16) }
        .not_to raise_error
    end
  end

  describe 'state colours — the one family the inline style cannot take directly' do
    it 'routes a bound tapBackground through a custom property the variant reads back' do
      out = convert({ 'type' => 'Button', 'text' => 'Go', 'tapBackground' => '@{c}' },
                    RjuiTools::React::Converters::ButtonConverter)
      expect(out).not_to include('@{')
      expect(out).to include('hover:bg-[var(--jui-tap-bg)]')
      expect(out).to include('active:bg-[var(--jui-tap-bg)]')
      expect(out).to include("'--jui-tap-bg': ColorManager.resolveColor(data.c)")
    end

    it 'asserts React.CSSProperties so a custom property does not fail the consumer tsc' do
      out = convert({ 'type' => 'Button', 'text' => 'Go', 'tapBackground' => '@{c}' },
                    RjuiTools::React::Converters::ButtonConverter)
      expect(out).to include('as React.CSSProperties')
    end

    it 'routes a bound TextField hintColor through the placeholder variant' do
      out = convert({ 'type' => 'TextField', 'hintColor' => '@{c}' },
                    RjuiTools::React::Converters::TextFieldConverter)
      expect(out).not_to include('@{')
      expect(out).to include('placeholder-[var(--jui-hint-color)]')
    end

    it 'gives the Switch track and knob their own inline colour' do
      out = convert({ 'type' => 'Switch', 'thumbTintColor' => '@{t}', 'onTintColor' => '@{on}' },
                    RjuiTools::React::Converters::SwitchConverter)
      expect(out).not_to include('bg-[@{')
      expect(out).to include('peer-checked:bg-[var(--jui-switch-on)]')
      expect(out).to include('backgroundColor: ColorManager.resolveColor(data.t)')
    end
  end

  describe 'enum values that need translating at runtime' do
    it 'maps a bound contentMode to object-fit rather than freezing on contain' do
      out = convert({ 'type' => 'Image', 'src' => 'a.png', 'contentMode' => '@{m}' },
                    RjuiTools::React::Converters::ImageConverter)
      expect(out).not_to include('@{')
      expect(out).to include("objectFit: (({ 'fit': 'contain'")
      expect(out).to include('String(data.m).toLowerCase()')
    end

    # Most CSS properties are unions of string literals in React.CSSProperties,
    # so a runtime string is TS2322 there. The assertion is written in terms of
    # the property's own type so it tracks the React types instead of restating
    # a union that would drift. Found by lane D running the bound fixtures
    # through the host's tsc — codegen-effect cannot see it, because the probe
    # only asks whether `@{` survived, never whether the emit typechecks.
    it 'asserts a bound textAlign into the property type' do
      out = label('textAlign' => '@{a}')
      expect(out).to include("textAlign: (data.a) as React.CSSProperties['textAlign']")
    end

    it 'asserts a bound objectFit into the property type' do
      out = convert({ 'type' => 'Image', 'src' => 'a.png', 'contentMode' => '@{m}' },
                    RjuiTools::React::Converters::ImageConverter)
      expect(out).to include("as React.CSSProperties['objectFit']")
    end

    # NetworkImage takes contentMode as a PROP and derives its own object-fit
    # from it; NetworkImageProps has no `style` at all, so writing one there is
    # TS2322 on the element.
    it 'leaves a bound NetworkImage contentMode to the prop, not an inline style' do
      out = convert({ 'type' => 'NetworkImage', 'src' => 'a.png', 'contentMode' => '@{m}' },
                    RjuiTools::React::Converters::NetworkImageConverter)
      expect(out).not_to include('objectFit')
      expect(out).to include("as React.ComponentProps<typeof NetworkImage>['contentMode']")
    end

    # A bound colour writes a `--jui-*` key, which React.CSSProperties does not
    # admit — every converter's style renderer has to assert. Six of them had
    # hand-copied the render loop and four copies had lost the assertion.
    it 'asserts React.CSSProperties wherever a custom property is written' do
      [[{ 'type' => 'TextField', 'hintColor' => '@{c}' }, RjuiTools::React::Converters::TextFieldConverter],
       [{ 'type' => 'TextView', 'hintColor' => '@{c}' }, RjuiTools::React::Converters::TextViewConverter],
       [{ 'type' => 'Label', 'text' => 'x', 'highlightColor' => '@{c}', 'selected' => '@{s}' },
        RjuiTools::React::Converters::LabelConverter]].each do |node, klass|
        expect(convert(node, klass)).to include('as React.CSSProperties'), "#{node['type']} lost the assertion"
      end
    end
  end

  describe 'presence-only attributes that now read their value' do
    it 'maps every declared TextView resize value to its own utility' do
      { 'none' => 'resize-none', 'both' => 'resize', 'horizontal' => 'resize-x', 'vertical' => 'resize-y' }
        .each do |value, utility|
          out = convert({ 'type' => 'TextView', 'resize' => value },
                        RjuiTools::React::Converters::TextViewConverter)
          expect(out).to include(utility), "resize: #{value.inspect} should emit #{utility}"
        end
    end
  end

  # The orchestrator's specificity question (plan 49 A adjudication): an inline
  # style always beats a class, so when a static class and a bound inline touch
  # the SAME CSS property the binding wins — for that property only. That is the
  # intended reading (the side that declared the binding wins) and it is pinned
  # here because it is the one place the two halves of the fix meet.
  describe 'a static class and a bound inline on the same property' do
    it 'keeps the static shorthand class and lets the bound side override one edge' do
      out = view('padding' => 8, 'topPadding' => '@{t}')

      expect(out).to include('p-2')
      expect(out).to include('paddingTop: `${data.t}px`')
    end
  end

  # The border ruling, pinned so it is not re-derived a fourth time.
  #
  # The PAIR requests a border; neither half does on its own, and there is no
  # default border colour. The ruling is a 2026-08-03 USER ruling recorded in
  # shared/core/attribute_semantics.json (`semantics.border`), whose five
  # `observable` entries `jui conformance gate --cross-effect` checks against
  # control_diff — so making any single declaration draw turns the next 3PF
  # measure red. `borderStyle`'s `"default": "solid"` in
  # attribute_definitions.json is the trap that has produced three reversals:
  # it proves style is a modifier, not that width is the summoner.
  describe 'border — the pair requests it, neither half does' do
    it 'draws when width and colour are both declared' do
      out = view('borderWidth' => 2, 'borderColor' => '#FF0000')
      expect(out).to include('border-2')
      expect(out).to include('border-[#FF0000]')
    end

    it 'draws nothing for a width with no colour — there is no default border colour' do
      expect(view('borderWidth' => 2)).not_to include('border')
    end

    it 'draws nothing for a colour with no width' do
      expect(view('borderColor' => '#FF0000')).not_to include('border')
    end

    it 'draws nothing for a style alone — it decorates a border, it never summons one' do
      expect(view('borderStyle' => 'dashed')).not_to include('border')
    end
  end

  # The other half of the contract, and the reason the change is safe: a value
  # with no binding in it takes the byte-identical path it always took.
  describe 'static values are untouched' do
    it 'still maps a numeric fontSize to a class and emits no style' do
      out = label('fontSize' => 16)
      expect(out).to include('text-base')
      expect(out).not_to include('style={{')
    end

    it 'still maps a numeric cornerRadius and spacing to classes' do
      out = view('cornerRadius' => 8, 'orientation' => 'horizontal', 'spacing' => 4)
      expect(out).to include('rounded-lg')
      expect(out).to include('gap-1')
      expect(out).not_to include('style={{')
    end

    it 'still bakes mx-auto for a literal centerHorizontal' do
      out = label('centerHorizontal' => true)
      expect(out).to include('mx-auto')
      expect(out).not_to include('marginInline')
    end
  end
end
