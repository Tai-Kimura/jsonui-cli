# frozen_string_literal: true

require_relative '../../spec_helper'
require 'react/converters/button_converter'

RSpec.describe RjuiTools::React::Converters::ButtonConverter do
  let(:default_config) { { 'use_tailwind' => true } }

  def create_converter(json_data, config = nil)
    described_class.new(json_data, config || default_config)
  end

  describe '#convert' do
    context 'with basic button' do
      it 'renders a button with text' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Click Me'
        })
        result = converter.convert
        expect(result).to include('<button')
        expect(result).to include('Click Me')
        expect(result).to include('</button>')
      end
    end

    # Regression: rjui-hidden-binding-renders-static-class — a bound
    # `hidden` toggles the Tailwind class at runtime; only static values
    # bake `invisible` into the className. hidden = visibility:"invisible"
    # shorthand: keeps layout space (visibility:hidden), NOT display:none.
    context 'with hidden binding' do
      it 'emits a conditional invisible class instead of a static one' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Set default',
          'hidden' => '@{isDisabledFutureMethod}'
        })
        result = converter.convert
        expect(result).to include('className={`')
        expect(result).to include('${data.isDisabledFutureMethod ? "invisible" : ""}')
        expect(result).not_to match(/className="[^"]*\binvisible\b/)
      end

      it 'keeps a static invisible class for hidden: true' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Hidden',
          'hidden' => true
        })
        result = converter.convert
        expect(result).to match(/className="[^"]*\binvisible\b/)
        # never the collapsing display:none class
        expect(result).not_to match(/className="[^"]*\bhidden\b/)
        expect(result).not_to include('${')
      end

      it 'combines with a visibility binding wrapper' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Both',
          'hidden' => '@{isHidden}',
          'visibility' => '@{buttonVisibility}'
        })
        result = converter.convert
        expect(result).to include('{data.buttonVisibility !== "gone" &&')
        expect(result).to include('${data.isHidden ? "invisible" : ""}')
        expect(result).to include('${data.buttonVisibility === "invisible" ? "invisible" : ""}')
      end
    end

    context 'with href' do
      it 'wraps button in Link component' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Go',
          'href' => '/dashboard'
        })
        result = converter.convert
        expect(result).to include('<Link href="/dashboard">')
        expect(result).to include('<button')
        expect(result).to include('</button></Link>')
      end
    end

    context 'with onclick' do
      it 'adds onClick attribute with data prefix' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Submit',
          'onclick' => 'handleSubmit'
        })
        result = converter.convert
        expect(result).to include('onClick={data.handleSubmit}')
      end
    end

    context 'with binding expression' do
      it 'converts text binding with data prefix' do
        converter = create_converter({
          'type' => 'Button',
          'text' => '@{buttonLabel}'
        })
        result = converter.convert
        expect(result).to include('{`${data.buttonLabel ?? ""}`}')
      end
    end
  end

  describe '#build_class_name' do
    context 'with default styles' do
      it 'includes cursor-pointer and transition-colors' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('cursor-pointer')
        expect(classes).to include('transition-colors')
      end

      it 'includes default hover:opacity-80' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('hover:opacity-80')
      end

      it 'includes disabled:cursor-not-allowed' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('disabled:cursor-not-allowed')
      end
    end

    context 'with tapBackground' do
      it 'adds hover and active background colors' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test',
          'tapBackground' => '#FF0000'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('hover:bg-[#FF0000]')
        expect(classes).to include('active:bg-[#FF0000]')
        expect(classes).not_to include('hover:opacity-80')
      end
    end

    context 'with highlightBackground' do
      it 'adds hover background color' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test',
          'highlightBackground' => '#00FF00'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('hover:bg-[#00FF00]')
      end
    end

    context 'with highlightColor' do
      it 'adds hover text color' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test',
          'highlightColor' => '#0000FF'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('hover:text-[#0000FF]')
      end
    end

    context 'with disabledBackground' do
      it 'adds disabled background color' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test',
          'disabledBackground' => '#CCCCCC'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('disabled:bg-[#CCCCCC]')
        expect(classes).not_to include('disabled:opacity-50')
      end
    end

    context 'with disabledFontColor' do
      it 'adds disabled text color' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test',
          'disabledFontColor' => '#999999'
        })
        classes = converter.send(:build_class_name)
        expect(classes).to include('disabled:text-[#999999]')
      end
    end
  end

  describe '#build_style_attr' do
    context 'with cornerRadius' do
      it 'adds borderRadius style' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test',
          'cornerRadius' => 8
        })
        converter.send(:build_class_name)
        result = converter.send(:build_style_attr)
        expect(result).to include("borderRadius: '8px'")
      end
    end
  end

  describe '#build_disabled_attr' do
    context 'with enabled: false' do
      it 'adds disabled attribute' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test',
          'enabled' => false
        })
        result = converter.convert
        expect(result).to include(' disabled')
      end
    end

    context 'with enabled: true' do
      it 'does not add disabled attribute' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test',
          'enabled' => true
        })
        result = converter.convert
        # Should not have disabled attribute on the button itself
        # (disabled:xxx classes are for styling, not the attribute)
        expect(result).not_to match(/<button[^>]* disabled[^:>]/)
      end
    end

    context 'with enabled binding' do
      it 'adds disabled binding expression' do
        converter = create_converter({
          'type' => 'Button',
          'text' => 'Test',
          'enabled' => '@{isEnabled}'
        })
        result = converter.convert
        expect(result).to include(%q(disabled={!data.isEnabled}))
      end
    end
  end

  describe 'partialAttributes rendering' do
    it 'renders styled spans within button' do
      converter = create_converter({
        'type' => 'Button',
        'text' => 'Hello World',
        'partialAttributes' => [
          {
            'range' => [0, 5],
            'fontColor' => '#FF0000'
          }
        ]
      })
      result = converter.convert
      # Applied at RUNTIME against the resolved string, same as Label and
      # as the iOS/Android runtimes.
      expect(result).to include('partialText(`Hello World`,')
      expect(result).to include('range: [0, 5]')
      expect(result).to include("style: { color: '#FF0000' }")
    end

    it 'handles multiple partial attributes' do
      converter = create_converter({
        'type' => 'Button',
        'text' => 'Save Changes',
        'partialAttributes' => [
          { 'range' => [0, 4], 'fontWeight' => 'bold' },
          { 'range' => [5, 12], 'fontColor' => '#666666' }
        ]
      })
      result = converter.convert
      expect(result).to include("fontWeight: 'bold'")
      expect(result).to include("color: '#666666'")
    end

    it 'applies underline to partial' do
      converter = create_converter({
        'type' => 'Button',
        'text' => 'Click here',
        'partialAttributes' => [
          { 'range' => [0, 5], 'underline' => true }
        ]
      })
      result = converter.convert
      expect(result).to include("className: 'underline'")
    end

    it 'applies onclick to partial' do
      converter = create_converter({
        'type' => 'Button',
        'text' => 'Click here for info',
        'partialAttributes' => [
          { 'range' => [6, 10], 'onclick' => 'handleInfo' }
        ]
      })
      result = converter.convert
      # Intended change: Button used to emit a bare `onClick={handleInfo}`,
      # which resolves to nothing — Label already applied the data. prefix.
      # Both now go through the shared spec builder, so the base onclick
      # contract holds for Button too.
      expect(result).to include('onClick: data.handleInfo')
    end
  end

  describe 'testId and tag attributes' do
    it 'includes data-testid when testId is present' do
      converter = create_converter({
        'type' => 'Button',
        'text' => 'Test',
        'testId' => 'submit-button'
      })
      result = converter.convert
      expect(result).to include('data-testid="submit-button"')
    end

    it 'includes data-tag when tag is present' do
      converter = create_converter({
        'type' => 'Button',
        'text' => 'Test',
        'tag' => 'primary-action'
      })
      result = converter.convert
      expect(result).to include('data-tag="primary-action"')
    end
  end
end
