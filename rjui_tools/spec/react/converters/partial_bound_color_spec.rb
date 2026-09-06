# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/label_converter'
require 'react/converters/button_converter'
require 'react/tailwind_mapper'

# A bound colour inside `partialAttributes` is resolved at runtime, not
# turned into a Tailwind class name.
#
# `map_color` only knows `#hex` and palette keys, so `@{x}` reached it as a
# colors.json MISS: it warned once per layout and returned `text-@{x}` — a
# class no stylesheet defines, on every build, forever. The same Label's
# TOP-LEVEL `fontColor` was already correct, going through
# `color_style_expr` -> `ColorManager.resolveColor`, so the two halves of one
# attribute disagreed about what a binding means.
#
# The runtime needed nothing: `PartialSpec` already declares `style`, and
# partialText already merges it onto the span. Only the emit side was wrong.
RSpec.describe 'a bound colour in partialAttributes' do
  let(:config) { { 'use_tailwind' => true } }

  # Both converters carry their OWN copy of build_partial_style /
  # build_partial_class — the defect was in both, and a fix to one would
  # leave the other emitting dead classes.
  CONVERTERS = {
    'Label' => RjuiTools::React::Converters::LabelConverter,
    'Button' => RjuiTools::React::Converters::ButtonConverter
  }.freeze

  def emit(klass, partial, type)
    klass.new({ 'type' => type, 'id' => 'target', 'text' => 'hello there',
                'partialAttributes' => [partial] }, config).convert
  end

  before do
    # Configured palette: without this `map_color` takes the "unconfigured"
    # legacy branch and returns the class silently, so the arm would pass
    # with the guard removed.
    RjuiTools::React::TailwindMapper.configure_palette(
      theme_safe: %w[accent surface], fallbacks: {}
    )
  end

  after { RjuiTools::React::TailwindMapper.reset_palette! }

  CONVERTERS.each do |type, klass|
    describe type do
      it 'resolves a bound fontColor at runtime instead of naming a class' do
        out = emit(klass, { 'range' => '@{r}', 'fontColor' => '@{c}' }, type)
        expect(out).to include('color: ColorManager.resolveColor(data.c)')
        expect(out).not_to include('text-@{')
      end

      it 'emits nothing at all for `background`, declared or bound' do
        # RULED 2026-09-07: dropped, not fixed. The SSoT declares no
        # `background` under partialAttributes on either component, the
        # validator already reports `Unknown property`, iOS never
        # implemented it, and no consumer layout uses one. Web reading it
        # was a reimplementation of an attribute that does not exist, so
        # neither channel may carry it.
        bound = emit(klass, { 'range' => '@{r}', 'background' => '@{b}' }, type)
        expect(bound).not_to include('backgroundColor')
        expect(bound).not_to include('bg-@{')

        static = emit(klass, { 'range' => '@{r}', 'background' => 'surface' }, type)
        expect(static).not_to include('backgroundColor')
        expect(static).not_to include('bg-surface')
      end

      it 'still maps a STATIC palette token to a class' do
        # The guard must be narrow: a literal token is what the class path
        # exists for, and L1 rewrites palette hex to a token, so moving
        # static colours inline would emit `color: 'accent'` — not CSS.
        out = emit(klass, { 'range' => '@{r}', 'fontColor' => 'accent' }, type)
        expect(out).to include('text-accent')
        expect(out).not_to include('ColorManager.resolveColor')
      end

      it 'does not warn about a binding as an off-palette colour' do
        warned = []
        allow(RjuiTools::React::TailwindMapper).to receive(:warn_off_palette) { |*a| warned << a }
        emit(klass, { 'range' => '@{r}', 'fontColor' => '@{c}', 'background' => '@{b}' }, type)
        expect(warned).to be_empty
      end

      it 'keeps a bound colour beside the other partial attributes' do
        # The regression this would hide: routing the colour to `style`
        # while dropping the class the same partial still needs.
        out = emit(klass, { 'range' => '@{r}', 'fontColor' => '@{c}',
                            'fontSize' => 14 }, type)
        expect(out).to include("fontSize: '14px'")
        expect(out).to include('color: ColorManager.resolveColor(data.c)')
      end
    end
  end

  it 'agrees with the top-level fontColor on the same Label' do
    # The asymmetry that made this a bug report rather than a preference:
    # one attribute, two answers, in one generated component.
    out = RjuiTools::React::Converters::LabelConverter.new(
      { 'type' => 'Label', 'id' => 'target', 'text' => '@{t}',
        'fontColor' => '@{c}',
        'partialAttributes' => [{ 'range' => '@{r}', 'fontColor' => '@{c}' }] },
      config
    ).convert
    expect(out.scan('ColorManager.resolveColor(data.c)').length).to eq(2)
  end
  # The emitted TSX reaches a compiler, not just a string match. A `style`
  # key that the runtime's PartialSpec does not accept, or a resolveColor
  # call with the wrong arity, is invisible to `include` and fatal in the
  # consumer build.
  #
  # PARTIAL_SPEC_TS below is the ambient the arm compiles against, and the
  # arm after it pins that this shape is the one `rjui build` actually
  # writes — an ambient I invent could accept output the real runtime
  # rejects, which is the failure mode a stub has.
  PARTIAL_SPEC_TS = <<~TS
    type CSSProperties = Record<string, string | number>;
    type PartialSpec = {
      range: [number, number] | string;
      style?: CSSProperties;
      className?: string;
      onClick?: () => void;
    };
    declare function partialText(text: string, partials: PartialSpec[]): JSX.Element;
    declare const ColorManager: { resolveColor(name: string): string };
    // NON-OPTIONAL on purpose: a `data` entry carrying `defaultValue` is
    // emitted as `bodyColor: string`, not `string | undefined` (checked
    // against a generated SampleData.ts). The first draft of this ambient
    // marked them optional and tsc rejected the emitted code — the STUB was
    // wrong, not the emit, which is exactly the failure a hand-written
    // ambient invites.
    declare const data: { r: string; c: string; b: string; t: string };
  TS

  it 'the emitted TSX type-checks against the real PartialSpec' do
    code = RjuiTools::React::Converters::LabelConverter.new(
      { 'type' => 'Label', 'id' => 'target', 'text' => '@{t}',
        'partialAttributes' => [{ 'range' => '@{r}', 'fontColor' => '@{c}',
                                  'background' => '@{b}' }] }, config
    ).convert

    expect(<<~TSX).to compile_as_typescript.with_ambient(PARTIAL_SPEC_TS)
      export const Emitted = (): JSX.Element => (
      #{code}
      );
    TSX
  end

  it 'the ambient above is the shape rjui build actually emits' do
    # Guards the arm before it: if the generated runtime stops declaring
    # `style`, compiling against a stub that still does would keep passing
    # while every consumer build broke.
    source = File.read(
      File.expand_path('../../../lib/cli/commands/build_command.rb', __dir__)
    )
    expect(source).to include('export type PartialSpec = {')
    expect(source).to include('style?: CSSProperties;')
    expect(source).to include('className?: string;')
  end
end
