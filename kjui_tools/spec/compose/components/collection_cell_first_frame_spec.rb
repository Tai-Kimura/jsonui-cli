# frozen_string_literal: true

require 'set'
require 'tmpdir'
require_relative '../../../lib/compose/components/collection_component'
require_relative '../../../lib/compose/generators/cell_generator'
require_relative '../../support/kotlin_compiler'
require_relative '../../support/compose_bounded_scroll_stubs'
require_relative '../../support/collection_first_frame'

# A Collection cell (and a section header / footer) is composed with its own
# data from its first frame. Each one gets its ViewModel from
# `viewModel(key = …)`, which makes a fresh one for a key it has not seen: a
# cell composed for the first time, or — under autoChangeTrackingId, whose
# key carries a hash of the cell's contents — a cell whose data changed.
# Until this change the ViewModel was fed only by `LaunchedEffect(data) {
# updateData(data) }`, which runs after the frame is composed, so that frame
# drew the cell from its layout's defaults (measured on an emulator: a cell
# with a label its data hides drew taller for exactly one frame on every data
# change, and in a reverseLayout list every row above it moved).
#
# Every site now seeds the ViewModel in composition, before the view
# (CollectionComponent.seed_view_model_line), and keeps the LaunchedEffect.
#
# The run arm COMPILES the emitted routes with kotlinc and RUNS them on the
# JVM against stubs that keep Compose's timing: a frame composes the body;
# a LaunchedEffect's block is queued and runs only after that frame (and
# again only when its key changes); `remember` keeps its value per call
# position while its keys are equal; `viewModel(key)` keeps one ViewModel per
# key. Each view prints what its ViewModel holds when it composes — its
# letter and the row's id, `-` for none. A green says the emitted code hands
# the view its data before the view composes, against these stubs.
RSpec.describe 'kjui codegen: a Collection cell composes with its own data from its first frame' do
  include CollectionFirstFrame
  FIRST_FRAME_SECTIONS = [{ 'cell' => 'ACell', 'header' => 'HCell', 'footer' => 'FCell' }, { 'cell' => 'BCell', 'header' => 'HCell' }].freeze

  FIRST_FRAME_ROUTES = {
    'list' => {},
    'lazyNone' => { 'lazy' => 'none' },
    'wrapContent' => { 'height' => 'wrapContent' },
    'grid' => { 'columns' => 2 },
    'gridLazyNone' => { 'columns' => 2, 'lazy' => 'none' },
    'tracked' => { 'cellIdProperty' => 'id', 'autoChangeTrackingId' => true },
    'trackedGrid' => { 'columns' => 2, 'cellIdProperty' => 'id', 'autoChangeTrackingId' => true },
    'keyed' => { 'cellIdProperty' => 'id' },
    'flow' => { 'layout' => 'flow' },
    'flowCentred' => { 'layout' => 'flow', 'flowAlignment' => 'center' },
    'flowAtTheEnd' => { 'layout' => 'flow', 'flowAlignment' => 'trailing' },
    'row' => { 'layout' => 'horizontal', 'lazy' => 'none' },
    'paging' => { 'layout' => 'horizontal', 'paging' => true },
    'classList' => { 'sections' => nil, 'cellClasses' => ['ACell'], 'headerClasses' => ['HCell'], 'footerClasses' => ['FCell'] },
    # A reorderable Collection (ticket jui-collection-drag-to-reorder): each row is a CollectionReorderRow, the
    # Collection the container — the cells are drawn as on the same route without it.
    'lazyNoneReorder' => { 'lazy' => 'none', 'cellIdProperty' => 'id', 'reorderable' => '@{editing}', 'onReorder' => '@{onMove}',
                           'reorderLockedProperty' => 'fixed' },
    'listReorder' => { 'reorderable' => true, 'onReorder' => '@{onMove}' },
    'keyedListReorder' => { 'cellIdProperty' => 'id', 'reorderable' => true, 'onReorder' => '@{onMove}' },
    'wrapContentReorder' => { 'height' => 'wrapContent', 'reorderable' => true, 'onReorder' => '@{onMove}' },
    'classListReorder' => { 'sections' => nil, 'cellClasses' => ['ACell'], 'headerClasses' => ['HCell'], 'footerClasses' => ['FCell'],
                            'reorderable' => true, 'onReorder' => '@{onMove}' },
    'classListNoneReorder' => { 'sections' => nil, 'cellClasses' => ['ACell'], 'lazy' => 'none', 'reorderable' => '@{editing}',
                                'onReorder' => '@{onMove}', 'reorderLockedProperty' => 'fixed' }
  }.freeze

  def emit(extra)
    %i[info debug warn].each { |m| allow(KjuiTools::Core::Logger).to receive(m) }
    node = { 'type' => 'Collection', 'id' => 'list', 'items' => '@{rows}', 'sections' => FIRST_FRAME_SECTIONS }.merge(extra).compact
    ComposeBoundedScrollStubs.unqualify(KjuiTools::Compose::Components::CollectionComponent.generate(node, 1, Set.new, nil))
  end

  # The stub universe, the scaffolded cells (`kjui g cell`'s signatures; a
  # view prints what its ViewModel holds when it composes) and program / run:
  # spec/support/collection_first_frame.rb.
  #
  # Per route, one line of frames separated by ` | `:
  #   1. the first frame;
  #   2. the next frame, after the first one's effects ran;
  #   3. a frame after a cell's own write to its ViewModel, the data unchanged;
  #   4. a frame with every row's data changed (its id gains `'`).

  def routes
    FIRST_FRAME_ROUTES.transform_values { |extra| emit(extra) }
  end

  it 'every site seeds its ViewModel in composition, before its view and ahead of the LaunchedEffect it keeps' do
    FIRST_FRAME_ROUTES.each do |route, extra|
      code = emit(extra)
      # (The class-list shape's header / footer has no data to feed: its view
      # follows its ViewModel line directly.)
      fed = code.scan(/^\s*val (\w+ViewModel): \w+ViewModel = viewModel\(key = .*\n\s*(.*)\n\s*(.*)\n/)
                .reject { |_, next_line, _| next_line.start_with?('Box(') }
      expect(fed).not_to be_empty, route
      fed.each do |vm, seed, effect|
        expect(seed).to match(/\Aremember\(#{vm}, ([\w.]+)\) \{ #{vm}\.updateData\(\1\); \1 \}\z/), "#{route}: #{seed}"
        data = seed[/\Aremember\(#{vm}, ([\w.]+)\)/, 1]
        expect(effect).to start_with("LaunchedEffect(#{data}) {"), "#{route}: #{effect}"
      end
      expect(code.scan('.updateData(').size).to eq(fed.size * 2), route
    end
    # Every emitted feed in the component is seeded: each LaunchedEffect
    # that updates a ViewModel follows a seed_view_model_line.
    source = File.read(File.expand_path('../../../lib/compose/components/collection_component.rb', __dir__)).lines
    feeds = source.each_index.select do |i|
      source[i].include?('indent("LaunchedEffect(') && (source[i] + source[i + 1].to_s).match?(/ViewModel\.updateData\(/)
    end
    expect(feeds.size).to eq(18)
    feeds.each { |i| expect(source[i - 1]).to include('seed_view_model_line('), "line #{i + 1}: #{source[i]}" }
  end

  it 'every route compiles (the compile arm; the run below compiles it again to run it)' do
    expect(program(routes)).to compile_as_kotlin
  end

  it 'the first frame draws every cell, header and footer with its own data, and later frames follow the data' do
    frames = run(routes)
    frames.each do |route, line|
      # The class-list shape's header / footer carry no data (its section has
      # none to give them): its cells are what it feeds.
      line = line.split(' | ').map { |f| f.split.grep_v(/\A[HF]-\z/).join(' ') }.join(' | ') if route.start_with?('classList')
      f1, f2, f3, f4 = line.split(' | ')
      # 1. No view composed from its ViewModel's defaults.
      expect(f1).not_to include('-'), "#{route}: #{line}"
      # 2. The effects that ran after it changed nothing.
      expect(f2).to eq(f1), "#{route}: #{line}"
      # 3. A recomposition with the same data leaves a cell's own write alone
      #    (the seed runs per new ViewModel or new data only).
      expect(f3.split.grep(/\AA/).uniq).to eq(['Aown']), "#{route}: #{line}"
      # 4. New data is drawn in the frame that brings it — a reused
      #    ViewModel (same key) or a new one (autoChangeTrackingId's key).
      expect(f4.split.reject { |t| t == '/' }).to all(end_with("'")), "#{route}: #{line}"
    end
    expect(frames['list'].split(' | ').first).to eq('Hh Aa0 Aa1 Ff Hh Bb0 / Hh Aa0 Aa1 Ff Hh Bb0')
    expect(frames['paging'].split(' | ').first).to eq('Aa0 Aa1 Bb0')
    expect(frames['classList'].split(' | ').first).to eq('H- Aa0 Aa1 Ab0 F-')
    expect(frames.keys).to match_array(FIRST_FRAME_ROUTES.keys)
  end

  it 'control: without the seed, the stubs show the first frame drawn from the defaults' do
    allow(KjuiTools::Compose::Components::CollectionComponent).to receive(:seed_view_model_line) { |_, _, depth| '    ' * depth + '// unseeded' }
    frames = run(FIRST_FRAME_ROUTES.slice('list', 'trackedGrid', 'paging').transform_values { |extra| emit(extra) })
    frames.each do |route, line|
      f1, f2, _f3, f4 = line.split(' | ')
      expect(f1.split.reject { |t| t == '/' }).to all(end_with('-')), "#{route}: #{line}"
      expect(f2).not_to include('-'), "#{route}: #{line}"
      # A re-keyed cell (autoChangeTrackingId) is a new ViewModel: its data
      # changed, and its frame drew the defaults again.
      expect(f4.split.grep(/\AA/)).to all(end_with('-')), "#{route}: #{line}" if route == 'trackedGrid'
    end
  end
end
