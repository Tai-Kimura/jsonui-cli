# frozen_string_literal: true

require 'json'
require_relative '../../lib/react/responsive_helper'
require_relative '../../lib/react/react_generator'

# Two things the web face draws by viewport width:
#
# 1. minWidth:N / maxWidth:N (jui-responsive-width-threshold-conditions). Each
#    key's classes are scoped to the band where it is the one that wins, so a
#    viewport holds exactly one key's classes — the key the shared vectors
#    name. Tailwind v4: min-[Npx] is `width >= N`, max-[Npx] is `width < N`.
# 2. A size class + landscape combination holds in its size class's band AND
#    in landscape (rjui-responsive-width-plus-landscape-drops-width-condition:
#    it was `isLandscape` alone).
RSpec.describe RjuiTools::React::ResponsiveHelper, 'width conditions and landscape combinations' do
  let(:vectors) do
    JSON.parse(File.read(File.expand_path('../../../shared/core/responsive_resolution_vectors.json', __dir__)))
  end

  # What a Tailwind v4 viewport-variant prefix (`min-[a]:max-[b]:`) says about
  # a width, read from the class itself.
  def band_holds?(prefix, width)
    lower = prefix[/min-\[(\d+)px\]:/, 1]
    upper = prefix[/max-\[(\d+)px\]:/, 1]
    (lower.nil? || width >= lower.to_i) && (upper.nil? || width < upper.to_i)
  end

  it 'scopes each width condition to the band where it wins' do
    component = { 'type' => 'View', 'responsive' => {
      'maxWidth:300' => { 'spacing' => 1 }, 'maxWidth:600' => { 'spacing' => 2 },
      'minWidth:600' => { 'spacing' => 3 }, 'minWidth:900' => { 'spacing' => 4 }
    } }
    expect(described_class.width_condition_prefixes(component)).to eq(
      'maxWidth:300' => 'max-[300px]:',
      'maxWidth:600' => 'min-[300px]:max-[600px]:',
      'minWidth:900' => 'min-[900px]:',
      'minWidth:600' => 'min-[600px]:max-[900px]:'
    )
    classes = described_class.build_responsive(component)[:classes]
    %w[max-[300px]: min-[300px]:max-[600px]: min-[600px]:max-[900px]: min-[900px]:].each do |prefix|
      expect(classes).to include(a_string_starting_with("#{prefix}gap-")), classes.inspect
    end
  end

  it 'holds exactly the classes of the key the shared vectors name, at every width case' do
    cases = vectors['cases'].select { |c| c['env'].key?('width') }
    expect(cases.size).to be >= 15
    cases.each do |c|
      component = { 'type' => 'View', 'responsive' => c['keys'].to_h { |k| [k, { 'spacing' => 1 }] } }
      prefixes = described_class.width_condition_prefixes(component)
      holding = prefixes.select { |_, prefix| band_holds?(prefix, c['env']['width']) }.keys
      expect(holding).to eq([c['winner']].compact), "#{c['name']}: #{prefixes}"
    end
  end

  it 'leaves size classes on their breakpoints' do
    component = { 'type' => 'View', 'responsive' => { 'regular' => { 'spacing' => 4 } } }
    expect(described_class.width_condition_prefixes(component)).to eq({})
    expect(described_class.build_responsive(component)[:classes]).to include(a_string_starting_with('lg:gap-'))
  end

  describe 'a size class + landscape combination' do
    # Media variants since jsonui-cli 2.3.30 (ResponsiveHelper.landscape_variants);
    # the run-time isLandscape / isMinMd / isMinLg hooks they replaced read the
    # same windows (measured in Chromium on 14 windows).
    it 'holds in its band and in landscape' do
      variants = ->(key) { described_class.send(:landscape_variants, key, [key]) }
      expect(variants.('landscape')).to eq(['landscape:'])
      expect(variants.('compact-landscape')).to eq(['landscape:max-md:'])
      expect(variants.('medium-landscape')).to eq(['landscape:md:max-lg:'])
      expect(variants.('regular-landscape')).to eq(['landscape:lg:'])
    end

    it 'writes a screen that compiles with the bands and the width classes', :typescript_compile do
      layout = {
        'type' => 'View', 'id' => 'root', 'orientation' => 'vertical', 'spacing' => 8,
        'responsive' => { 'regular-landscape' => { 'spacing' => 32 }, 'compact-landscape' => { 'spacing' => 4 } },
        'child' => [{ 'type' => 'View', 'id' => 'pane', 'spacing' => 2,
                      'responsive' => { 'maxWidth:700' => { 'spacing' => 1 }, 'minWidth:700' => { 'spacing' => 6 } },
                      'child' => [{ 'type' => 'Label', 'id' => 'title', 'text' => 'x' }] }]
      }
      screen = RjuiTools::React::ReactGenerator.new({ 'typescript' => true, 'use_tailwind' => true })
                                               .generate('Home', layout, screen_id: 'home')
      expect(screen).to include('landscape:lg:gap-', 'landscape:max-md:gap-')
      expect(screen).not_to include('isLandscape', 'useMediaQuery')
      expect(screen).to include('max-[700px]:gap-', 'min-[700px]:gap-')
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
end
