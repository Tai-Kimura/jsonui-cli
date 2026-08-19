# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/label_converter'

RSpec.describe RjuiTools::React::Converters::LabelConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'with basic text' do
      it 'renders a span with text content' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Hello World'
        })
        result = converter.convert
        expect(result).to include('<span')
        expect(result).to include('Hello World')
        expect(result).to include('</span>')
      end
    end

    context 'with binding expression' do
      it 'converts binding to JSX expression with viewModel.data prefix' do
        converter = create_converter({
          'type' => 'Label',
          'text' => '@{userName}'
        })
        result = converter.convert
        expect(result).to include('{`${data.userName ?? ""}`}')
      end
    end
  end

  describe '#build_class_name' do
    context 'with line clamp' do
      it 'adds truncate class for single line' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lines' => 1
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('truncate')
      end

      it 'adds line-clamp class for multiple lines' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lines' => 3
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('line-clamp-3')
      end

      # `line-clamp-N` IS a display utility (`display: -webkit-box`), and so is
      # `flex`. Same specificity, so the winner is decided by their order in
      # the generated stylesheet — measured `.line-clamp-2` at offset 7010 and
      # `.flex` at 7130, so flex won and the cap did nothing. The conformance
      # fixture rendered all five lines with `line-clamp-2` in its class list.
      it 'does not emit a competing display utility beside the clamp' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lines' => 3
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('line-clamp-3')
        expect(classes.split).not_to include('flex')
        expect(classes.split).not_to include('block')
      end

      it 'keeps the flex box for an unclamped label' do
        converter = create_converter({ 'type' => 'Label', 'text' => 'Test' })
        expect(converter.send(:build_class_name).split).to include('flex')
      end

      it 'keeps the flex box for a single-line truncate' do
        # `truncate` sets no display of its own, so it does not collide.
        converter = create_converter({ 'type' => 'Label', 'text' => 'Test', 'lines' => 1 })
        classes = converter.send(:build_class_name)
        expect(classes).to include('truncate')
        expect(classes.split).to include('flex')
      end

      it 'does not add line clamp for zero lines' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lines' => 0
        })
        classes = converter.send(:build_class_name)
        expect(classes).not_to include('truncate')
        expect(classes).not_to match(/line-clamp/)
      end

      # `lines` is declared `["number", "binding"]`, and `"@{n}" > 0` raised
      # `ArgumentError: comparison of String with 0 failed` — `jui build`
      # aborted on the declared spelling (plan 41). A runtime cap cannot be a
      # `line-clamp-N` class, so it becomes the four declarations that class
      # expands to.
      it 'routes a bound line cap into the inline style' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lines' => '@{maxLines}'
        })
        expect(converter.send(:build_class_name)).not_to match(/line-clamp|truncate/)
        style = converter.send(:build_style_attr)
        expect(style).to include("display: '-webkit-box'")
        expect(style).to include("WebkitBoxOrient: 'vertical'")
        expect(style).to include('WebkitLineClamp: data.maxLines')
        expect(style).to include("overflow: 'hidden'")
      end

      it 'does not force nowrap on a bound cap' do
        # The runtime number decides how many lines; `nowrap` would defeat
        # any cap above one, and the comparison that used to make this
        # decision raised on a bound value.
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lines' => '@{maxLines}',
          'lineBreakMode' => 'Tail'
        })
        converter.send(:build_class_name)
        expect(converter.send(:build_style_attr)).not_to include("whiteSpace: 'nowrap'")
      end

      it 'still forces nowrap on a single static line' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lines' => 1,
          'lineBreakMode' => 'Tail'
        })
        converter.send(:build_class_name)
        expect(converter.send(:build_style_attr)).to include("whiteSpace: 'nowrap'")
      end
    end

    context 'with underline' do
      it 'adds underline class' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Underlined text',
          'underline' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('underline')
      end
    end

    context 'with strikethrough' do
      it 'adds line-through class' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Strikethrough text',
          'strikethrough' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('line-through')
      end
    end

    # The object face. Contract: attribute_semantics.json -> textDecoration.
    # The presence test this replaces was `if attributes['underline']`, and a
    # Hash is truthy in Ruby, so every object — including the one that means
    # "draw nothing" — drew the same plain line.
    context 'with a styled text decoration' do
      def classes_for(attrs)
        create_converter({ 'type' => 'Label', 'text' => 'Styled' }.merge(attrs)).send(:build_class_name)
      end

      it 'draws nothing for lineStyle None' do
        expect(classes_for('underline' => { 'lineStyle' => 'None' })).not_to include('underline')
        expect(classes_for('strikethrough' => { 'lineStyle' => 'None' })).not_to include('line-through')
      end

      it 'draws the plain line for an object that styles nothing' do
        expect(classes_for('underline' => {})).to include('underline')
      end

      it 'maps each declared lineStyle' do
        expect(classes_for('underline' => { 'lineStyle' => 'Single' })).to include('decoration-solid')
        expect(classes_for('underline' => { 'lineStyle' => 'Double' })).to include('decoration-double')
        expect(classes_for('underline' => { 'lineStyle' => 'Thick' })).to include('decoration-2')
      end

      it 'colours the line without touching the text colour' do
        classes = classes_for('underline' => { 'color' => '#FF0000' })
        expect(classes).to include('decoration-[#FF0000]')
        expect(classes).not_to include('text-[#FF0000]')
      end

      it 'routes a bound colour through a custom property' do
        converter = create_converter({ 'type' => 'Label', 'text' => 'Styled',
                                       'underline' => { 'color' => '@{lineColor}' } })
        expect(converter.send(:build_class_name)).to include('decoration-[var(--jui-underline-color)]')
        expect(converter.send(:build_style_attr)).to include('--jui-underline-color')
      end

      # lineOffset is declared on underline only, and strikethrough must not
      # invent one.
      it 'applies lineOffset to underline and never to strikethrough' do
        expect(classes_for('underline' => { 'lineOffset' => 3 })).to include('underline-offset-[3px]')
        expect(classes_for('strikethrough' => { 'lineOffset' => 3 })).not_to include('underline-offset')
      end

      # Two utilities, one CSS property: as classes, whichever the stylesheet
      # orders last would win and the other line would vanish.
      it 'keeps both lines when a label asks for both' do
        converter = create_converter({ 'type' => 'Label', 'text' => 'Both',
                                       'underline' => true, 'strikethrough' => true })
        converter.send(:build_class_name)
        expect(converter.send(:build_style_attr)).to include("textDecorationLine: 'underline line-through'")
      end
    end

    context 'with onClick' do
      it 'adds cursor-pointer class' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Clickable',
          'onClick' => 'handleClick'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('cursor-pointer')
      end
    end

    context 'with linkable' do
      it 'adds cursor-pointer class' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Visit https://example.com',
          'linkable' => true
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('cursor-pointer')
      end
    end
  end

  describe '#build_style_attr' do
    context 'with lineHeightMultiple' do
      it 'sets lineHeight style' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lineHeightMultiple' => 1.5
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include('lineHeight: 1.5')
      end
    end

    context 'with lineSpacing' do
      it 'calculates lineHeight from lineSpacing and fontSize' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lineSpacing' => 8,
          'fontSize' => 16
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        # lineHeight = (16 + 8) / 16 = 1.5
        expect(result).to include('lineHeight: 1.5')
      end

      it 'uses default fontSize of 16 when not specified' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'lineSpacing' => 8
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include('lineHeight: 1.5')
      end
    end

    context 'with edgeInset' do
      it 'handles single value' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'edgeInset' => 10
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px'")
      end

      it 'handles 2-element array' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'edgeInset' => [10, 20]
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px 20px'")
      end

      it 'handles 4-element array' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'edgeInset' => [10, 20, 30, 40]
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px 20px 30px 40px'")
      end

      it 'handles pipe-separated string' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'edgeInset' => '10|20|30|40'
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("padding: '10px 20px 30px 40px'")
      end
    end

    context 'with disabled state' do
      it 'sets color to disabledFontColor when enabled is false' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Test',
          'enabled' => false,
          'disabledFontColor' => '#999999'
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("color: '#999999'")
      end
    end

    context 'with lineBreakMode' do
      it 'handles Head truncation' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Long text that will be truncated',
          'lineBreakMode' => 'Head'
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("textOverflow: 'ellipsis'")
        expect(result).to include("direction: 'rtl'")
        expect(result).to include("textAlign: 'left'")
        expect(result).to include("overflow: 'hidden'")
      end

      it 'handles Tail truncation' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Long text',
          'lineBreakMode' => 'Tail'
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("textOverflow: 'ellipsis'")
        expect(result).to include("overflow: 'hidden'")
        expect(result).to include("whiteSpace: 'nowrap'")
      end

      it 'handles Middle truncation (falls back to ellipsis)' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Long text',
          'lineBreakMode' => 'Middle'
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("textOverflow: 'ellipsis'")
      end

      it 'does not add whiteSpace nowrap when lines > 1' do
        converter = create_converter({
          'type' => 'Label',
          'text' => 'Long text',
          'lineBreakMode' => 'Tail',
          'lines' => 2
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).not_to include("whiteSpace: 'nowrap'")
      end
    end

    # The style object used to carry `min(<size>px, max(<size*factor>px, 1vw))`
    # for autoShrink. That sizes text against the VIEWPORT, which says nothing
    # about whether the text fits its box: a 16px Label rendered at 8px on a
    # 375px-wide phone, and on a wide viewport the 1vw term outran both floors
    # so minimumScaleFactor changed nothing (measured 0 differing px against
    # the control — plan 51-A). The fit is measured at runtime now.
    context 'with autoShrink' do
      it 'writes no font size into the style object' do
        converter = create_converter({
          'type' => 'Label', 'id' => 'shrinking', 'text' => 'Test',
          'autoShrink' => true, 'fontSize' => 20, 'minimumScaleFactor' => 0.5
        })
        converter.send(:build_class_name)
        expect(converter.send(:build_style_attr)).not_to include('1vw')
      end

      it 'attaches the ref the hoisted fit effect writes through' do
        converter = create_converter({
          'type' => 'Label', 'id' => 'shrinking_label', 'text' => 'Test',
          'autoShrink' => true, 'fontSize' => 20, 'minimumScaleFactor' => 0.25
        })
        expect(converter.convert).to include('ref={shrinkingLabelShrinkRef}')
      end

      # A literal id is what ties the ref to the hoisted declaration, exactly
      # as for the focus and collection-scroll helpers.
      it 'attaches no ref without a literal id' do
        converter = create_converter({
          'type' => 'Label', 'text' => 'Test', 'autoShrink' => true
        })
        expect(converter.convert).not_to include('ShrinkRef')
      end

      it 'attaches no ref when autoShrink is off' do
        converter = create_converter({
          'type' => 'Label', 'id' => 'plain', 'text' => 'Test', 'autoShrink' => false
        })
        expect(converter.convert).not_to include('ShrinkRef')
      end
    end
  end

  # Canon since rjui-label-linkable-binding-renders-raw: the converter no
  # longer splits literals at build time — detection (URL AND phone), tel:
  # sanitization and newline preservation live in the LinkifyText runtime so
  # literal and bound text share one implementation. The anchor-tag contract
  # (target/_blank, noopener) is pinned on the template in label_linkable_spec.
  describe 'linkable text rendering' do
    it 'routes literal text through the LinkifyText runtime' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Visit https://example.com today',
        'linkable' => true
      })
      result = converter.convert
      expect(result).to include('<LinkifyText')
      expect(result).to include('text={`Visit https://example.com today`}')
      expect(result).not_to include('<a href')
    end

    it 'hands multiple URLs over intact for runtime detection' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Check https://foo.com and https://bar.com',
        'linkable' => true
      })
      result = converter.convert
      expect(result).to include('text={`Check https://foo.com and https://bar.com`}')
    end
  end

  # web-partial-labels-render-inside-a-flex-row: partialText returns one node
  # per run, so a flex wrapper turns every run into its own line box and the
  # paragraph lays out as a single unwrapping row.
  describe 'multi-run labels lay out as paragraphs, not flex rows' do
    it 'drops the flex wrapper when partialAttributes are present' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'See the docs for details.',
        'partialAttributes' => [{ 'range' => [4, 12], 'onclick' => 'openDocs' }]
      })
      result = converter.convert
      expect(result).not_to match(/className="[^"]*\bflex\b/)
      expect(result).not_to match(/className="[^"]*\bitems-center\b/)
      expect(result).to match(/className="[^"]*\bblock\b/)
    end

    it 'drops the flex wrapper for linkable text' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Visit https://example.com now',
        'linkable' => true
      })
      result = converter.convert
      expect(result).not_to match(/className="[^"]*\bflex\b/)
      expect(result).to match(/className="[^"]*\bblock\b/)
    end

    it 'keeps horizontal alignment via text-* instead of flex justify-*' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Centered paragraph',
        'textAlign' => 'center',
        'partialAttributes' => [{ 'range' => [0, 8], 'underline' => true }]
      })
      result = converter.convert
      expect(result).to include('text-center')
      expect(result).not_to include('justify-center')
    end

    it 'still centers a single-run label with flex' do
      converter = create_converter({ 'type' => 'Label', 'text' => 'Plain' })
      result = converter.convert
      expect(result).to match(/className="[^"]*\bflex\b/)
      expect(result).to match(/className="[^"]*\bitems-center\b/)
    end
  end

  describe 'partialAttributes rendering' do
    it 'renders styled spans for text ranges' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Hello World',
        'partialAttributes' => [
          {
            'range' => [0, 5],
            'fontColor' => '#FF0000',
            'fontWeight' => 'bold'
          }
        ]
      })
      result = converter.convert
      # Partials are applied at RUNTIME against the resolved string, so the
      # build emits the spec rather than pre-sliced spans.
      expect(result).to include('partialText(`Hello World`,')
      expect(result).to include("range: [0, 5]")
      # Colors route through TailwindMapper like the main fontColor path,
      # so a palette TOKEN survives as a class instead of becoming an
      # invalid inline `color: 'accent'`.
      expect(result).to include("style: { fontWeight: 'bold' }")
      expect(result).to include("className: 'text-[#FF0000]'")
    end

    it 'handles multiple partial attributes' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Red Green Blue',
        'partialAttributes' => [
          { 'range' => [0, 3], 'fontColor' => '#FF0000' },
          { 'range' => [4, 9], 'fontColor' => '#00FF00' },
          { 'range' => [10, 14], 'fontColor' => '#0000FF' }
        ]
      })
      result = converter.convert
      expect(result).to include("text-[#FF0000]")
      expect(result).to include("text-[#00FF00]")
      expect(result).to include("text-[#0000FF]")
    end

    it 'applies underline to partial' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5], 'underline' => true }
        ]
      })
      result = converter.convert
      expect(result).to include("className: 'underline'")
    end

    it 'applies strikethrough to partial' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Hello World',
        'partialAttributes' => [
          { 'range' => [0, 5], 'strikethrough' => true }
        ]
      })
      result = converter.convert
      expect(result).to include("className: 'line-through'")
    end

    it 'applies onclick to partial' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Click Here for more',
        'partialAttributes' => [
          { 'range' => [0, 10], 'onclick' => 'handlePartialClick' }
        ]
      })
      result = converter.convert
      # Intended change (2026-07-24): partial onclick now follows the base
      # onclick contract — selector resolves to a data.-prefixed reference.
      expect(result).to include('onClick: data.handlePartialClick')
      expect(result).to include('cursor-pointer')
    end

    it 'applies fontSize to partial' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Big Text',
        'partialAttributes' => [
          { 'range' => [0, 3], 'fontSize' => 24 }
        ]
      })
      result = converter.convert
      expect(result).to include("fontSize: '24px'")
    end

    it 'applies background to partial' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Highlighted',
        'partialAttributes' => [
          { 'range' => [0, 11], 'background' => '#FFFF00' }
        ]
      })
      result = converter.convert
      expect(result).to include("bg-[#FFFF00]")
    end
  end

  describe '#escape_jsx_text' do
    it 'escapes curly braces in text' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Test {value}'
      })
      # Access private method
      result = converter.send(:escape_jsx_text, 'Test {value}')
      expect(result).to eq('{`Test {value}`}')
    end

    it 'escapes angle brackets' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'a < b > c'
      })
      result = converter.send(:escape_jsx_text, 'a < b > c')
      expect(result).to eq('{`a < b > c`}')
    end

    it 'returns plain text when no special characters' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Plain text'
      })
      result = converter.send(:escape_jsx_text, 'Plain text')
      expect(result).to eq('Plain text')
    end

    it 'escapes template literal characters' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Value: ${name}'
      })
      result = converter.send(:escape_jsx_text, 'Value: ${name}')
      expect(result).to include('\\${')
    end
  end

  describe 'testId and tag attributes' do
    it 'includes data-testid when testId is present' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Test',
        'testId' => 'label-test-id'
      })
      result = converter.convert
      expect(result).to include('data-testid="label-test-id"')
    end

    it 'includes data-tag when tag is present' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Test',
        'tag' => 'custom-tag'
      })
      result = converter.convert
      expect(result).to include('data-tag="custom-tag"')
    end
  end

  # The reason partials moved to runtime rendering: these three shapes are
  # impossible to resolve during the build, and iOS/Android have always
  # supported them. Each was silently broken on web before.
  describe 'partialAttributes runtime resolution' do
    it 'keeps a text-pattern range instead of dropping it' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Go to screen identity now',
        'partialAttributes' => [
          { 'range' => 'screen identity', 'fontColor' => '#2563EB', 'onclick' => 'onNavigate' }
        ]
      })
      result = converter.convert
      # Used to vanish entirely — no span, no handler, no warning.
      expect(result).to include("range: 'screen identity'")
      expect(result).to include('onClick: data.onNavigate')
    end

    it 'resolves a bound text at runtime rather than slicing the expression' do
      converter = create_converter({
        'type' => 'Label',
        'text' => '@{bodyText}',
        'partialAttributes' => [{ 'range' => [0, 6], 'fontColor' => '#2563EB' }]
      })
      result = converter.convert
      # Used to emit `{`@{body`}` + `{`Text}`}` — the expression itself cut
      # in half at offset 6.
      expect(result).to include('partialText(`${data.bodyText ?? ""}`')
      expect(result).not_to include('@{body`')
    end

    it 'passes a binding range through to the runtime' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Highlight some of this',
        'partialAttributes' => [{ 'range' => '@{highlightRange}', 'underline' => true }]
      })
      result = converter.convert
      expect(result).to include('range: data.highlightRange')
    end

    it 'emits one runtime call, not pre-sliced spans' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Red Green Blue',
        'partialAttributes' => [
          { 'range' => [0, 3], 'fontColor' => '#FF0000' },
          { 'range' => [4, 9], 'fontColor' => '#00FF00' }
        ]
      })
      result = converter.convert
      expect(result.scan('partialText(').length).to eq(1)
      expect(result).not_to include('>Red<')
    end
  end

  describe 'partialAttributes palette colors' do
    it 'emits a palette token as a class, never as an inline CSS color' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'See the guide',
        'partialAttributes' => [
          { 'range' => 'guide', 'fontColor' => 'accent', 'background' => 'surface' }
        ]
      })
      result = converter.convert
      # L1 normalization rewrites a palette hex to its token name, and
      # `color: 'accent'` is not a CSS color — the browser drops it and the
      # text comes out unstyled.
      expect(result).to include('text-accent')
      expect(result).to include('bg-surface')
      expect(result).not_to include("color: 'accent'")
      expect(result).not_to include("backgroundColor: 'surface'")
    end
  end

  describe 'partialAttributes onclick emit' do
    it 'emits data-prefixed onClick for selector format' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Tap here now',
        'partialAttributes' => [
          { 'range' => [0, 3], 'fontColor' => '#FF0000', 'onclick' => 'handleTap' }
        ]
      })
      result = converter.convert
      expect(result).to include('onClick: data.handleTap')
      expect(result).not_to include('onClick={handleTap}')
    end

    it 'emits ERROR comment for binding-format onclick (selector required, matching base contract)' do
      converter = create_converter({
        'type' => 'Label',
        'text' => 'Tap here now',
        'partialAttributes' => [
          { 'range' => [0, 3], 'onclick' => '@{handleTap}' }
        ]
      })
      result = converter.convert
      expect(result).to include('ERROR: onclick requires selector format')
      expect(result).not_to include('onClick={@{handleTap}}')
    end
  end
  # highlightAttributes / highlightColor take over while `selected` is true.
  # Canonical semantics come from the iOS UIKit runtime, which keeps two
  # attribute dictionaries and swaps on `selected`.
  describe 'highlight state' do
    it 'swaps at runtime when selected is a binding' do
      result = create_converter({
        'type' => 'Label', 'text' => 'Hi', 'fontSize' => 14, 'fontColor' => '#000000',
        'selected' => '@{isChosen}',
        'highlightAttributes' => { 'fontSize' => 24, 'fontColor' => '#FF0000' }
      }).convert

      expect(result).to include('className={data.isChosen ?')
      expect(result).to include('text-[#FF0000]')
    end

    # Tailwind precedence comes from stylesheet order, not attribute order, so
    # `text-black text-red-500` in one class list has no defined winner.
    it 'replaces the base font classes rather than appending to them' do
      result = create_converter({
        'type' => 'Label', 'text' => 'Hi', 'fontSize' => 14, 'fontColor' => '#000000',
        'selected' => '@{isChosen}',
        'highlightAttributes' => { 'fontSize' => 24, 'fontColor' => '#FF0000' }
      }).convert
      highlighted = result[/className=\{data\.isChosen \? "([^"]*)"/, 1]

      expect(highlighted).to include('text-[#FF0000]')
      expect(highlighted).not_to include('text-[#000000]')
      expect(highlighted).not_to include('text-sm')
    end

    it 'keeps the base branch intact for the unselected state' do
      result = create_converter({
        'type' => 'Label', 'text' => 'Hi', 'fontColor' => '#000000',
        'selected' => '@{isChosen}', 'highlightColor' => '#00FF00'
      }).convert
      base = result[/: "([^"]*)"\}/, 1]

      expect(base).to include('text-[#000000]')
      expect(base).not_to include('text-[#00FF00]')
    end

    it 'needs no runtime branch when selected is literally true' do
      result = create_converter({
        'type' => 'Label', 'text' => 'Hi', 'fontColor' => '#000000', 'selected' => true,
        'highlightAttributes' => { 'fontColor' => '#FF0000' }
      }).convert

      expect(result).to include('className="')
      expect(result).not_to include('?')
      expect(result).to include('text-[#FF0000]')
      expect(result).not_to include('text-[#000000]')
    end

    # SJUILabel's creator: a non-empty highlightAttributes wins, otherwise
    # highlightColor.
    it 'prefers highlightAttributes and falls through when it has no usable key' do
      both = create_converter({
        'type' => 'Label', 'text' => 'Hi', 'selected' => true,
        'highlightAttributes' => { 'fontColor' => '#FF0000' }, 'highlightColor' => '#00FF00'
      }).convert
      expect(both).to include('text-[#FF0000]')
      expect(both).not_to include('text-[#00FF00]')

      empty = create_converter({
        'type' => 'Label', 'text' => 'Hi', 'selected' => true,
        'highlightAttributes' => {}, 'highlightColor' => '#00FF00'
      }).convert
      expect(empty).to include('text-[#00FF00]')
    end

    # textAlign is two classes on web: text-* from the base converter and
    # justify-* because a single-run label is a flex container.
    it 'swaps both the text-* and justify-* classes for textAlign' do
      result = create_converter({
        'type' => 'Label', 'text' => 'Hi', 'textAlign' => 'Left', 'selected' => '@{sel}',
        'highlightAttributes' => { 'textAlign' => 'Center' }
      }).convert
      highlighted = result[/className=\{data\.sel \? "([^"]*)"/, 1]

      expect(highlighted).to include('text-center')
      expect(highlighted).to include('justify-center')
      expect(highlighted).not_to include('text-left')
      expect(highlighted).not_to include('justify-start')
    end

    # Line height is a unitless multiplier in the style object, not a class.
    it 'swaps lineHeight through the style object' do
      result = create_converter({
        'type' => 'Label', 'text' => 'Hi', 'lineHeightMultiple' => 1.2,
        'selected' => '@{sel}', 'highlightAttributes' => { 'lineHeightMultiple' => 1.5 }
      }).convert

      expect(result).to include('lineHeight: (data.sel ? 1.5 : 1.2)')
    end

    it 'falls back to CSS normal when the base sets no line height' do
      result = create_converter({
        'type' => 'Label', 'text' => 'Hi', 'selected' => '@{sel}',
        'highlightAttributes' => { 'lineHeightMultiple' => 1.5 }
      }).convert

      expect(result).to include("lineHeight: (data.sel ? 1.5 : 'normal')")
    end

    it 'leaves the class list untouched when there is no driver' do
      with_driver = create_converter({
        'type' => 'Label', 'text' => 'Hi', 'fontColor' => '#000000', 'highlightColor' => '#00FF00'
      }).convert
      without = create_converter({
        'type' => 'Label', 'text' => 'Hi', 'fontColor' => '#000000'
      }).convert

      expect(with_driver).to eq(without)
    end
  end
