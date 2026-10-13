# frozen_string_literal: true

require 'json'
require_relative '../../lib/react/responsive_helper'
require_relative '../../lib/react/react_generator'

# Every face draws ONE key of a responsive block: the first of
# shared/core/responsive_resolver.rb's PRIORITY_ORDER that is in the block and
# holds, alone on the base (the codegens' if / else if chains, both Dynamic
# runtimes). The web writes classes, and CSS applies every class whose
# condition holds — so each key's classes must hold exactly where that key
# wins, or two keys' overrides stack:
#
# - rjui-responsive-medium-classes-hold-on-regular-windows: `md:` holds from
#   768px up, so a medium override also applied on a regular window
#   (measured in Chromium with Tailwind v4: regular window, {medium: padding
#   4, regular: spacing 24} drew padding 4).
# - rjui-responsive-landscape-classes-stack-on-breakpoint-classes: a landscape
#   key's classes are runtime-conditional and the size classes' are
#   breakpoint-prefixed, so both held on a regular landscape window, and
#   landscape beside regular-landscape stacked too.
#
# The arm reads what rjui wrote — the className of a node, prefixes and
# `${cond ? "…" : ""}` fragments — evaluates it in a window, and asks whose
# classes hold. Each key carries its own marker class (cornerRadius), so a
# key's classes are told apart by the marker alone.
RSpec.describe RjuiTools::React::ResponsiveHelper, 'one key wins on the web' do
  KEYS = %w[regular-landscape medium-landscape compact-landscape landscape regular medium compact].freeze unless defined?(KEYS)
  # Radii Tailwind has no name for, so each is written `rounded-[Npx]`
  # (12 is `rounded-xl`, 16 `rounded-2xl`).
  MARKERS = [13, 14, 15, 17, 18, 19, 21].freeze unless defined?(MARKERS)

  # Windows across the bands, both orientations: [width, landscape].
  let(:windows) { [[500, false], [500, true], [900, false], [900, true], [1100, false], [1100, true]] }

  def band(width)
    return 'compact' if width < 768
    return 'medium' if width < 1024

    'regular'
  end

  # The resolver's answer (shared/core/responsive_resolver.rb): the first key
  # of PRIORITY_ORDER in the block whose width band and orientation hold.
  def winner(keys, width, landscape)
    JsonUIShared::ResponsiveResolver::PRIORITY_ORDER.find do |key|
      next false unless keys.include?(key)

      parsed = JsonUIShared::ResponsiveResolver.parse_size_class(key)
      (parsed[:width].nil? || parsed[:width] == band(width)) && (!parsed[:landscape] || landscape)
    end
  end

  # Whether a Tailwind v4 viewport prefix chain (`md:max-lg:`, `max-md:`,
  # `lg:`, `min-[700px]:`) holds at `width`.
  def prefix_holds?(prefix, width)
    prefix.scan(/([a-z\-\[\]0-9px]+):/).flatten.all? do |variant|
      case variant
      when 'md' then width >= 768
      when 'lg' then width >= 1024
      when 'max-md' then width < 768
      when 'max-lg' then width < 1024
      when /\Amin-\[(\d+)px\]\z/ then width >= Regexp.last_match(1).to_i
      when /\Amax-\[(\d+)px\]\z/ then width < Regexp.last_match(1).to_i
      else raise "unread variant #{variant}"
      end
    end
  end

  # A `${…}` fragment's condition: isLandscape / isMinMd / isMinLg with !, &&,
  # || and parentheses (what rjui writes), read as a boolean in the window.
  def condition_holds?(condition, width, landscape)
    values = { 'isLandscape' => landscape, 'isMinMd' => width >= 768, 'isMinLg' => width >= 1024 }
    ruby = condition.gsub(/[A-Za-z]+/) do |name|
      raise "unread name #{name} in #{condition}" unless values.key?(name)

      values[name].to_s
    end
    raise "unread condition #{condition}" unless ruby.match?(/\A[\s!&|()truefals]*\z/)

    eval(ruby) # rubocop:disable Security/Eval -- only true / false / ! && || ( ) reach here
  end

  # The classes of `class_name` (as rjui wrote it) that apply in the window.
  def applied(class_name, width, landscape)
    classes = []
    rest = class_name.gsub(/\$\{([^?]*?) \? "(.*?)" : ""\}/) do
      classes.concat(Regexp.last_match(2).split) if condition_holds?(Regexp.last_match(1), width, landscape)
      ''
    end
    rest.split.each do |cls|
      prefix = cls[/\A((?:[a-z\-]+(?:\[\d+px\])?:)*)/, 1]
      classes << cls.delete_prefix(prefix) if prefix.empty? || prefix_holds?(prefix, width)
    end
    classes
  end

  def class_name_for(keys)
    node = { 'type' => 'View', 'id' => 'probe', 'orientation' => 'vertical', 'padding' => 8,
             'responsive' => keys.each_with_index.to_h { |k, i| [k, { 'cornerRadius' => MARKERS[i] }] },
             'child' => [{ 'type' => 'View', 'id' => 'a' }] }
    tsx = RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true })
                                          .generate('Probe', { 'type' => 'View', 'id' => 'root', 'child' => [node] }, screen_id: 'probe')
    line = tsx.lines.find { |l| l.include?('id="probe"') }
    line[/className=\{`(.*?)`\}/, 1] || line[/className="(.*?)"/, 1]
  end

  def holding_keys(keys, width, landscape)
    on = applied(class_name_for(keys), width, landscape)
    keys.each_with_index.select { |_, i| on.include?("rounded-[#{MARKERS[i]}px]") }.map(&:first)
  end

  def misses_for(blocks)
    blocks.flat_map do |keys|
      windows.filter_map do |width, landscape|
        held = holding_keys(keys, width, landscape)
        expected = [winner(keys, width, landscape)].compact
        "#{keys.inspect} at #{width}px #{landscape ? 'landscape' : 'portrait'}: #{held.inspect}, expected #{expected.inspect}" if held != expected
      end
    end
  end

  it 'reads its own markers: one key alone holds where it holds' do
    expect(holding_keys(['regular'], 1100, false)).to eq(['regular'])
    expect(holding_keys(['regular'], 900, false)).to eq([])
    expect(holding_keys(['landscape'], 500, true)).to eq(['landscape'])
  end

  it 'size classes: every pair, in every window, holds the one winner' do
    pairs = %w[regular medium compact].combination(2).to_a + [%w[compact medium regular]]
    misses = misses_for(pairs)
    expect(misses).to be_empty, "#{misses.size} misses:\n#{misses.join("\n")}"
  end

  it 'with landscape keys: every pair of the seven, and the triples with landscape, hold the one winner' do
    pairs = KEYS.combination(2).select { |pair| pair.any? { |k| k.include?('landscape') } }
    triples = [%w[landscape regular compact], %w[landscape regular-landscape regular], %w[compact-landscape medium-landscape landscape]]
    misses = misses_for(pairs + triples)
    expect(misses).to be_empty, "#{misses.size} misses:\n#{misses.join("\n")}"
  end
  it 'writes a screen that compiles with a run-time block of every kind of key', :typescript_compile do
    layout = { 'type' => 'View', 'id' => 'root', 'child' => [
      { 'type' => 'View', 'id' => 'probe', 'orientation' => 'vertical', 'padding' => 8,
        'responsive' => { 'landscape' => { 'padding' => 2 }, 'medium-landscape' => { 'spacing' => 4 },
                          'regular' => { 'padding' => 16 }, 'medium' => { 'orientation' => 'horizontal' },
                          'compact' => { 'cornerRadius' => 13 } },
        'child' => [{ 'type' => 'View', 'id' => 'a' }] },
      { 'type' => 'View', 'id' => 'bands', 'responsive' => { 'medium' => { 'padding' => 4 }, 'regular' => { 'padding' => 16 } } }
    ] }
    screen = RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true })
                                             .generate('Home', layout, screen_id: 'home')
    expect(screen).to include('(!isMinMd || isMinLg)', 'md:max-lg:p-')
    template = File.read(File.expand_path('../../lib/react/templates/use_media_query.ts', __dir__))
    signature = template[/^export function useMediaQuery\(([^)]*)\): (\w+)/]
    expect(screen.lines.reject { |l| l.start_with?('import ') }.join).to compile_as_typescript.with_ambient(<<~TS)
      #{signature.sub('export function', 'declare function')};
      interface HomeData {}
      declare function createHomeData(): HomeData;
      declare function useStringManager(): Record<string, string>;
      declare function screenMarker(screenId: string): Record<string, string>;
    TS
  end
end
