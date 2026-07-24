# frozen_string_literal: true

require 'swiftui/views/selectbox_converter'

RSpec.describe SjuiTools::SwiftUI::Views::SelectBoxConverter do
  before(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = false
  end

  after(:all) do
    SjuiTools::SwiftUI::Views::BaseViewConverter.validation_enabled = true
  end

  describe '#convert' do
    context 'with basic selectbox' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'id' => 'countrySelector'
        }
      end

      it 'generates SelectBoxView' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('SelectBoxView(')
        expect(code).to include('id: "countrySelector"')
      end
    end

    context 'with prompt' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'prompt' => 'Select a country'
        }
      end

      it 'includes prompt parameter' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('prompt: "Select a country"')
      end
    end

    context 'with static items' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'items' => ['Apple', 'Banana', 'Cherry']
        }
      end

      it 'includes items array' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('items: ["Apple", "Banana", "Cherry"]')
      end
    end

    context 'with binding items' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'items' => '@{countryList}'
        }
      end

      # Bindings resolve through the view-data model, so the binding `@{countryList}`
      # becomes `data.countryList` in the generated Swift.
      it 'uses binding for items' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('items: Array(data.countryList)')
      end
    end

    context 'with Date selectItemType' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'selectItemType' => 'Date'
        }
      end

      it 'sets selectItemType to date' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('selectItemType: .date')
      end
    end

    context 'with datePickerMode time' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'datePickerMode' => 'time'
        }
      end

      it 'sets datePickerMode to time' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('datePickerMode: .time')
      end
    end

    context 'with datePickerMode datetime' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'datePickerMode' => 'datetime'
        }
      end

      it 'sets datePickerMode to dateTime' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('datePickerMode: .dateTime')
      end
    end

    context 'with datePickerStyle' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'datePickerStyle' => 'compact'
        }
      end

      it 'sets datePickerStyle' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('datePickerStyle: .compact')
      end
    end

    context 'with datePickerStyle graphical' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'datePickerStyle' => 'graphical'
        }
      end

      it 'sets datePickerStyle to graphical' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('datePickerStyle: .graphical')
      end
    end

    context 'with dateStringFormat' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'dateStringFormat' => 'yyyy-MM-dd'
        }
      end

      it 'includes dateStringFormat' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('dateStringFormat: "yyyy-MM-dd"')
      end
    end

    context 'with selectedDate (Date mode)' do
      it 'forwards the optional from String.toDate without falling back to today' do
        component = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'dateStringFormat' => 'yyyy-MM-dd',
          'selectedDate' => '@{fromDate}'
        }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('selectedDate: data.fromDate.toDate(format: "yyyy-MM-dd")')
        expect(code).not_to include('?? Date()')
      end

      it 'forwards the optional for literal selectedDate too' do
        component = {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'dateStringFormat' => 'yyyy-MM-dd',
          'selectedDate' => '2026-01-01'
        }
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('selectedDate: "2026-01-01".toDate(format: "yyyy-MM-dd")')
        expect(code).not_to include('?? Date()')
      end
    end

    context 'with minimumDate and maximumDate' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'minimumDate' => '2020-01-01',
          'maximumDate' => '2030-12-31'
        }
      end

      it 'includes date constraints' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('minimumDate:')
        expect(code).to include('maximumDate:')
      end
    end

    context 'with minuteInterval' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'selectItemType' => 'Date',
          'datePickerMode' => 'time',
          'minuteInterval' => 15
        }
      end

      it 'includes minuteInterval' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('minuteInterval: 15')
      end
    end

    context 'with selectedIndex' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'items' => ['A', 'B', 'C'],
          'selectedIndex' => 1
        }
      end

      it 'includes selectedIndex' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('selectedIndex: 1')
      end
    end

    context 'with styling' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'fontSize' => 16,
          'fontColor' => '#333333',
          'background' => '#FFFFFF',
          'cornerRadius' => 8
        }
      end

      it 'includes styling parameters' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('fontSize: 16')
        expect(code).to include('fontColor:')
        expect(code).to include('backgroundColor:')
        expect(code).to include('cornerRadius: 8')
      end
    end

    context 'with paddings' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'paddings' => 16
        }
      end

      it 'includes padding EdgeInsets' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('padding: EdgeInsets(')
      end
    end

    context 'with paddings array' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'paddings' => [10, 20]
        }
      end

      it 'includes padding with array values' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('padding: EdgeInsets(top: 10')
      end
    end

    context 'with border' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'borderWidth' => 1,
          'borderColor' => '#CCCCCC',
          'cornerRadius' => 8
        }
      end

      it 'adds overlay with stroke' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.overlay(')
        expect(code).to include('RoundedRectangle')
        expect(code).to include('.stroke(')
      end
    end

    context 'with opacity' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'alpha' => 0.8
        }
      end

      it 'adds opacity modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0.8)')
      end
    end

    context 'with hidden' do
      let(:component) do
        {
          'type' => 'SelectBox',
          'hidden' => true
        }
      end

      it 'adds hidden modifier' do
        converter = described_class.new(component)
        code = converter.convert

        expect(code).to include('.opacity(0).accessibilityHidden(true)')
      end
    end
  end
end
