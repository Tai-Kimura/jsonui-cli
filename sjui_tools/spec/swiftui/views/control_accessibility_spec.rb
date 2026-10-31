# frozen_string_literal: true

require 'swiftui/converter_factory'

# A control's screen-reader name and a Label read out when it changes
# (shared/core/control_accessibility.rb): `accessibilityLabel` (alias
# `contentDescription`) is `.accessibilityLabel(Text(…))` on the element the
# chain forms, and a Label's `accessibilityLiveRegion` posts an announcement
# of its bound text when it changes. iOS has no live region, so a View's
# reads nothing (declared for web and Android). Until jsonui-cli 2.3.38
# neither was declared on these types, and nothing was emitted for them.
RSpec.describe 'iOS control accessibility' do
  before(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false }
  after(:all) { SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true }

  let(:factory) { SjuiTools::SwiftUI::ConverterFactory.new }

  def convert(node)
    factory.create_converter(JsonUIShared::TapAccessibility.annotate!(JSON.parse(JSON.generate(node)))).convert
  end

  describe 'accessibilityLabel' do
    {
      'Button' => { 'type' => 'Button', 'text' => 'Open', 'onClick' => '@{open}' },
      'TextField' => { 'type' => 'TextField', 'id' => 'f', 'text' => '@{q}' },
      'Slider' => { 'type' => 'Slider', 'id' => 's', 'value' => '@{v}' },
      'SelectBox' => { 'type' => 'SelectBox', 'id' => 'b', 'items' => %w[a b] },
      'CheckBox' => { 'type' => 'CheckBox', 'id' => 'c', 'checked' => '@{on}' },
      'Check (the alias section)' => { 'type' => 'Check', 'checked' => '@{on}' },
      'Switch' => { 'type' => 'Switch', 'isOn' => '@{on}' },
      'Segment' => { 'type' => 'Segment', 'id' => 'sg', 'items' => %w[a b] }
    }.each do |what, node|
      it "names #{what}, last on its chain" do
        code = convert(node.merge('accessibilityLabel' => 'Name'))
        expect(code.scan('.accessibilityLabel(').size).to eq(1)
        expect(code.rstrip).to end_with('.accessibilityLabel(Text("Name"))')
      end
    end

    it 'names a View that combines into one button, after it is combined' do
      code = convert({ 'type' => 'View', 'onClick' => '@{open}', 'accessibilityLabel' => 'Name',
                       'child' => [{ 'type' => 'Label', 'text' => 'Card' }] })
      expect(code.index('.accessibilityElement(children: .combine)')).to be < code.index('.accessibilityLabel(Text("Name"))')
    end

    it 'names nothing on a View that taps nothing (no element: the name would land on its children)' do
      code = convert({ 'type' => 'View', 'accessibilityLabel' => 'Name', 'child' => [{ 'type' => 'Label', 'text' => 'x' }] })
      expect(code).not_to include('.accessibilityLabel(')
    end

    it 'names a Radio in place of its text, on the element it forms' do
      code = convert({ 'type' => 'Radio', 'id' => 'r', 'text' => 'A', 'accessibilityLabel' => 'Name' })
      expect(code).to include(".accessibilityElement(children: .ignore)\n")
      expect(code.scan('.accessibilityLabel(').size).to eq(1)
      expect(code).to include('.accessibilityLabel("Name")')
    end

    it 'names a Radio with no text of its own' do
      code = convert({ 'type' => 'Radio', 'id' => 'r', 'accessibilityLabel' => 'Name' })
      expect(code).to include('.accessibilityElement(children: .ignore)')
      expect(code).to include('.accessibilityLabel("Name")')
    end

    it 'reads the contentDescription spelling the same' do
      expect(convert({ 'type' => 'Button', 'text' => 'Open', 'contentDescription' => 'Name' })).to include('.accessibilityLabel(Text("Name"))')
    end

    it 'takes a binding' do
      expect(convert({ 'type' => 'Button', 'text' => 'Open', 'accessibilityLabel' => '@{name}' }))
        .to include('.accessibilityLabel(Text((data.name ?? "")))')
    end
  end

  # The lines it adds reach a compiler, on a Text (StateAwareButtonView and
  # PartialAttributedText are the library's): a name from a binding, and a
  # Label's announcement.
  describe 'what it emits type-checks' do
    it 'for a name from a binding' do
      code = convert({ 'type' => 'Button', 'text' => 'Open', 'onClick' => '@{open}', 'accessibilityLabel' => '@{name}' })
      tail = code.lines.last.strip
      expect(tail).to start_with('.accessibilityLabel(')
      expect(compilable_view("Text(\"x\")\n#{tail}", data: ['var name: String? = nil'])).to compile_as_swift
    end

    it "for a Label's announcement" do
      code = convert({ 'type' => 'Label', 'text' => '@{status}', 'accessibilityLiveRegion' => 'assertive' })
      tail = code[code.index('.onChange')..]
      expect(compilable_view("Text(\"x\")\n#{tail}", data: ['var status: String? = nil'])).to compile_as_swift
    end
  end

  describe 'accessibilityLiveRegion' do
    # The three lines inside the onChange, as emitted (indentation aside).
    def announcement(priority)
      ['var announcement = AttributedString(newValue)',
       "announcement.accessibilitySpeechAnnouncementPriority = #{priority}",
       'AccessibilityNotification.Announcement(announcement).post()'].join("\n")
    end

    def convert(node)
      super.lines.map(&:strip).join("\n")
    end

    it 'announces a Label whose bound text changes' do
      code = convert({ 'type' => 'Label', 'text' => '@{status}', 'accessibilityLiveRegion' => 'polite' })
      expect(code).to include('.onChange(of: (data.status ?? "")) { _, newValue in')
      expect(code).to include(announcement('.default'))
    end

    it 'announces at high priority when assertive' do
      expect(convert({ 'type' => 'Label', 'text' => '@{error}', 'accessibilityLiveRegion' => 'assertive' }))
        .to include(announcement('.high'))
    end

    it 'announces nothing when off, or for a static text (it never changes)' do
      expect(convert({ 'type' => 'Label', 'text' => '@{s}', 'accessibilityLiveRegion' => 'off' })).not_to include('Announcement')
      expect(convert({ 'type' => 'Label', 'text' => 'Saved', 'accessibilityLiveRegion' => 'polite' })).not_to include('Announcement')
    end

    it 'does nothing on a View (iOS has no live region)' do
      code = convert({ 'type' => 'View', 'accessibilityLiveRegion' => 'polite', 'child' => [{ 'type' => 'Label', 'text' => '@{s}' }] })
      expect(code).not_to include('Announcement')
    end
  end
end
