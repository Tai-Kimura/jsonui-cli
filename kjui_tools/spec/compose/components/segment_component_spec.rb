# frozen_string_literal: true

require 'core/bind_fold'
require 'compose/components/segment_component'
require 'compose/helpers/modifier_builder'
require 'compose/helpers/resource_resolver'

RSpec.describe KjuiTools::Compose::Components::SegmentComponent do
  let(:required_imports) { Set.new }

  before do
    allow(KjuiTools::Core::ConfigManager).to receive(:load_config).and_return({})
    allow(KjuiTools::Core::ProjectFinder).to receive(:get_full_source_path).and_return('/tmp')
    # Clear data definitions before each test
    KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {}
  end

  describe '.generate' do
    it 'generates Segment component' do
      json_data = {
        'type' => 'Segment',
        'items' => ['Tab 1', 'Tab 2']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Segment(')
      expect(required_imports).to include(:segment)
    end

    it 'generates Segment with static items' do
      json_data = {
        'type' => 'Segment',
        'items' => ['First', 'Second', 'Third']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('SegmentTab(')
      expect(result).to include('First')
      expect(result).to include('Second')
      expect(result).to include('Third')
    end

    # Inverted 2026-09-04. `segments` was an undeclared alias: absent from
    # attribute_definitions.json, read by no other face, used by no consumer
    # layout. This example asserted it worked; it now asserts it does not, so
    # the removal is pinned by the test that used to prove the opposite.
    it 'does not accept segments as an alias for items' do
      json_data = {
        'type' => 'Segment',
        'segments' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('"A"')
      expect(result).not_to include('"B"')
    end

    it 'generates nothing for a binding, which the declaration does not allow' do
      # This used to emit `data.segmentOptions.forEachIndexed` — a feature
      # only this face had. `Segment.items` is declared `type: "array"`
      # with no binding; sjui raised NoMethodError on the same input and
      # iOS dynamic takes strings only. Usage across seven faces: 0. The
      # validator names it; the generator emits no items.
      json_data = {
        'type' => 'Segment',
        'items' => '@{segmentOptions}'
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('forEachIndexed')
      expect(result).not_to include('segmentOptions')
      expect(result).to include('Segment(')
    end

    it 'generates Segment with static selectedIndex' do
      json_data = {
        'type' => 'Segment',
        'selectedIndex' => 1,
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      # The static index seeds the segment's own state; a tap writes it.
      expect(result).to include('var seeded by remember { mutableStateOf(1) }')
      expect(result).to include('selectedTabIndex = seeded,')
      expect(result).to include('seeded = 0')
      expect(result).to include('seeded = 1')
    end

    it 'generates Segment with dynamic selectedIndex binding' do
      json_data = {
        'type' => 'Segment',
        'selectedIndex' => '@{currentTab}',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('selectedTabIndex = data.currentTab')
    end

    it 'generates Segment with bind attribute' do
    # `bind` reaches the component folded (JsonUIShared::BindFold at the
    # dispatch, ComposeBuilder#generate_component); the component reads no bind.
      json_data = JsonUIShared::BindFold.fold({
        'type' => 'Segment',
        'bind' => '@{tabIndex}',
        'items' => ['A', 'B']
      })
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('selectedTabIndex = data.tabIndex')
    end

    it 'defaults selectedIndex to 0' do
      json_data = {
        'type' => 'Segment',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('var seeded by remember { mutableStateOf(0) }')
      expect(result).to include('selectedTabIndex = seeded,')
    end

    it 'generates Segment with enabled attribute' do
      json_data = {
        'type' => 'Segment',
        'enabled' => false,
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = false')
    end

    it 'generates Segment with enabled binding' do
      json_data = {
        'type' => 'Segment',
        'enabled' => '@{isEnabled}',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('enabled = (data.isEnabled ?: false)')
    end

    it 'draws a declared background as the track (containerColor)' do
      json_data = {
        'type' => 'Segment',
        'background' => '#EEEEEE',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('containerColor')
    end

    # The ruling 2026-11-15 (ticket jui-segment-android-draws-no-track, option (a)): with no
    # background the library's Segment draws iOS's track; each segment is a SegmentTab whose
    # label is on one line. It was containerColor = Color.Transparent and Material's Tab.
    # A Segment reads no cornerRadius (the requester's ruling 2026-11-16): its track and fill are
    # capsules on every platform, so a declared one, fixed or bound, is written nowhere.
    # Its border and shadow follow that capsule (the orchestrator's decision 2026-11-16), declared
    # corner or not: a RectangleShape outline sat square around the track.
    it "draws a Segment's border and shadow as capsules" do
      [nil, 4].each do |radius|
        node = { 'type' => 'Segment', 'items' => %w[A B], 'borderColor' => '#FF0000', 'borderWidth' => 2,
                 'shadow' => '#000000|0|2|0.5|4' }
        node['cornerRadius'] = radius if radius
        imports = Set.new
        result = described_class.generate(node, 0, imports)
        expect(result).to match(/\.border\(2\.dp, [^\n]*CircleShape\)/)
        expect(result).to match(/\.dropShadow\(shape = CircleShape/)
        expect(result).not_to match(/RectangleShape|RoundedCornerShape/)
        expect(imports).to include(:circle_shape)
      end
    end

    it "writes no cornerRadius for a Segment, declared or bound" do
      [8, '@{r}'].each do |radius|
        result = described_class.generate({ 'type' => 'Segment', 'items' => %w[A B], 'cornerRadius' => radius }, 0, required_imports)
        expect(result).not_to include('cornerRadius')
        expect(result).not_to include('RoundedCornerShape')
      end
    end

    it "leaves the track to the library when no background is written, and writes one-line SegmentTabs" do
      result = described_class.generate({ 'type' => 'Segment', 'items' => %w[A B] }, 0, required_imports)
      expect(result).not_to include('containerColor')
      expect(result.scan('SegmentTab(').size).to eq(2)
      expect(result).not_to match(/(?<!Segment)Tab\(/)
      expect(result.scan('maxLines = 1, overflow = TextOverflow.Ellipsis').size).to eq(2)
    end

    it 'generates Segment with fontColor' do
      json_data = {
        'type' => 'Segment',
        'fontColor' => '#666666',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('contentColor')
    end

    it 'generates Segment with selectedFontColor' do
      json_data = {
        'type' => 'Segment',
        'selectedFontColor' => '#007AFF',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('selectedContentColor')
    end

    # tintColor is the SELECTED segment's accent on every platform; on Compose
    # that is the TabRow indicator, not the label (contract:
    # semantics.segmentLabelColors → tintColorAlignment).
    it 'generates Segment with tintColor' do
      json_data = {
        'type' => 'Segment',
        'tintColor' => '#FF0000',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('indicatorColor')
      expect(result).not_to include('selectedContentColor')
    end

    # indicatorColor was an undeclared second spelling of the same slot and is
    # no longer read — tintColor is the declared one.
    it 'ignores the undeclared indicatorColor spelling' do
      json_data = {
        'type' => 'Segment',
        'indicatorColor' => '#0000FF',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).not_to include('indicatorColor')
    end

    it 'generates Segment with onValueChange handler' do
      json_data = {
        'type' => 'Segment',
        'onValueChange' => '@{handleTabChange}',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('data.handleTabChange?.invoke()')
    end

    it 'generates update when binding is set' do
      json_data = {
        'type' => 'Segment',
        'selectedIndex' => '@{tab}',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('viewModel.updateData(mapOf("tab" to')
    end

    it 'applies size modifiers' do
      json_data = {
        'type' => 'Segment',
        'width' => 'matchParent',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.fillMaxWidth()')
    end

    it 'applies padding modifiers' do
      json_data = {
        'type' => 'Segment',
        'padding' => 16,
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('.padding(16.dp)')
    end

    it 'handles conditional text color for static index' do
      json_data = {
        'type' => 'Segment',
        'selectedIndex' => 0,
        'selectedFontColor' => '#FF0000',
        'fontColor' => '#999999',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('Text(')
      expect(result).to include('color =')
    end

    it 'handles conditional text color for dynamic index' do
      json_data = {
        'type' => 'Segment',
        'selectedIndex' => '@{tab}',
        'selectedFontColor' => '#FF0000',
        'fontColor' => '#999999',
        'items' => ['A', 'B']
      }
      result = described_class.generate(json_data, 0, required_imports)
      expect(result).to include('if (data.tab')
    end
  end

  describe '.indent' do
    it 'returns text unchanged for level 0' do
      result = described_class.send(:indent, 'text', 0)
      expect(result).to eq('text')
    end

    it 'adds indentation for level 1' do
      result = described_class.send(:indent, 'text', 1)
      expect(result).to eq('    text')
    end
  end

  describe 'event handler invocation' do
    it 'generates invoke() without arguments when handler type is () -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '(() -> Unit)?' }
      }

      json_data = {
        'type' => 'Segment',
        'id' => 'tabSegment',
        'items' => ['Tab1', 'Tab2'],
        'selectedIndex' => '@{selectedTab}',
        'onValueChange' => '@{onTabChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTabChange?.invoke()')
      expect(result).not_to include('invoke("tabSegment"')
    end

    it 'generates invoke(viewId, value) when handler type is (Event) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Segment',
        'id' => 'tabSegment',
        'items' => ['Tab1', 'Tab2'],
        'selectedIndex' => '@{selectedTab}',
        'onValueChange' => '@{onTabChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTabChange?.invoke("tabSegment", 0)')
      expect(result).to include('data.onTabChange?.invoke("tabSegment", 1)')
    end

    it 'generates invoke(viewId, value) when handler type is (String, Int) -> Unit' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '((String, Int) -> Unit)?' }
      }

      json_data = {
        'type' => 'Segment',
        'id' => 'categorySegment',
        'items' => ['All', 'Active', 'Completed'],
        'onValueChange' => '@{onTabChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTabChange?.invoke("categorySegment", 0)')
      expect(result).to include('data.onTabChange?.invoke("categorySegment", 1)')
      expect(result).to include('data.onTabChange?.invoke("categorySegment", 2)')
    end

    it 'includes both viewModel.updateData and handler invocation when both binding and handler exist' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '((String, Int) -> Unit)?' }
      }

      json_data = {
        'type' => 'Segment',
        'id' => 'tabSegment',
        'items' => ['Tab1', 'Tab2'],
        'selectedIndex' => '@{selectedTab}',
        'onValueChange' => '@{onTabChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('viewModel.updateData')
      expect(result).to include('data.onTabChange?.invoke("tabSegment", 0)')
    end

    it 'uses its position as the viewId when no id is specified (LayoutPath.view_id; it was the kind word)' do
      KjuiTools::Compose::Helpers::ResourceResolver.data_definitions = {
        'onTabChange' => { 'name' => 'onTabChange', 'class' => '((Event) -> Unit)?' }
      }

      json_data = {
        'type' => 'Segment',
        'items' => ['A', 'B'],
        'onValueChange' => '@{onTabChange}'
      }

      result = described_class.generate(json_data, 0, required_imports)

      expect(result).to include('data.onTabChange?.invoke("segment_0", 0)')
    end

    # fontColor is the unselected label and selectedFontColor the selected one,
    # falling back to fontColor (contract: semantics.segmentLabelColors). The
    # legacy normalColor / selectedColor spellings resolve behind them.
    describe 'label colours' do
      it 'fills contentColor from fontColor' do
        result = described_class.generate(
          { 'type' => 'Segment', 'items' => %w[A B], 'fontColor' => '#0000FF' }, 0, required_imports
        )

        expect(result).to include('contentColor =')
      end

      it 'fills selectedContentColor from selectedFontColor' do
        result = described_class.generate(
          { 'type' => 'Segment', 'items' => %w[A B], 'selectedFontColor' => '#00FF00' }, 0, required_imports
        )

        expect(result).to include('selectedContentColor =')
      end

      it 'sends tintColor to the selected background, not the label' do
        result = described_class.generate(
          { 'type' => 'Segment', 'items' => %w[A B], 'tintColor' => '#FF0000' }, 0, required_imports
        )

        expect(result).to include('indicatorColor =')
        expect(result).not_to include('selectedContentColor =')
      end

      it 'leaves the alias spellings to the normalizer' do
        result = described_class.generate(
          { 'type' => 'Segment', 'items' => %w[A B], 'normalColor' => '#0000FF' }, 0, required_imports
        )

        expect(result).not_to include('contentColor = Color(0xFF0000FF)')
      end
    end
  end
  # It reached the screen as `Text("{\"label\"=>\"opt_a\", …}")` in Compose
  # (measured 2026-09-04). The declaration says static labels and the
  # dynamic runtime keeps primitives only (DynamicSegmentComponent
  # mapNotNull), so the generator was the only layer that disagreed.
  describe 'an object item (undeclared)' do
    let(:json) do
      { 'type' => 'Segment', 'id' => 'seg',
        'items' => ['Tab 1', { 'label' => 'opt_a', 'value' => 'a' }, 'Tab 3'] }
    end

    it 'emits no hash for it' do
      code = described_class.generate(json, 0)
      expect(code).not_to include('=>')
      expect(code).not_to include('label')
    end

    it 'still emits the declared items' do
      # The control: one dropped element must not drop the others.
      code = described_class.generate(json, 0)
      expect(code).to include('Tab 1')
      expect(code).to include('Tab 3')
    end
  end

end