end

RSpec.describe RjuiTools::React::Converters::LabelConverter, 'web-only text attributes' do
  let(:config) { { 'use_tailwind' => true } }

  def label(extra)
    described_class.new({ 'class' => 'Label', 'text' => 'hi' }.merge(extra), config).convert(2)
  end

  # Declared `platform: react`: CSS text-transform is the web's own capability.
  it 'maps every textTransform value' do
    expect(label('textTransform' => 'uppercase')).to include('uppercase')
    expect(label('textTransform' => 'lowercase')).to include('lowercase')
    expect(label('textTransform' => 'capitalize')).to include('capitalize')
  end

  # `none` is the CSS initial value, but a style block may have set another, so
  # it is spelled out rather than omitted.
  it 'spells out none' do
    expect(label('textTransform' => 'none')).to include('normal-case')
  end

  it 'ignores an unknown value' do
    result = label('textTransform' => 'smallcaps')
    %w[uppercase lowercase capitalize normal-case].each { |c| expect(result).not_to include(c) }
  end

  # lineHeight is the CSS property directly, in px.
  it 'emits lineHeight in px' do
    expect(label('lineHeight' => 28)).to include("lineHeight: '28px'")
  end

  # The cross-platform spellings are the multiplier and the extra spacing, so
  # they win over the web-only literal.
  it 'yields to lineHeightMultiple and lineSpacing' do
    expect(label('lineHeight' => 28, 'lineHeightMultiple' => 1.5)).to include('lineHeight: 1.5')
    expect(label('lineHeight' => 28, 'lineHeightMultiple' => 1.5)).not_to include('28px')
    expect(label('lineHeight' => 28, 'lineSpacing' => 4, 'fontSize' => 16)).not_to include('28px')
  end
end
