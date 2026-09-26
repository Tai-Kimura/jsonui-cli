# frozen_string_literal: true

module RjuiTools
  module React
    module Converters
      # The one table from a component type to its converter — for a
      # layout's root (ReactGenerator#convert_component) and for every child
      # (BaseConverter#get_converter_class) alike. Until jsonui-cli 1.9.0
      # each kept its own table and they differed in two types: a root
      # NetworkImage went to ImageConverter (a plain <img>: no defaultImage,
      # no errorImage, contentMode as a class only) while a child went to
      # NetworkImageConverter; a root Toggle went to SwitchConverter while a
      # child went to ToggleConverter (a checkbox). The table takes
      # NetworkImageConverter (NetworkImage is its own component) and
      # SwitchConverter for Toggle — the SSoT declares Toggle `_alias_of:
      # Switch` (attribute_definitions.json), and the other faces draw it as
      # a switch. Extension converters are looked up before it, by each
      # caller, as before.
      module ConverterTable
        module_function

        def table
          @table ||= begin
            %w[view label button image network_image text_field text_view scroll_view collection switch toggle
               slider segment radio progress indicator select_box include tab_view embed icon_label
               circle_view web blur gradient_view].each { |file| require_relative "#{file}_converter" }
            {
              'View' => ViewConverter,
              'SafeAreaView' => ViewConverter,
              'Label' => LabelConverter,
              'Text' => LabelConverter,
              'Button' => ButtonConverter,
              'Image' => ImageConverter,
              'CircleImage' => ImageConverter,
              'NetworkImage' => NetworkImageConverter,
              'TextField' => TextFieldConverter,
              # EditText / Input are aliases for TextField (attribute_definitions
              # `_alias_of: TextField`; kept for Android / HTML naming compatibility)
              'EditText' => TextFieldConverter,
              'Input' => TextFieldConverter,
              'TextView' => TextViewConverter,
              'Scroll' => ScrollViewConverter,
              'ScrollView' => ScrollViewConverter,
              'Collection' => CollectionConverter,
              'Table' => CollectionConverter,
              'Switch' => SwitchConverter,
              # Toggle is `_alias_of: Switch` in the SSoT.
              'Toggle' => SwitchConverter,
              # CheckBox and its alias spellings are the simple checkbox.
              'CheckBox' => ToggleConverter,
              'Check' => ToggleConverter,
              'Checkbox' => ToggleConverter,
              'Slider' => SliderConverter,
              'Segment' => SegmentConverter,
              'Radio' => RadioConverter,
              'Progress' => ProgressConverter,
              'Indicator' => IndicatorConverter,
              'SelectBox' => SelectBoxConverter,
              'Include' => IncludeConverter,
              'TabView' => TabViewConverter,
              'Embed' => EmbedConverter,
              'IconLabel' => IconLabelConverter,
              'CircleView' => CircleViewConverter,
              'Web' => WebConverter,
              'Blur' => BlurConverter,
              'GradientView' => GradientViewConverter
            }.freeze
          end
        end
      end
    end
  end
end
