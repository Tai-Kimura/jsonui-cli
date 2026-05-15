# frozen_string_literal: true

require 'swiftui/views/responsive_helper'
require 'swiftui/views/view_converter'
require 'swiftui/converter_factory'
require 'swiftui/view_registry'

RSpec.describe SjuiTools::SwiftUI::Views::ResponsiveHelper do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '.size_class_condition' do
    it 'returns correct condition for regular' do
      result = described_class.size_class_condition('regular')
      expect(result).to eq('horizontalSizeClass == .regular')
    end

    it 'returns correct condition for compact' do
      result = described_class.size_class_condition('compact')
      expect(result).to eq('horizontalSizeClass == .compact')
    end

    it 'returns correct condition for landscape' do
      result = described_class.size_class_condition('landscape')
      expect(result).to eq('verticalSizeClass == .compact')
    end

    it 'returns correct condition for regular-landscape' do
      result = described_class.size_class_condition('regular-landscape')
      expect(result).to eq('horizontalSizeClass == .regular && verticalSizeClass == .compact')
    end

    it 'returns correct condition for compact-landscape' do
      result = described_class.size_class_condition('compact-landscape')
      expect(result).to eq('horizontalSizeClass == .compact && verticalSizeClass == .compact')
    end

    it 'falls back medium to compact' do
      result = described_class.size_class_condition('medium')
      expect(result).to eq('horizontalSizeClass == .compact')
    end

    it 'returns correct condition for medium-landscape' do
      result = described_class.size_class_condition('medium-landscape')
      expect(result).to eq('horizontalSizeClass == .compact && verticalSizeClass == .compact')
    end
  end

  describe '.has_responsive_descendant?' do
    it 'returns false for non-responsive component' do
      component = { 'type' => 'View', 'orientation' => 'vertical' }
      expect(described_class.has_responsive_descendant?(component)).to be false
    end

    it 'returns true for component with responsive block' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'responsive' => { 'regular' => { 'orientation' => 'horizontal' } }
      }
      expect(described_class.has_responsive_descendant?(component)).to be true
    end

    it 'returns true if a child has responsive block' do
      component = {
        'type' => 'View',
        'orientation' => 'vertical',
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' },
          {
            'type' => 'View',
            'orientation' => 'horizontal',
            'responsive' => { 'regular' => { 'spacing' => 24 } },
            'child' => [{ 'type' => 'Label', 'text' => 'World' }]
          }
        ]
      }
      expect(described_class.has_responsive_descendant?(component)).to be true
    end

    it 'returns false for nil input' do
      expect(described_class.has_responsive_descendant?(nil)).to be false
    end

    it 'returns false for non-hash input' do
      expect(described_class.has_responsive_descendant?('string')).to be false
    end
  end

  describe '.environment_declarations' do
    it 'returns two @Environment declarations' do
      decls = described_class.environment_declarations
      expect(decls.length).to eq(2)
      expect(decls[0]).to include('@Environment')
      expect(decls[0]).to include('horizontalSizeClass')
      expect(decls[1]).to include('@Environment')
      expect(decls[1]).to include('verticalSizeClass')
    end
  end

  describe '.generate_container_function' do
    let(:component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 8,
        'responsive' => {
          'regular' => { 'orientation' => 'horizontal', 'spacing' => 24 },
          'landscape' => { 'spacing' => 16 },
          'regular-landscape' => { 'orientation' => 'horizontal', 'spacing' => 32 }
        },
        'child' => [
          { 'type' => 'Label', 'text' => 'Hello' }
        ]
      }
    end

    let(:converter) do
      SjuiTools::SwiftUI::Views::ViewConverter.new(component, 0)
    end

    it 'generates a generic wrapper function' do
      code = described_class.generate_container_function('responsive0', component, converter)
      expect(code).to include('private func responsive0<Content: View>')
      expect(code).to include('@ViewBuilder content: () -> Content')
    end

    it 'generates if/else branches in priority order' do
      code = described_class.generate_container_function('responsive0', component, converter)
      # regular-landscape should come first (highest priority compound)
      expect(code).to include('horizontalSizeClass == .regular && verticalSizeClass == .compact')
      # Then landscape
      expect(code).to include('verticalSizeClass == .compact')
      # Then regular
      expect(code).to include('horizontalSizeClass == .regular')
      # Then default (else)
      expect(code).to include('} else {')
    end

    it 'generates HStack for horizontal orientation' do
      code = described_class.generate_container_function('responsive0', component, converter)
      expect(code).to include('HStack(')
    end

    it 'generates VStack for vertical/default orientation' do
      code = described_class.generate_container_function('responsive0', component, converter)
      expect(code).to include('VStack(')
    end

    it 'includes content() call in each branch' do
      code = described_class.generate_container_function('responsive0', component, converter)
      expect(code.scan('content()').length).to be >= 2
    end

    it 'uses correct spacing values per branch' do
      code = described_class.generate_container_function('responsive0', component, converter)
      expect(code).to include('spacing: 32')  # regular-landscape
      expect(code).to include('spacing: 24')  # regular
      expect(code).to include('spacing: 16')  # landscape
      expect(code).to include('spacing: 8')   # default
    end
  end

  describe '.generate_leaf_function' do
    let(:component) do
      {
        'type' => 'Label',
        'text' => 'Hello',
        'fontSize' => 14,
        'responsive' => {
          'regular' => { 'fontSize' => 20 }
        }
      }
    end

    let(:binding_registry) { SjuiTools::SwiftUI::Binding::BindingHandlerRegistry.new }
    let(:converter_factory) { SjuiTools::SwiftUI::ConverterFactory.new(binding_registry) }
    let(:view_registry) { SjuiTools::SwiftUI::ViewRegistry.new }

    it 'generates a leaf function with branches' do
      code = described_class.generate_leaf_function(
        'responsive0', component, converter_factory, 0, nil, view_registry, binding_registry
      )
      expect(code).to include('private func responsive0()')
      expect(code).to include('-> some View')
      expect(code).to include('horizontalSizeClass == .regular')
    end
  end

  describe '.resolve_vstack_alignment' do
    it 'returns .leading by default' do
      expect(described_class.resolve_vstack_alignment(nil)).to eq('.leading')
    end

    it 'returns .center for center gravity' do
      expect(described_class.resolve_vstack_alignment('center')).to eq('.center')
    end

    it 'returns .trailing for right gravity' do
      expect(described_class.resolve_vstack_alignment('right')).to eq('.trailing')
    end

    it 'handles pipe-separated gravity' do
      expect(described_class.resolve_vstack_alignment('center|top')).to eq('.center')
    end
  end

  describe '.resolve_hstack_alignment' do
    it 'returns .center by default' do
      expect(described_class.resolve_hstack_alignment(nil)).to eq('.center')
    end

    it 'returns .top for top gravity' do
      expect(described_class.resolve_hstack_alignment('top')).to eq('.top')
    end

    it 'returns .bottom for bottom gravity' do
      expect(described_class.resolve_hstack_alignment('bottom')).to eq('.bottom')
    end
  end

  describe '.build_responsive_modifiers (regression: sjui-responsive-maxwidth-centerhorizontal-not-applied)' do
    it 'emits .frame(maxWidth:) when attrs has maxWidth' do
      modifiers = described_class.build_responsive_modifiers({ 'maxWidth' => 480 }, nil)
      expect(modifiers).to eq(['.frame(maxWidth: 480)'])
    end

    it 'emits .frame(maxWidth: .infinity, alignment: .center) for centerHorizontal alone' do
      modifiers = described_class.build_responsive_modifiers({ 'centerHorizontal' => true }, nil)
      expect(modifiers).to eq(['.frame(maxWidth: .infinity, alignment: .center)'])
    end

    it 'composes maxWidth and centerHorizontal into a single .frame' do
      modifiers = described_class.build_responsive_modifiers(
        { 'maxWidth' => 480, 'centerHorizontal' => true }, nil
      )
      expect(modifiers).to eq(['.frame(maxWidth: 480, alignment: .center)'])
    end

    it 'emits maxHeight and minWidth/minHeight when present' do
      modifiers = described_class.build_responsive_modifiers(
        { 'minWidth' => 100, 'maxWidth' => 400, 'minHeight' => 50, 'maxHeight' => 200 }, nil
      )
      expect(modifiers).to eq(
        ['.frame(minWidth: 100, maxWidth: 400, minHeight: 50, maxHeight: 200)']
      )
    end

    it 'expands centerInParent into both axes' do
      modifiers = described_class.build_responsive_modifiers({ 'centerInParent' => true }, nil)
      expect(modifiers).to eq(
        ['.frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .center)']
      )
    end

    it 'returns an empty array when no recognized keys are present' do
      modifiers = described_class.build_responsive_modifiers(
        { 'orientation' => 'horizontal', 'spacing' => 24 }, nil
      )
      expect(modifiers).to eq([])
    end

    # Regression: sjui-kjui-responsive-align-cascades-to-inner-ignoring-
    # gravity. The inner frame's `alignment:` MUST be `gravity`-driven,
    # NOT responsive `align*` flag-driven. The responsive flags get their
    # effect from the outer wrap (`.frame(.infinity, alignment: ...)`).
    it 'emits alignment: .center for alignLeft + numeric maxWidth (no gravity)' do
      # Without `gravity`, alignLeft falls back to the default-center
      # inner alignment. alignLeft itself is honored by the outer wrap
      # (when matchParent + numeric maxWidth collide) — not here.
      modifiers = described_class.build_responsive_modifiers(
        { 'maxWidth' => 480, 'alignLeft' => true }, nil
      )
      expect(modifiers).to eq(['.frame(maxWidth: 480, alignment: .center)'])
    end

    it 'emits alignment: .center for alignRight + numeric maxWidth (no gravity)' do
      modifiers = described_class.build_responsive_modifiers(
        { 'maxWidth' => 480, 'alignRight' => true }, nil
      )
      expect(modifiers).to eq(['.frame(maxWidth: 480, alignment: .center)'])
    end

    it 'does not auto-fall back to .infinity for alignLeft alone (only center* does)' do
      # alignLeft without explicit max means "outer anchor only". Without
      # matchParent there is no outer wrap, so the responsive flag is
      # effectively a no-op in this configuration. build_responsive_modifiers
      # should NOT manufacture a `.frame(maxWidth: .infinity, ...)` for it.
      modifiers = described_class.build_responsive_modifiers({ 'alignLeft' => true }, nil)
      expect(modifiers).to eq([])
    end

    it 'gravity drives the inner frame alignment' do
      # gravity: "center" → `.center` (matches the chat-button repro).
      modifiers = described_class.build_responsive_modifiers(
        { 'maxWidth' => 320, 'alignLeft' => true, 'gravity' => 'center' }, nil
      )
      expect(modifiers).to eq(['.frame(maxWidth: 320, alignment: .center)'])
    end

    it 'gravity: "left" emits .leading inner alignment' do
      modifiers = described_class.build_responsive_modifiers(
        { 'maxWidth' => 320, 'centerHorizontal' => true, 'gravity' => 'left' }, nil
      )
      expect(modifiers).to eq(['.frame(maxWidth: 320, alignment: .leading)'])
    end

    it 'gravity: "bottom|right" emits .bottomTrailing inner alignment' do
      modifiers = described_class.build_responsive_modifiers(
        { 'maxWidth' => 320, 'maxHeight' => 200, 'alignLeft' => true, 'gravity' => 'bottom|right' },
        nil
      )
      expect(modifiers).to eq(
        ['.frame(maxWidth: 320, maxHeight: 200, alignment: .bottomTrailing)']
      )
    end
  end

  # `frame_alignment_for` is the OUTER-wrap resolver (responsive
  # `align*` / `center*` flags). It is not used by the inner frame;
  # see `inner_frame_alignment` below for that.
  describe '.frame_alignment_for' do
    it 'returns nil when no flag is set' do
      expect(described_class.frame_alignment_for({})).to be_nil
    end

    it 'returns .leading for alignLeft alone' do
      expect(described_class.frame_alignment_for({ 'alignLeft' => true })).to eq('.leading')
    end

    it 'returns .trailing for alignRight alone' do
      expect(described_class.frame_alignment_for({ 'alignRight' => true })).to eq('.trailing')
    end

    it 'returns .top for alignTop alone' do
      expect(described_class.frame_alignment_for({ 'alignTop' => true })).to eq('.top')
    end

    it 'returns .bottom for alignBottom alone' do
      expect(described_class.frame_alignment_for({ 'alignBottom' => true })).to eq('.bottom')
    end

    it 'returns .topLeading for alignTop + alignLeft' do
      expect(described_class.frame_alignment_for({ 'alignTop' => true, 'alignLeft' => true }))
        .to eq('.topLeading')
    end

    it 'returns .bottomTrailing for alignBottom + alignRight' do
      expect(described_class.frame_alignment_for({ 'alignBottom' => true, 'alignRight' => true }))
        .to eq('.bottomTrailing')
    end

    it 'collapses alignLeft + alignRight to .center horizontally' do
      expect(described_class.frame_alignment_for({ 'alignLeft' => true, 'alignRight' => true }))
        .to eq('.center')
    end

    it 'returns .center for centerInParent (back-compat)' do
      expect(described_class.frame_alignment_for({ 'centerInParent' => true })).to eq('.center')
    end
  end

  # Regression: sjui-kjui-responsive-align-cascades-to-inner-ignoring-
  # gravity. inner_frame_alignment is `gravity`-driven and falls back to
  # `.center` when no gravity is set but a responsive flag is present.
  describe '.inner_frame_alignment' do
    it 'returns nil when neither gravity nor a responsive flag is set' do
      expect(described_class.inner_frame_alignment({})).to be_nil
      expect(described_class.inner_frame_alignment({ 'maxWidth' => 480 })).to be_nil
    end

    it 'returns .center when a responsive flag is set but no gravity' do
      expect(described_class.inner_frame_alignment({ 'alignLeft' => true })).to eq('.center')
      expect(described_class.inner_frame_alignment({ 'centerHorizontal' => true })).to eq('.center')
      expect(described_class.inner_frame_alignment({ 'alignBottom' => true })).to eq('.center')
    end

    it 'returns gravity-derived alignment when gravity is set' do
      expect(described_class.inner_frame_alignment({ 'gravity' => 'center' })).to eq('.center')
      expect(described_class.inner_frame_alignment({ 'gravity' => 'left' })).to eq('.leading')
      expect(described_class.inner_frame_alignment({ 'gravity' => 'right' })).to eq('.trailing')
      expect(described_class.inner_frame_alignment({ 'gravity' => 'top' })).to eq('.top')
      expect(described_class.inner_frame_alignment({ 'gravity' => 'bottom' })).to eq('.bottom')
    end

    it 'parses pipe-separated compound gravity' do
      expect(described_class.inner_frame_alignment({ 'gravity' => 'bottom|right' }))
        .to eq('.bottomTrailing')
      expect(described_class.inner_frame_alignment({ 'gravity' => 'top|left' }))
        .to eq('.topLeading')
    end

    it 'gravity overrides responsive flag (chat button repro)' do
      # `responsive.regular.alignLeft: true` + base `gravity: "center"` →
      # inner alignment is `.center` from gravity, not `.leading` from
      # the responsive flag. The outer wrap resolves to `.leading`.
      result = described_class.inner_frame_alignment(
        'alignLeft' => true, 'gravity' => 'center'
      )
      expect(result).to eq('.center')
    end
  end

  describe '.generate_container_function (regression: maxWidth/centerHorizontal in responsive override)' do
    let(:component_with_size_override) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 0,
        'responsive' => {
          'regular' => { 'maxWidth' => 480, 'centerHorizontal' => true }
        }
      }
    end

    let(:converter_for_override) do
      SjuiTools::SwiftUI::Views::ViewConverter.new(component_with_size_override, 0)
    end

    it 'emits .frame(maxWidth: 480, alignment: .center) in the regular branch' do
      code = described_class.generate_container_function(
        'responsive0', component_with_size_override, converter_for_override
      )
      expect(code).to include('.frame(maxWidth: 480, alignment: .center)')
    end

    it 'does not emit the frame modifier in the default branch (no override)' do
      code = described_class.generate_container_function(
        'responsive0', component_with_size_override, converter_for_override
      )
      # The default branch's VStack does not have an override of maxWidth/centerHorizontal,
      # so build_responsive_modifiers returns [] for it. There should be exactly one .frame line.
      expect(code.scan('.frame(maxWidth:').length).to eq(1)
    end
  end

  # Regression: sjui-view-responsive-maxwidth-border-overflow
  # `width: matchParent` + responsive `maxWidth + centerHorizontal` used to
  # land the `.frame(maxWidth: .infinity)` from apply_frame_size BETWEEN the
  # inner maxWidth frame and the decorations (background/cornerRadius/
  # overlay), so the border ended up painted full-width. Fix: strip width
  # from the collect_modifiers_for input when the center flag overrides it,
  # and emit a single outer `.frame(.infinity, .center)` after decorations.
  describe '.generate_container_function (regression: maxWidth + matchParent border overflow)' do
    let(:bordered_button_component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 0,
        'width' => 'matchParent',
        'height' => 44,
        'background' => '#FFFFFF',
        'borderWidth' => 1,
        'borderColor' => '#CCCCCC',
        'cornerRadius' => 10,
        'responsive' => {
          'regular' => { 'maxWidth' => 320, 'centerHorizontal' => true }
        },
        'child' => [{ 'type' => 'Label', 'text' => 'Hi' }]
      }
    end

    let(:converter_for_bordered) do
      SjuiTools::SwiftUI::Views::ViewConverter.new(bordered_button_component, 0)
    end

    it 'emits exactly one inner .frame(maxWidth: 320, alignment: .center)' do
      code = described_class.generate_container_function(
        'responsive0', bordered_button_component, converter_for_bordered
      )
      expect(code.scan('.frame(maxWidth: 320, alignment: .center)').length).to eq(1)
    end

    it 'emits the outer .frame(maxWidth: .infinity, alignment: .center) AFTER decorations' do
      code = described_class.generate_container_function(
        'responsive0', bordered_button_component, converter_for_bordered
      )
      # Decorations are present in the regular branch.
      bg_idx = code.index('.background(')
      corner_idx = code.index('.cornerRadius(')
      overlay_idx = code.index('.overlay(')
      outer_frame_idx = code.index('.frame(maxWidth: .infinity, alignment: .center)')
      expect([bg_idx, corner_idx, overlay_idx, outer_frame_idx]).to all(be_truthy)
      # Decoration emit positions must precede the outer .infinity frame in the regular branch.
      regular_section = code[/horizontalSizeClass == \.regular.*?(?=\} else \{|\}\s*\}\s*\z)/m] || code
      bg_in_regular = regular_section.index('.background(')
      outer_in_regular = regular_section.index('.frame(maxWidth: .infinity, alignment: .center)')
      expect(bg_in_regular).not_to be_nil
      expect(outer_in_regular).not_to be_nil
      expect(bg_in_regular).to be < outer_in_regular
    end

    it 'does not emit a stray .frame(maxWidth: .infinity) from matchParent inside the regular branch' do
      code = described_class.generate_container_function(
        'responsive0', bordered_button_component, converter_for_bordered
      )
      # Only one .frame(maxWidth: .infinity, ...) — the outer wrap. The
      # apply_frame_size emit for `width: matchParent` is suppressed here.
      regular_section = code[/horizontalSizeClass == \.regular.*?(?=\} else \{)/m]
      expect(regular_section).not_to be_nil
      expect(regular_section.scan(/\.frame\(maxWidth: \.infinity/).length).to eq(1)
    end
  end

  # Regression: sjui-kjui-responsive-align-cascades-to-inner-ignoring-
  # gravity. alignLeft is OUTER-only — the inner frame's alignment comes
  # from `gravity` (or `.center` default). chat-button repro:
  # `gravity: "center"` + `responsive.regular.alignLeft: true` + maxWidth
  # + matchParent → inner `.center`, outer `.leading`.
  describe '.generate_container_function (regression: alignLeft outer-only, gravity drives inner)' do
    let(:chat_button_component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 0,
        'width' => 'matchParent',
        'height' => 44,
        'gravity' => 'center',
        'background' => '#FFFFFF',
        'borderWidth' => 1,
        'borderColor' => '#CCCCCC',
        'cornerRadius' => 10,
        'responsive' => {
          'regular' => { 'maxWidth' => 320, 'alignLeft' => true }
        },
        'child' => [{ 'type' => 'Label', 'text' => 'Hi' }]
      }
    end

    let(:converter_for_chat_button) do
      SjuiTools::SwiftUI::Views::ViewConverter.new(chat_button_component, 0)
    end

    it 'emits inner .frame(maxWidth: 320, alignment: .center) from gravity (not alignLeft)' do
      code = described_class.generate_container_function(
        'responsive0', chat_button_component, converter_for_chat_button
      )
      expect(code).to include('.frame(maxWidth: 320, alignment: .center)')
      expect(code).not_to include('.frame(maxWidth: 320, alignment: .leading)')
    end

    it 'emits outer .frame(maxWidth: .infinity, alignment: .leading) after decorations' do
      code = described_class.generate_container_function(
        'responsive0', chat_button_component, converter_for_chat_button
      )
      expect(code).to include('.frame(maxWidth: .infinity, alignment: .leading)')
      regular_section = code[/horizontalSizeClass == \.regular.*?(?=\} else \{)/m]
      expect(regular_section).not_to be_nil
      bg_idx = regular_section.index('.background(')
      outer_idx = regular_section.index('.frame(maxWidth: .infinity, alignment: .leading)')
      expect(bg_idx).not_to be_nil
      expect(outer_idx).not_to be_nil
      expect(bg_idx).to be < outer_idx
    end
  end

  # Regression: sjui-markdowntext-custom-converter-centerhorizontal-missing
  # Leaf-path extension converters (jui generate converter <Name>) reach
  # apply_modifiers directly. Without the alignment hook on a center flag,
  # `maxWidth: N` shrinks the view but leaves it leading-aligned in its frame.
  describe 'apply_frame_constraints alignment for centerHorizontal/Vertical (regression: markdowntext)' do
    it 'adds alignment: .center for non-Label types when centerHorizontal is true' do
      component = {
        'type' => 'MarkdownText',
        'centerHorizontal' => true,
        'maxWidth' => 480
      }
      converter = SjuiTools::SwiftUI::Views::BaseViewConverter.new(component)
      converter.send(:apply_modifiers)
      lines = converter.instance_variable_get(:@modifier_bag).to_lines
      expect(lines).to include('.frame(maxWidth: 480, alignment: .center)')
    end

    it 'adds alignment: .center for centerVertical' do
      component = {
        'type' => 'MarkdownText',
        'centerVertical' => true,
        'maxHeight' => 200
      }
      converter = SjuiTools::SwiftUI::Views::BaseViewConverter.new(component)
      converter.send(:apply_modifiers)
      lines = converter.instance_variable_get(:@modifier_bag).to_lines
      expect(lines).to include('.frame(maxHeight: 200, alignment: .center)')
    end

    it 'adds alignment: .center for centerInParent' do
      component = {
        'type' => 'MarkdownText',
        'centerInParent' => true,
        'maxWidth' => 320,
        'maxHeight' => 200
      }
      converter = SjuiTools::SwiftUI::Views::BaseViewConverter.new(component)
      converter.send(:apply_modifiers)
      lines = converter.instance_variable_get(:@modifier_bag).to_lines
      expect(lines).to include('.frame(maxWidth: 320, maxHeight: 200, alignment: .center)')
    end

    it 'leaves Label types using label_frame_alignment (textAlign-aware)' do
      component = {
        'type' => 'Label',
        'centerHorizontal' => true,
        'maxWidth' => 480,
        'textAlign' => 'center'
      }
      converter = SjuiTools::SwiftUI::Views::BaseViewConverter.new(component)
      converter.send(:apply_modifiers)
      lines = converter.instance_variable_get(:@modifier_bag).to_lines
      # Label uses label_frame_alignment which returns .center for textAlign:center
      expect(lines.any? { |l| l.start_with?('.frame(maxWidth: 480, alignment:') }).to be true
    end

    # Regression: sjui-kjui-responsive-align-cascades-to-inner-ignoring-
    # gravity. align* flags do NOT cascade to inner-frame alignment —
    # that's `gravity`-driven. Without gravity, inner falls back to
    # `.center` (matching the trio contract for centerHorizontal).
    it 'adds alignment: .center for non-Label types when alignLeft alone (no gravity)' do
      component = {
        'type' => 'MarkdownText',
        'alignLeft' => true,
        'maxWidth' => 480
      }
      converter = SjuiTools::SwiftUI::Views::BaseViewConverter.new(component)
      converter.send(:apply_modifiers)
      lines = converter.instance_variable_get(:@modifier_bag).to_lines
      expect(lines).to include('.frame(maxWidth: 480, alignment: .center)')
    end

    it 'adds alignment: .center for non-Label types when alignRight alone (no gravity)' do
      component = {
        'type' => 'MarkdownText',
        'alignRight' => true,
        'maxWidth' => 480
      }
      converter = SjuiTools::SwiftUI::Views::BaseViewConverter.new(component)
      converter.send(:apply_modifiers)
      lines = converter.instance_variable_get(:@modifier_bag).to_lines
      expect(lines).to include('.frame(maxWidth: 480, alignment: .center)')
    end

    it 'gravity drives inner alignment, NOT the responsive align* flag' do
      # alignLeft (responsive) + gravity:center (inner) → inner `.center`.
      component = {
        'type' => 'MarkdownText',
        'alignLeft' => true,
        'gravity' => 'center',
        'maxWidth' => 480
      }
      converter = SjuiTools::SwiftUI::Views::BaseViewConverter.new(component)
      converter.send(:apply_modifiers)
      lines = converter.instance_variable_get(:@modifier_bag).to_lines
      expect(lines).to include('.frame(maxWidth: 480, alignment: .center)')
    end

    it 'gravity: "left" emits .leading even when centerHorizontal is set' do
      component = {
        'type' => 'MarkdownText',
        'centerHorizontal' => true,
        'gravity' => 'left',
        'maxWidth' => 480
      }
      converter = SjuiTools::SwiftUI::Views::BaseViewConverter.new(component)
      converter.send(:apply_modifiers)
      lines = converter.instance_variable_get(:@modifier_bag).to_lines
      expect(lines).to include('.frame(maxWidth: 480, alignment: .leading)')
    end
  end

  # Regression lock-in: sjui-kjui-responsive-honor-weight-and-width.
  # `width: matchParent` / `height: matchParent` (and numeric values) in a
  # responsive branch DO reach apply_frame_size via collect_modifiers_for,
  # because the branch attrs are passed in directly and `width`/`height`
  # are NOT in FRAME_CENTER_KEYS (the explicit exclude list). The bug
  # filer assumed these were scope-outside; they aren't on iOS as long as
  # the consumer uses `width: matchParent` (= `.frame(maxWidth: .infinity)`)
  # rather than `weight`. Equal split across an HStack works because
  # multiple `.frame(maxWidth: .infinity)` siblings distribute evenly.
  #
  # Out of scope (deferred): `weight: N` in responsive branches —
  # WeightedHStack/WeightedVStack uses a tuple children API and can't be
  # rendered via the generate_container_function content() ViewBuilder
  # pattern without a substantial refactor. Documented as v3.
  describe '.generate_container_function (regression: width/height responsive override reaches the branch)' do
    let(:width_override_component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 0,
        'responsive' => {
          'regular' => { 'width' => 'matchParent' }
        },
        'child' => [{ 'type' => 'Label', 'text' => 'Hi' }]
      }
    end

    let(:converter_for_width_override) do
      SjuiTools::SwiftUI::Views::ViewConverter.new(width_override_component, 0)
    end

    it 'emits .frame(maxWidth: .infinity) in the regular branch when width: matchParent is set there' do
      code = described_class.generate_container_function(
        'responsive0', width_override_component, converter_for_width_override
      )
      # Branch-merged width: matchParent → size_to_swiftui → .infinity →
      # apply_frame_size emits .frame(maxWidth: .infinity).
      regular_section = code[/horizontalSizeClass == \.regular.*?(?=\} else \{)/m]
      expect(regular_section).not_to be_nil
      expect(regular_section).to include('.frame(maxWidth: .infinity')
    end

    it 'does not emit .frame(maxWidth: .infinity) in the default branch (no override)' do
      code = described_class.generate_container_function(
        'responsive0', width_override_component, converter_for_width_override
      )
      default_section = code[/\} else \{.*?(?=\s*\}\s*\}\s*\z)/m]
      expect(default_section).not_to be_nil
      expect(default_section).not_to include('.frame(maxWidth: .infinity')
    end

    let(:height_override_component) do
      {
        'type' => 'View',
        'orientation' => 'horizontal',
        'spacing' => 0,
        'responsive' => {
          'regular' => { 'height' => 'matchParent' }
        },
        'child' => [{ 'type' => 'Label', 'text' => 'Hi' }]
      }
    end

    let(:converter_for_height_override) do
      SjuiTools::SwiftUI::Views::ViewConverter.new(height_override_component, 0)
    end

    it 'emits .frame(maxHeight: .infinity) in the regular branch when height: matchParent is set there' do
      code = described_class.generate_container_function(
        'responsive0', height_override_component, converter_for_height_override
      )
      regular_section = code[/horizontalSizeClass == \.regular.*?(?=\} else \{)/m]
      expect(regular_section).not_to be_nil
      expect(regular_section).to include('maxHeight: .infinity')
    end

    let(:numeric_width_component) do
      {
        'type' => 'View',
        'orientation' => 'vertical',
        'spacing' => 0,
        'width' => 'matchParent',
        'responsive' => {
          'regular' => { 'width' => 240 }
        },
        'child' => [{ 'type' => 'Label', 'text' => 'Hi' }]
      }
    end

    let(:converter_for_numeric_width) do
      SjuiTools::SwiftUI::Views::ViewConverter.new(numeric_width_component, 0)
    end

    it 'emits .frame(width: 240) in the regular branch and .frame(maxWidth: .infinity) in the default branch' do
      code = described_class.generate_container_function(
        'responsive0', numeric_width_component, converter_for_numeric_width
      )
      regular_section = code[/horizontalSizeClass == \.regular.*?(?=\} else \{)/m]
      default_section = code[/\} else \{.*?(?=\s*\}\s*\}\s*\z)/m]
      expect(regular_section).to include('.frame(width: 240)')
      expect(default_section).to include('maxWidth: .infinity')
    end
  end

  describe '.numeric_dimension?' do
    it 'accepts Integer / Float' do
      expect(described_class.numeric_dimension?(480)).to be true
      expect(described_class.numeric_dimension?(320.5)).to be true
    end

    it 'accepts all-digit Strings' do
      expect(described_class.numeric_dimension?('480')).to be true
      expect(described_class.numeric_dimension?('320.5')).to be true
    end

    it 'rejects .infinity / matchParent / bindings / nil' do
      expect(described_class.numeric_dimension?('.infinity')).to be false
      expect(described_class.numeric_dimension?('matchParent')).to be false
      expect(described_class.numeric_dimension?('@{maxW}')).to be false
      expect(described_class.numeric_dimension?(nil)).to be false
    end
  end

  describe 'responsive? instance method (via include)' do
    let(:converter_class) do
      Class.new do
        include SjuiTools::SwiftUI::Views::ResponsiveHelper
      end
    end

    it 'returns true for component with responsive block' do
      obj = converter_class.new
      component = { 'responsive' => { 'regular' => {} } }
      expect(obj.responsive?(component)).to be true
    end

    it 'returns false for component without responsive block' do
      obj = converter_class.new
      component = { 'type' => 'View' }
      expect(obj.responsive?(component)).to be false
    end
  end
end
