# frozen_string_literal: true

require_relative 'views/label_converter'
require_relative 'views/button_converter'
require_relative 'views/view_converter'
require_relative 'views/textfield_converter'
require_relative 'views/textview_converter'
require_relative 'views/image_converter'
require_relative 'views/scrollview_converter'
require_relative 'views/segment_converter'
require_relative 'views/progress_converter'
require_relative 'views/slider_converter'
require_relative 'views/indicator_converter'
require_relative 'views/table_converter'
require_relative 'views/collection_converter'
require_relative 'views/web_converter'
require_relative 'views/radio_converter'
require_relative 'views/selectbox_converter'
require_relative 'views/network_image_converter'
require_relative 'views/blur_converter'
require_relative 'views/gradient_view_converter'
require_relative 'views/icon_label_converter'
require_relative 'views/dynamic_component_converter'
require_relative 'views/toggle_converter'
require_relative 'views/checkbox_converter'
# include_converter is no longer used - includes are expanded inline by process_includes
require_relative 'views/tab_view_converter'
require_relative 'views/embed_converter'
require_relative 'view_registry'

module SjuiTools
  module SwiftUI
    class ConverterFactory
      attr_accessor :data_properties

      # Responsive function code strings collected during conversion.
      # Each entry is a String containing a complete @ViewBuilder function.
      attr_reader :responsive_functions

      # Counter for generating unique responsive function names
      attr_reader :responsive_counter

      def initialize(binding_registry = nil)
        @view_registry = ViewRegistry.new
        @binding_registry = binding_registry
        @custom_converters = load_custom_converters
        @data_properties = []
        @responsive_functions = []
        @responsive_counter = 0
        STDERR.puts "[ConverterFactory] Loaded custom converters: #{@custom_converters.inspect}" if ENV['DEBUG']
      end

      # Generate a unique responsive function name and increment the counter.
      # @return [String] function name like "responsive0", "responsive1", etc.
      def next_responsive_name
        name = "responsive#{@responsive_counter}"
        @responsive_counter += 1
        name
      end

      # Register a responsive function code string for later emission.
      # @param code [String] the complete Swift function code
      def register_responsive_function(code)
        @responsive_functions << code
      end

      # Reset responsive state (call before each file conversion)
      def reset_responsive
        @responsive_functions = []
        @responsive_counter = 0
      end

      def load_custom_converters
        mappings_file = File.join(__dir__, 'views', 'extensions', 'converter_mappings.rb')

        puts "DEBUG: Looking for mappings at: #{mappings_file}" if ENV['DEBUG']

        # Return empty hash if mappings file doesn't exist
        unless File.exist?(mappings_file)
          puts "DEBUG: Mappings file does not exist" if ENV['DEBUG']
          return {}
        end

        begin
          # Load the mappings file
          require_relative 'views/extensions/converter_mappings'

          # Get the mappings if the constant exists
          if defined?(SjuiTools::SwiftUI::Views::Extensions::CONVERTER_MAPPINGS)
            SjuiTools::SwiftUI::Views::Extensions::CONVERTER_MAPPINGS
          elsif defined?(Views::Extensions::CONVERTER_MAPPINGS)
            Views::Extensions::CONVERTER_MAPPINGS
          else
            {}
          end
        rescue LoadError, StandardError => e
          # If there's any error loading the mappings, just use empty hash
          puts "Warning: Could not load custom converter mappings: #{e.message}" if ENV['DEBUG']
          {}
        end
      end

      def create_converter(component, indent_level = 0, action_manager = nil, converter_factory = nil, view_registry = nil)
        # Skip data definition objects (metadata, not UI components)
        if component['data'] && !component['type']
          return nil
        end

        # includeは process_includes でインライン展開されるため、ここに来ることはない
        if component['include']
          raise "Include should have been expanded by process_includes. This is a bug."
        end

        component_type = component['type']
        registry = view_registry || @view_registry

        # Check if there's a custom converter for this component type
        if @custom_converters && @custom_converters[component_type]
          converter_class_name = @custom_converters[component_type]
          puts "DEBUG: Found custom converter for #{component_type}: #{converter_class_name}" if ENV['DEBUG']

          begin
            # Load the custom converter file if not already loaded
            converter_file = converter_class_name.gsub(/([A-Z])/, '_\1').downcase.sub(/^_/, '')
            puts "DEBUG: [Loading converter] File: views/extensions/#{converter_file}, Class: #{converter_class_name}" if ENV['DEBUG']
            require_relative "views/extensions/#{converter_file}"

            # Get the converter class
            converter_class = if defined?(SjuiTools::SwiftUI::Views::Extensions)
              SjuiTools::SwiftUI::Views::Extensions.const_get(converter_class_name)
            else
              Views::Extensions.const_get(converter_class_name)
            end

            puts "DEBUG: [Converter loaded] Successfully loaded #{converter_class_name}" if ENV['DEBUG']

            # Create and return the custom converter instance
            return converter_class.new(component, indent_level, action_manager, self, registry, @binding_registry)
          rescue LoadError, NameError => e
            STDERR.puts "[Converter error] Failed to load #{converter_class_name}: #{e.message}" if ENV['DEBUG']
            STDERR.puts "  Backtrace: #{e.backtrace.first(3).join("\n  ")}" if ENV['DEBUG']
            # Fall through to standard converters
          end
        end

        case component_type
        when 'Label', 'Text'
          Views::LabelConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'IconLabel'
          Views::IconLabelConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Button'
          Views::ButtonConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'View', 'SafeAreaView'
          Views::ViewConverter.new(component, indent_level, action_manager, self, registry, @binding_registry)
        when 'GradientView'
          Views::GradientViewConverter.new(component, indent_level, action_manager, self, registry, @binding_registry)
        when 'Blur', 'BlurView'
          Views::BlurConverter.new(component, indent_level, action_manager, self, registry, @binding_registry)
        # EditText / Input are aliases for TextField (attribute_definitions
        # `_alias_of: TextField`; kept for Android / HTML naming compatibility)
        when 'TextField', 'EditText', 'Input'
          Views::TextFieldConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Image', 'CircleImage'
          Views::ImageConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'NetworkImage'
          Views::NetworkImageConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Scroll', 'ScrollView'
          Views::ScrollViewConverter.new(component, indent_level, action_manager, self, registry, @binding_registry)
        when 'TextView'
          Views::TextViewConverter.new(component, indent_level, action_manager, @binding_registry)
        # Switch/Toggle: Both component types supported for backward compatibility
        # "Switch" is primary name, "Toggle" is alias (see attribute_definitions.json)
        when 'Switch', 'Toggle'
          Views::ToggleConverter.new(component, indent_level, action_manager, @binding_registry)
        # CheckBox is primary name, Check is alias (see attribute_definitions.json)
        when 'CheckBox', 'Check', 'Checkbox'
          Views::CheckboxConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Radio'
          Views::RadioConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Segment'
          Views::SegmentConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Progress'
          Views::ProgressConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Slider'
          Views::SliderConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Indicator'
          Views::IndicatorConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Table'
          Views::TableConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Collection'
          Views::CollectionConverter.new(component, indent_level, action_manager, @binding_registry, @data_properties)
        when 'SelectBox'
          Views::SelectBoxConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Web', 'WebView'
          Views::WebConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'DynamicComponent'
          Views::DynamicComponentConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Include'
          # Include type should have been expanded by process_includes
          raise "Include type should have been expanded by process_includes. This is a bug."
        when 'TabView'
          Views::TabViewConverter.new(component, indent_level, action_manager, self, registry, @binding_registry)
        when 'Embed'
          Views::EmbedConverter.new(component, indent_level, action_manager, self, registry, @binding_registry)
        else
          # デフォルトコンバーター
          DefaultConverter.new(component, indent_level, action_manager, @binding_registry)
        end
      end
    end

    # 追加のコンバータークラス
    class SwitchConverter < Views::BaseViewConverter
      def convert
        id = @component['id'] || "toggle"

        # Create @State variable name
        state_var = "#{id}IsOn"

        # Add state variable to requirements
        @state_variables ||= []
        @state_variables << "@State private var #{state_var} = false"

        add_line "Toggle(\"\", isOn: $#{state_var})"
        add_modifier_line ".labelsHidden()"

        # onChange handler
        if @component['onValueChanged'] && @action_manager
          handler_name = @action_manager.register_action(@component['onValueChanged'], 'switch')
          add_modifier_line ".onChange(of: #{state_var}) { _, newValue in"
          indent do
            add_line "#{handler_name}()"
          end
          add_line "}"
        end

        apply_modifiers
        generated_code
      end
    end

    class CheckboxConverter < Views::BaseViewConverter
      def convert
        id = @component['id'] || "checkbox"

        # Create @State variable name
        state_var = "#{id}IsChecked"

        # Add state variable to requirements
        @state_variables ||= []
        @state_variables << "@State private var #{state_var} = false"

        add_line "Image(systemName: #{state_var} ? \"checkmark.square.fill\" : \"square\")"
        add_modifier_line ".onTapGesture {"
        indent do
          add_line "#{state_var}.toggle()"
          if @component['onClick']
            method_name = extract_binding_property(@component['onClick'])
            add_line "data.#{method_name}?()"
          end
        end
        add_line "}"

        apply_modifiers
        generated_code
      end
    end

    class DefaultConverter < Views::BaseViewConverter
      def convert
        add_line "Text(\"Unsupported component: #{@component['type']}\")"
        add_modifier_line ".foregroundColor(.red)"

        apply_modifiers
        generated_code
      end
    end
  end
end
