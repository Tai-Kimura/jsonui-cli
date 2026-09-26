# frozen_string_literal: true

require_relative '../core/type_synonyms'
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

require_relative '../core/bind_fold'
require_relative '../core/logger'
require_relative '../core/attribute_validator'
module SjuiTools
  module SwiftUI
    class ConverterFactory
      attr_accessor :data_properties

      # Responsive function code strings collected during conversion.
      # Each entry is a String containing a complete @ViewBuilder function.
      attr_reader :responsive_functions

      # Counter for generating unique responsive function names
      attr_reader :responsive_counter

      # The validator whose sentence DefaultConverter says: the build's own
      # when it validates, else one made the first time a type is drawn as
      # nothing — one per build either way. A validator per node read the
      # definitions again for each, and a copy that left its links dangling
      # said "attribute_definitions.json not found" once per such node.
      attr_writer :unknown_type_validator

      def unknown_type_validator
        @unknown_type_validator ||= SjuiTools::Core::AttributeValidator.new(:swiftui)
      end

      def initialize(binding_registry = nil)
        @view_registry = ViewRegistry.new
        @binding_registry = binding_registry
        @custom_converters = load_custom_converters
        # a spelling the app registers is the app's, for what classifies a
        # node by its drawn type too (TypeSynonyms.app_types)
        JsonUIShared::TypeSynonyms.app_types = @custom_converters.keys
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

      # The spellings this project registers converters of its own for: the
      # keys of views/extensions/converter_mappings.rb.
      def self.custom_types
        allocate.send(:load_custom_converters).keys
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

        # A type-synonym spelling (HStack, ProgressBar, WebView, …) is drawn
        # as its type, from shared/core/type_synonyms.json — after the app's
        # converters were asked, above, with the spelling as written. The
        # cases below are canonical declared sections; a spelling that is
        # neither draws the default. The node's converter gets the node as drawn, so what reads
        # its type afterwards (the binding handlers) reads the drawn one.
        component = JsonUIShared::TypeSynonyms.canonicalize(component)
        # A declared alias section (EditText / Input -> TextField, Check ->
        # CheckBox, Toggle -> Switch: `_alias_of` in attribute_definitions.json)
        # is drawn as its canonical section.
        component = JsonUIShared::ComponentAliases.resolve(component)
        component_type = component['type']
        # `bind` folded into the attribute it stands for (JsonUIShared::BindFold)
        # on the node a built-in converter draws — its style merged
        # (StyleLoader, before conversion), drawn as its type — after the
        # app's own converters were asked; an app's converter gets its node as
        # written. The layout normalizer leaves a node with a style or
        # responsive overrides to this fold.
        component = JsonUIShared::BindFold.fold(component, component_type)

        case component_type
        when 'Label'
          Views::LabelConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'IconLabel'
          Views::IconLabelConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Button'
          Views::ButtonConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'View', 'SafeAreaView'
          Views::ViewConverter.new(component, indent_level, action_manager, self, registry, @binding_registry)
        when 'GradientView'
          Views::GradientViewConverter.new(component, indent_level, action_manager, self, registry, @binding_registry)
        when 'Blur'
          Views::BlurConverter.new(component, indent_level, action_manager, self, registry, @binding_registry)
        when 'TextField'
          Views::TextFieldConverter.new(component, indent_level, action_manager, @binding_registry)
        # CircleImage / CircleImageView: Image synonyms drawn as CircleImage
        # (`render_as`), which ImageConverter clips to a circle
        when 'Image', 'CircleImage'
          Views::ImageConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'NetworkImage'
          Views::NetworkImageConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'ScrollView'
          Views::ScrollViewConverter.new(component, indent_level, action_manager, self, registry, @binding_registry)
        when 'TextView'
          Views::TextViewConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Switch'
          Views::ToggleConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'CheckBox'
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
        when 'Collection'
          Views::CollectionConverter.new(component, indent_level, action_manager, @binding_registry, @data_properties)
        when 'SelectBox'
          Views::SelectBoxConverter.new(component, indent_level, action_manager, @binding_registry)
        when 'Web'
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
          # No case draws it. A type the validator knows (an extension
          # definition with no converter, say) is named in its own sentence
          # and drawn as a View, its children in it; an unknown type is named
          # and drawn as nothing (DefaultConverter). 4f's ruling, jsonui-cli 1.9.0.
          type = component['type'].to_s
          if unknown_type_validator.known_component_type?(type)
            SjuiTools::Core::Logger.warn(SjuiTools::Core::AttributeValidator.declared_without_drawer_message(type, 'SwiftUI'))
            Views::ViewConverter.new(component, indent_level, action_manager, self, registry, @binding_registry)
          else
            sentence = unknown_type_validator.unknown_component_type_message(type)
            DefaultConverter.new(component, indent_level, action_manager, @binding_registry, sentence: sentence)
          end
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

    # A type the validator does not know: named in the build in the
    # validator's sentence (JsonUIShared::AttributeValidatorCore
    # .unknown_component_type_message), and drawn as nothing — the sentence
    # in a comment where the node would be, and an EmptyView, so what the
    # parent puts after a child's code has a view to take. Not its children.
    # It was a red Text holding the sentence (the words of a build on a
    # release screen), and before that "Unsupported component: <type>";
    # kjui and rjui draw nothing there too (4f's ruling, jsonui-cli 1.9.0).
    # The factory hands it the sentence (ConverterFactory#unknown_type_validator).
    class DefaultConverter < Views::BaseViewConverter
      def initialize(component, indent_level = 0, action_manager = nil, binding_registry = nil, sentence: nil)
        super(component, indent_level, action_manager, binding_registry)
        @sentence = sentence
      end

      def convert
        sentence = @sentence || SjuiTools::Core::AttributeValidator.new(:swiftui).unknown_component_type_message(@component['type'].to_s)
        SjuiTools::Core::Logger.warn(sentence)
        add_line "// #{sentence}"
        add_line 'EmptyView()'
        generated_code
      end
    end
  end
end
