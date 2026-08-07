# frozen_string_literal: true

require_relative '../spec_helper'
require 'react/react_generator'

RSpec.describe RjuiTools::React::ReactGenerator do
  let(:config) { { 'use_tailwind' => true, 'typescript' => true } }
  let(:generator) { described_class.new(config) }

  describe '#collect_lucide_icons' do
    it 'collects mapped icon names from TabView tabs' do
      json = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'Home', 'icon' => 'house' },
          { 'title' => 'Settings', 'icon' => 'gearshape' }
        ]
      }
      result = generator.send(:collect_lucide_icons, json).to_a.sort
      expect(result).to eq(%w[Home Settings])
    end

    it 'includes selectedIcon when present' do
      json = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'Home', 'icon' => 'house', 'selectedIcon' => 'house.fill' }
        ]
      }
      # Both 'house' and 'house.fill' map to 'Home' — de-duped by Set
      expect(generator.send(:collect_lucide_icons, json).to_a).to eq(['Home'])
    end

    it 'defaults missing icon to Circle (matches build_icon default)' do
      json = { 'type' => 'TabView', 'tabs' => [{ 'title' => 'Tab' }] }
      expect(generator.send(:collect_lucide_icons, json).to_a).to eq(['Circle'])
    end

    it 'skips iconType: resource tabs entirely' do
      json = {
        'type' => 'TabView',
        'tabs' => [
          { 'title' => 'Learn', 'iconType' => 'resource', 'icon' => 'learn' }
        ]
      }
      expect(generator.send(:collect_lucide_icons, json).to_a).to be_empty
    end

    it 'recurses into nested children' do
      json = {
        'type' => 'View',
        'child' => [
          {
            'type' => 'View',
            'child' => [
              { 'type' => 'TabView', 'tabs' => [{ 'title' => 'X', 'icon' => 'bell' }] }
            ]
          }
        ]
      }
      expect(generator.send(:collect_lucide_icons, json).to_a).to eq(['Bell'])
    end

    it 'returns an empty set when no TabView is present' do
      json = { 'type' => 'View', 'child' => [{ 'type' => 'Label', 'text' => 'hi' }] }
      expect(generator.send(:collect_lucide_icons, json).to_a).to be_empty
    end
  end

  describe '#generate sets _current_json_name for StringManager scoping' do
    # Use a minimal View so generate returns quickly. The ASSERTion is about
    # the side effect on config['_current_json_name'], which StringManagerHelper
    # reads to scope bare key lookups to the current screen's namespace.
    let(:minimal_json) { { 'type' => 'View' } }

    it 'converts PascalCase component name to snake_case when no subdir is passed' do
      generator.generate('Installation', minimal_json)
      expect(config['_current_json_name']).to eq('installation')
    end

    it 'prepends subdir segments to form a directory-qualified namespace' do
      generator.generate('Installation', minimal_json, subdir: 'learn')
      expect(config['_current_json_name']).to eq('learn_installation')
    end

    it 'flattens multi-level subdir into underscore-joined namespace' do
      generator.generate('Advanced', minimal_json, subdir: 'learn/deep')
      expect(config['_current_json_name']).to eq('learn_deep_advanced')
    end

    it 'downcases every subdir part' do
      generator.generate('Page', minimal_json, subdir: 'Learn/Topic')
      expect(config['_current_json_name']).to eq('learn_topic_page')
    end

    it 'ignores empty subdir gracefully' do
      generator.generate('Home', minimal_json, subdir: '')
      expect(config['_current_json_name']).to eq('home')
    end

    it 'ignores File.dirname sentinel `.` for root-level layouts' do
      # build_command.rb passes `File.dirname(relative_path)` as the subdir.
      # For a root-level layout that returns the string "." — without this
      # guard the namespace becomes `._learn_index` and Phase 2 of
      # StringManager lookup can never match the strings.json namespace.
      generator.generate('LearnIndex', minimal_json, subdir: '.')
      expect(config['_current_json_name']).to eq('learn_index')
    end

    it 'strips leading `.` while keeping real subdir parts' do
      generator.generate('Index', minimal_json, subdir: './learn')
      expect(config['_current_json_name']).to eq('learn_index')
    end
  end

  describe '#generate_component_file StringManager import emission' do
    # `uses_string_manager?(json)` only inspects a hard-coded attribute
    # whitelist (text / hint / placeholder / label / title / src / url),
    # so it misses snake_case values on custom component props (e.g.
    # `TopBar brandLabel="chrome_brand_name"` — `brandLabel` is not in
    # the whitelist). The scaffold-generated converter emits
    # `StringManager.currentLanguage.xxx` for those props anyway via
    # `convert_string_key`, so the downstream JSX references the global
    # but the file header's `import { useStringManager } …` would be
    # missing — TS `TS2304: Cannot find name '$s'`.
    #
    # The fix: also scan the already-converted `jsx_content` for
    # `StringManager.` so any converter path that lands a reference
    # in the JSX stream gets its import emitted AND the reference
    # rewritten to `$s.` (the subscribed snapshot).
    let(:minimal_json) { { 'type' => 'View' } }

    it 'emits the useStringManager import + $s declaration and rewrites references when jsx_content contains a StringManager reference (custom component prop path)' do
      jsx = "      <TopBar brandLabel={StringManager.currentLanguage.chromeBrandName} />"
      result = generator.send(:generate_component_file, 'Chrome', jsx, minimal_json)
      expect(result).to include("import { useStringManager } from '@/generated/StringManager';")
      expect(result).to include('const $s = useStringManager();')
      expect(result).to include('{$s.chromeBrandName}')
      expect(result).not_to include('StringManager.currentLanguage.')
    end

    it 'still emits the import via the JSON walk when a standard Label text uses a snake_case key' do
      jsx = '' # jsx_content is empty here on purpose — we rely on uses_string_manager?(json)
      json_with_label = { 'type' => 'Label', 'text' => 'hero_eyebrow' }
      result = generator.send(:generate_component_file, 'Home', jsx, json_with_label)
      expect(result).to include("import { useStringManager } from '@/generated/StringManager';")
      expect(result).to include('const $s = useStringManager();')
    end

    it 'omits the import when neither the JSON tree nor the jsx_content references StringManager' do
      jsx = '      <div>static content</div>'
      result = generator.send(:generate_component_file, 'Static', jsx, minimal_json)
      expect(result).not_to include('StringManager')
      expect(result).not_to include('$s')
    end
  end

  describe '#generate_component_file ColorManager import emission' do
    # Read off the emitted JSX for the same reason the Configuration import
    # is: the emitter's own output cannot drift from itself, whereas a second
    # walk of the tree deciding "does this need resolving?" could
    # (rjui-dynamic-color-binding-emits-raw-token).
    let(:minimal_json) { { 'type' => 'View' } }

    it 'emits the ColorManager import when the JSX resolves a color at runtime' do
      jsx = '      <span style={{ color: ColorManager.resolveColor(data.badgeColor) }}>Hi</span>'
      result = generator.send(:generate_component_file, 'Badge', jsx, minimal_json)
      expect(result).to include("import { ColorManager } from '@/generated/ColorManager';")
    end

    it 'omits it when every color resolved to a class or a CSS literal' do
      jsx = '      <span className="text-warn">Hi</span>'
      result = generator.send(:generate_component_file, 'Plain', jsx, minimal_json)
      expect(result).not_to include("from '@/generated/ColorManager'")
    end
  end

  describe '#generate_component_file Configuration (FontSpec) import emission' do
    # The generator scans the already-converted JSX for the
    # Configuration.Font.resolve(...) emission BaseConverter produces when
    # `fontFamily` is set. If found, it imports `Configuration` from the
    # synced template path so the spread compiles and the host-supplied
    # fontProvider can intercept.
    let(:minimal_json) { { 'type' => 'View' } }

    it 'emits the Configuration import when jsx_content contains Configuration.Font.resolve(...)' do
      jsx = "      <span style={{ ...Configuration.Font.resolve({ family: 'Inter', italic: false }) }}>Hi</span>"
      result = generator.send(:generate_component_file, 'Hero', jsx, minimal_json)
      expect(result).to include("import { Configuration } from '@/lib/jsonui/Configuration';")
    end

    it 'omits the Configuration import when no FontSpec emission is present in the JSX stream' do
      jsx = '      <span>plain text</span>'
      result = generator.send(:generate_component_file, 'Plain', jsx, minimal_json)
      expect(result).not_to include("from '@/lib/jsonui/Configuration'")
      expect(result).not_to include('Configuration.Font')
    end
  end

  describe '#generate_component_file data prop call convention (regression: rjui-include-data-partial-call-convention-missing)' do
    # `data` is optional at every call site: bare includes render `<Name />`,
    # data-passing includes provide a Partial merged over createXxxData()
    # defaults, and pages/cells pass the full object.
    let(:minimal_json) { { 'type' => 'View' } }

    it 'makes data optional when the body never reads data' do
      jsx = '      <header>logo + service name</header>'
      result = generator.send(:generate_component_file, 'UserHeader', jsx, minimal_json)
      expect(result).to include('data?: UserHeaderData;')
      expect(result).not_to include('createUserHeaderData')
    end

    it 'takes an optional Partial and merges over factory defaults when the JSX reads data' do
      jsx = '      <span>{data.title}</span>'
      result = generator.send(:generate_component_file, 'Titled', jsx, minimal_json)
      expect(result).to include('data?: Partial<TitledData>;')
      expect(result).to include('({ data: dataProp, id }: TitledProps)')
      expect(result).to include('const data: TitledData = { ...createTitledData(), ...dataProp };')
      expect(result).to include("import { type TitledData, createTitledData } from '@/generated/data/TitledData';")
    end

    it 'applies the merge convention when focus bindings reference data' do
      json = { 'type' => 'View', 'child' => [
        { 'type' => 'TextField', 'id' => 'email_input' }
      ] }
      jsx = '      <input />'
      result = generator.send(:generate_component_file, 'Form', jsx, json)
      expect(result).to include('data?: Partial<FormData>;')
      expect(result).to include('const data: FormData = { ...createFormData(), ...dataProp };')
    end

    it 'does not mistake cellData references for data usage' do
      jsx = '      <Cell data={cellData} />'
      result = generator.send(:generate_component_file, 'ListHost', jsx, minimal_json)
      expect(result).to include('data?: ListHostData;')
      expect(result).not_to include('dataProp')
    end
  end

  describe '#generate_component_file root id passthrough (regression: rjui-collection-cells-missing-item-index-id)' do
    # Collections address cells as {collectionId}_item_{index} via an `id`
    # prop applied to the component's root element (kjui testTag parity).
    let(:minimal_json) { { 'type' => 'View' } }

    it 'injects id={id} into an element root and destructures id' do
      jsx = '      <div className="cell">{data.label}</div>'
      result = generator.send(:generate_component_file, 'RowCell', jsx, minimal_json)
      expect(result).to include('<div id={id} className="cell">')
      expect(result).to include('({ data: dataProp, id }: RowCellProps)')
      expect(result).to include('id?: string;')
    end

    it 'keeps a layout-declared root id as the fallback' do
      jsx = '      <div id="own_root" className="cell">{data.label}</div>'
      result = generator.send(:generate_component_file, 'OwnId', jsx, minimal_json)
      expect(result).to include('<div id={id ?? "own_root"} className="cell">')
    end

    it 'skips injection for an expression-container root but keeps id in the interface' do
      jsx = "    {data.visible !== \"gone\" && (\n    <div>x</div>\n    )}"
      result = generator.send(:generate_component_file, 'CondRoot', jsx, minimal_json)
      expect(result).to include('id?: string;')
      expect(result).not_to include('id={id}')
      expect(result).to include('({ data: dataProp }: CondRootProps)')
    end
  end

  describe '#generate_component_file root visibility wrapper (regression: rjui-root-visibility-binding-emits-bare-jsx-expression-container)' do
    # A root element with a visibility binding arrives as a bare JSX
    # expression container (`{cond && (...)}`), which is not legal directly
    # under `return (` — it must be wrapped in a fragment.
    let(:minimal_json) { { 'type' => 'View' } }

    it 'wraps a root-level expression container in a fragment' do
      jsx = "    {data.drawerVisibility !== \"gone\" && (\n    <div id=\"adminDrawerView\">x</div>\n    )}"
      result = generator.send(:generate_component_file, 'AdminDrawer', jsx, minimal_json)
      expect(result).to match(/return \(\s*\n\s*<>\s*\n\s*\{data\.drawerVisibility/)
      expect(result).to include('</>')
    end

    it 'leaves element-rooted JSX unwrapped' do
      jsx = '      <div>plain</div>'
      result = generator.send(:generate_component_file, 'Plain2', jsx, minimal_json)
      expect(result).not_to include('<>')
    end
  end
end
RSpec.describe RjuiTools::React::ReactGenerator, 'focus-state declarations' do
  let(:generator) do
    described_class.new({ 'use_tailwind' => true, 'typescript' => true,
                          'layouts_directory' => '/tmp/x', 'generated_directory' => '/tmp/x/out' })
  end

  it 'hoists a ref + effect per id-bearing editable field and imports the hooks' do
    json = { 'type' => 'View', 'child' => [
      { 'type' => 'TextField', 'id' => 'email_field' },
      { 'type' => 'TextView', 'id' => 'note_input' }
    ] }
    out = generator.generate('FocusScreen', json)
    expect(out).to include("import React, { useRef, useEffect } from 'react';")
    expect(out).to include('const emailFieldRef = useRef<HTMLInputElement | null>(null);')
    expect(out).to include('const noteInputRef = useRef<HTMLTextAreaElement | null>(null);')
    expect(out).to include('useEffect(() => { if (data.emailFieldIsFocused) { emailFieldRef.current?.focus(); } }, [data.emailFieldIsFocused]);')
    expect(out).to include('"use client"')
  end

  it 'emits nothing focus-related without editable ids' do
    json = { 'type' => 'View', 'child' => [{ 'type' => 'Text', 'text' => 'hi' }] }
    out = generator.generate('PlainScreen', json)
    expect(out).not_to include('useRef')
    expect(out).not_to include('IsFocused')
  end

  # A JS project emits .jsx, where `useRef<HTMLInputElement | null>(null)` is a
  # syntax error rather than a harmless annotation.
  it 'leaves the ref untyped in a JavaScript project' do
    js = described_class.new({ 'use_tailwind' => true, 'layouts_directory' => '/tmp/x',
                               'generated_directory' => '/tmp/x/out' })
    out = js.generate('FocusScreenJs', { 'type' => 'View', 'child' => [
      { 'type' => 'TextField', 'id' => 'email_field' }
    ] })
    expect(out).to include('const emailFieldRef = useRef(null);')
    expect(out).not_to include('useRef<')
  end
end

RSpec.describe RjuiTools::React::ReactGenerator, 'collection scroll declarations' do
  let(:generator) do
    described_class.new({ 'use_tailwind' => true, 'typescript' => true,
                          'layouts_directory' => '/tmp/x', 'generated_directory' => '/tmp/x/out' })
  end

  def screen(collection, name: 'ScrollScreen')
    generator.generate(name, { 'type' => 'View', 'child' => [collection] })
  end

  let(:base) do
    { 'type' => 'Collection', 'id' => 'item_list', 'items' => '@{listData}',
      'sections' => [{ 'cell' => 'ItemCell' }] }
  end

  it 'hoists a ref and imports only the helpers it uses' do
    out = screen(base.merge('scrollTo' => '@{scrollIndex}'))
    expect(out).to include("import { scrollCollectionToItem } from '@/generated/collectionScroll';")
    expect(out).to include('const itemListRef = useRef<HTMLDivElement | null>(null);')
    expect(out).to include("import React, { useRef, useEffect } from 'react';")
    expect(out).to include('"use client"')
  end

  it 'passes the anchor and animation through to the scroll helper' do
    out = screen(base.merge('scrollTo' => '@{scrollIndex}', 'scrollAnchor' => 'top',
                            'scrollAnimated' => false))
    expect(out).to include(
      'useEffect(() => { scrollCollectionToItem(itemListRef.current, data.scrollIndex, ' \
      "'top', false, false); }, [data.scrollIndex]);"
    )
  end

  # The SSoT states bottom as the default anchor, and animation defaults on.
  it 'defaults to a bottom anchor with animation' do
    out = screen(base.merge('scrollTo' => '@{scrollIndex}'))
    expect(out).to include("data.scrollIndex, 'bottom', true, false)")
  end

  it 'measures the horizontal axis for a horizontal collection' do
    out = screen(base.merge('scrollTo' => '@{scrollIndex}', 'orientation' => 'horizontal'))
    expect(out).to include("data.scrollIndex, 'bottom', true, true)")
  end

  # Mount-only: a later re-run would yank the user back to the anchor.
  it 'applies the default anchor once, on mount' do
    out = screen(base.merge('defaultScrollAnchor' => 'bottom'))
    expect(out).to include(
      "useEffect(() => { applyCollectionDefaultAnchor(itemListRef.current, 'bottom', false); }, []);"
    )
  end

  it 'falls back to a bottom anchor for an unrecognised value' do
    out = screen(base.merge('defaultScrollAnchor' => 'sideways'))
    expect(out).to include("applyCollectionDefaultAnchor(itemListRef.current, 'bottom', false)")
  end

  # The observer can only watch the cells that existed when it was created, so
  # it is rebuilt when the item list changes.
  it 're-observes when the items change' do
    out = screen(base.merge('onItemAppear' => '@{onItemAppear}'))
    expect(out).to include(
      'useEffect(() => observeCollectionItems(itemListRef.current, ' \
      '(index) => data.onItemAppear?.(index)), [data.listData]);'
    )
    expect(out).to include("import { observeCollectionItems } from '@/generated/collectionScroll';")
  end

  it 'drives the scroll position from currentPage' do
    out = screen(base.merge('currentPage' => '@{page}'))
    expect(out).to include("scrollCollectionToItem(itemListRef.current, data.page, 'top', true, false); }, [data.page]);")
    expect(out).to include('currentCollectionPage')
  end

  it 'emits nothing for a collection without scroll control' do
    out = screen(base)
    expect(out).not_to include('collectionScroll')
    expect(out).not_to include('itemListRef')
  end

  # A literal id is what ties the element to the hoisted ref.
  it 'skips a collection whose id is a binding' do
    out = screen(base.merge('id' => '@{listId}', 'scrollTo' => '@{scrollIndex}'))
    expect(out).not_to include('collectionScroll')
  end

  it 'leaves the ref untyped in a JavaScript project' do
    js = described_class.new({ 'use_tailwind' => true, 'layouts_directory' => '/tmp/x',
                               'generated_directory' => '/tmp/x/out' })
    out = js.generate('ScrollScreenJs', { 'type' => 'View', 'child' => [
      base.merge('scrollTo' => '@{scrollIndex}')
    ] })
    expect(out).to include('const itemListRef = useRef(null);')
    expect(out).not_to include('useRef<')
  end
end

RSpec.describe RjuiTools::React::ReactGenerator, 'relative positioning' do
  let(:generator) do
    described_class.new({ 'use_tailwind' => true, 'typescript' => true,
                          'layouts_directory' => '/tmp/x', 'generated_directory' => '/tmp/x/out' })
  end

  let(:header) { { 'type' => 'Label', 'id' => 'header', 'text' => 'Header', 'height' => 40 } }

  def screen(children, name: 'RelScreen')
    generator.generate(name, { 'type' => 'View', 'child' => children })
  end

  it 'hoists one ref and one effect per container' do
    out = screen([header, { 'type' => 'Label', 'id' => 'body', 'text' => 'Body',
                            'alignBottomOfView' => 'header' }])
    expect(out).to include("import { applyRelativePositions } from '@/generated/relativePosition';")
    expect(out).to include('const bodyRelRef = useRef<HTMLDivElement | null>(null);')
    expect(out).to include(
      "useEffect(() => applyRelativePositions(bodyRelRef.current, [{ id: 'body', below: 'header' }]), []);"
    )
    expect(out).to include('ref={bodyRelRef}')
    expect(out).to include('"use client"')
  end

  # The OfView family positions the element BESIDE the anchor — UIKit
  # constrains alignTopOfView's subject bottom to the anchor's top, i.e. the
  # subject goes above it.
  it 'maps every constraint to its helper field' do
    out = screen([header, {
      'type' => 'Label', 'id' => 'body', 'text' => 'Body',
      'alignTopOfView' => 'a', 'alignBottomOfView' => 'b',
      'alignLeftOfView' => 'c', 'alignRightOfView' => 'd',
      'alignTopView' => 'e', 'alignBottomView' => 'f',
      'alignLeftView' => 'g', 'alignRightView' => 'h',
      'alignCenterVerticalView' => 'i', 'alignCenterHorizontalView' => 'j'
    }])
    expect(out).to include(
      "{ id: 'body', above: 'a', below: 'b', leftOf: 'c', rightOf: 'd', " \
      "alignTop: 'e', alignBottom: 'f', alignLeft: 'g', alignRight: 'h', " \
      "centerVertical: 'i', centerHorizontal: 'j' }"
    )
  end

  it 'collects every constrained child of the same container into one spec' do
    out = screen([header,
                  { 'type' => 'Label', 'id' => 'body', 'text' => 'B', 'alignBottomOfView' => 'header' },
                  { 'type' => 'Label', 'id' => 'footer', 'text' => 'F', 'alignBottomOfView' => 'body' }])
    expect(out).to include("[{ id: 'body', below: 'header' }, { id: 'footer', below: 'body' }]")
    expect(out.scan('applyRelativePositions').length).to eq(2) # import + one call
  end

  # The helper finds anchors and subjects by DOM id, so a binding-form id has
  # nothing to look up.
  it 'skips a child whose id is a binding' do
    out = screen([header, { 'type' => 'Label', 'id' => '@{rowId}', 'text' => 'B',
                            'alignBottomOfView' => 'header' }])
    expect(out).not_to include('relativePosition')
  end

  it 'skips a constraint whose target is a binding' do
    out = screen([header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B',
                            'alignBottomOfView' => '@{anchorId}' }])
    expect(out).not_to include('relativePosition')
  end

  it 'emits nothing without sibling constraints' do
    out = screen([header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B' }])
    expect(out).not_to include('relativePosition')
    expect(out).not_to include('RelRef')
  end

  it 'leaves the ref untyped in a JavaScript project' do
    js = described_class.new({ 'use_tailwind' => true, 'layouts_directory' => '/tmp/x',
                               'generated_directory' => '/tmp/x/out' })
    out = js.generate('RelScreenJs', { 'type' => 'View', 'child' => [
      header, { 'type' => 'Label', 'id' => 'body', 'text' => 'B', 'alignBottomOfView' => 'header' }
    ] })
    expect(out).to include('const bodyRelRef = useRef(null);')
    expect(out).not_to include('useRef<')
  end
end

# autoShrink / minimumScaleFactor. CSS can size text against the viewport but
# never against the element's own box, so the fit is measured at runtime: the
# converter attaches a ref and the generator hoists the effect that fits it.
RSpec.describe RjuiTools::React::ReactGenerator, 'autoShrink' do
  let(:generator) do
    described_class.new({ 'use_tailwind' => true, 'typescript' => true,
                          'layouts_directory' => '/tmp/x', 'generated_directory' => '/tmp/x/out' })
  end

  def screen(child, name: 'ShrinkScreen')
    generator.generate(name, { 'type' => 'View', 'child' => [child] })
  end

  it 'hoists a ref and a fit effect per shrinking label' do
    out = screen({ 'type' => 'Label', 'id' => 'title', 'text' => 'Long text',
                   'autoShrink' => true, 'fontSize' => 16, 'minimumScaleFactor' => 0.25 })
    expect(out).to include("import { applyAutoShrink } from '@/generated/autoShrink';")
    expect(out).to include('const titleShrinkRef = useRef<HTMLElement | null>(null);')
    expect(out).to include(
      'useEffect(() => applyAutoShrink(titleShrinkRef.current, ' \
      '{ fontSize: 16, minimumScaleFactor: 0.25 }), []);'
    )
    expect(out).to include('ref={titleShrinkRef}')
  end

  # A bound size or factor is the effect's dependency, so the text re-fits when
  # the data moves. The old viewport clamp could not express this at all: it
  # multiplied the two in Ruby and raised on a bound value.
  it 'makes a bound factor a dependency' do
    out = screen({ 'type' => 'Label', 'id' => 'title', 'text' => 'Long text',
                   'autoShrink' => true, 'fontSize' => 16,
                   'minimumScaleFactor' => '@{minScale}' })
    expect(out).to include(
      'useEffect(() => applyAutoShrink(titleShrinkRef.current, ' \
      '{ fontSize: 16, minimumScaleFactor: data.minScale }), [data.minScale]);'
    )
  end

  # `autoShrink: "@{flag}"` cannot be resolved at build time; the ref is
  # attached and the helper decides at runtime whether anything overflows.
  it 'hoists for a bound autoShrink flag' do
    out = screen({ 'type' => 'Label', 'id' => 'title', 'text' => 'Long text',
                   'autoShrink' => '@{shrink}' })
    expect(out).to include('const titleShrinkRef = useRef<HTMLElement | null>(null);')
  end

  it 'hoists nothing for a label that does not declare it' do
    out = screen({ 'type' => 'Label', 'id' => 'title', 'text' => 'Long text' })
    expect(out).not_to include('applyAutoShrink')
    expect(out).not_to include('ShrinkRef')
  end

  # A JS project emits .jsx, where the type parameter is a syntax error.
  it 'omits the type parameter for a JavaScript project' do
    js = described_class.new({ 'use_tailwind' => true, 'layouts_directory' => '/tmp/x',
                               'generated_directory' => '/tmp/x/out' })
    out = js.generate('ShrinkScreenJs', { 'type' => 'View', 'child' => [
      { 'type' => 'Label', 'id' => 'title', 'text' => 'Long text', 'autoShrink' => true }
    ] })
    expect(out).to include('const titleShrinkRef = useRef(null);')
    expect(out).not_to include('useRef<')
  end
end
