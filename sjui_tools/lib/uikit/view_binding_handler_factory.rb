# frozen_string_literal: true

require_relative 'handlers/button_binding_handler'
require_relative 'handlers/check_binding_handler'
require_relative 'handlers/collection_view_binding_handler'
require_relative 'handlers/icon_label_binding_handler'
require_relative 'handlers/image_binding_handler'
require_relative 'handlers/label_binding_handler'
require_relative 'handlers/network_image_binding_handler'
require_relative 'handlers/radio_binding_handler'
require_relative 'handlers/scroll_binding_handler'
require_relative 'handlers/select_box_binding_handler'
require_relative 'handlers/switch_binding_handler'
require_relative 'handlers/text_field_binding_handler'
require_relative 'handlers/text_view_binding_handler'

module SjuiTools
  module UIKit
    class ViewBindingHandlerFactory
      # Cache for dynamically loaded extension handlers
      @extension_handlers = {}
      @extensions_loaded = false

      def self.create_handler(view_type, binding_content, reset_text_views, reset_constraint_views, data_sets = [])
        case view_type
        when "Button"
          ButtonBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        # CheckBox is primary name, Check is alias (see attribute_definitions.json)
        when "CheckBox", "Check"
          CheckBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        when "CollectionView"
          CollectionViewBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        when "NetworkImage", "CircleImage"
          NetworkImageBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        when "IconLabel"
          IconLabelBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        when "Image"
          ImageBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        when "Label"
          LabelBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        when "Radio"
          RadioBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        when "Scroll", "ScrollView"
          ScrollBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        when "SelectBox"
          SelectBoxBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        # Switch/Toggle: Both types supported for backward compatibility
        # "Switch" is primary name, "Toggle" is alias (see attribute_definitions.json)
        when "Switch", "Toggle"
          SwitchBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        when "TextField"
          TextFieldBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        when "TextView"
          TextViewBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
        else
          # Try to find extension handler
          handler_class = find_extension_handler(view_type)
          if handler_class
            handler_class.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
          else
            # デフォルトは共通処理のみのハンドラー
            ViewBindingHandler.new(binding_content, reset_text_views, reset_constraint_views, data_sets)
          end
        end
      end

      # Load extension handlers dynamically from handlers/extensions directory
      def self.load_extension_handlers
        return if @extensions_loaded

        extension_paths = [
          # Main SwiftJsonUI structure
          File.join(Dir.pwd, 'tools', 'sjui_tools', 'lib', 'uikit', 'handlers', 'extensions'),
          # Test app structure
          File.join(Dir.pwd, 'sjui_tools', 'lib', 'uikit', 'handlers', 'extensions')
        ]

        extension_paths.each do |ext_dir|
          next unless File.directory?(ext_dir)

          Dir.glob(File.join(ext_dir, '*_binding_handler.rb')).each do |file|
            require file

            # Extract component name from filename (e.g., triangle_binding_handler.rb -> Triangle)
            basename = File.basename(file, '.rb')
            component_name = basename.sub(/_binding_handler$/, '')
                                     .split('_')
                                     .map(&:capitalize)
                                     .join

            # Find the handler class
            handler_class_name = "#{component_name}BindingHandler"
            if SjuiTools::UIKit.const_defined?(handler_class_name)
              @extension_handlers[component_name] = SjuiTools::UIKit.const_get(handler_class_name)
            end
          end
        end

        @extensions_loaded = true
      end

      # Find extension handler for a given view type
      def self.find_extension_handler(view_type)
        load_extension_handlers
        @extension_handlers[view_type]
      end
    end
  end
end
