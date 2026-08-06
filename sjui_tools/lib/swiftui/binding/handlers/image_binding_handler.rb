# frozen_string_literal: true

require_relative '../view_binding_handler'

module SjuiTools
  module SwiftUI
    module Binding
      class ImageBindingHandler < ViewBindingHandler
        def handle_specific_binding(component, key, value)
          case key
          when 'srcName', 'src'
            # Image source is handled in Image initialization
            nil
          when 'contentMode'
            # Owned by ImageConverter, which emits the library seam
            # (`.imageContentMode(ImageContentModeIntent.from(...))`) — the
            # run-time twin of its own literal table. The ternary that lived
            # here (`== "fill" ? .fill : .fit`) collapsed fifteen declared
            # values to two and read canonical fill (stretch, spelled as the
            # ABSENCE of aspectRatio) as SwiftUI's aspect-fill crop.
            nil
          else
            nil
          end
        end

        # Get the image source (with binding support)
        def get_image_source(component)
          src_value = component['srcName'] || component['src']
          if is_binding?(src_value)
            # For binding, we need to handle it differently
            # SwiftUI Image doesn't directly support binding for the image name
            parse_binding(src_value, read_only: true)
          else
            "\"#{src_value || 'placeholder'}\""
          end
        end

        # Check if this is a system image
        def is_system_image?(component)
          component['systemImage'] == true || component['isSystemImage'] == true
        end
      end
    end
  end
end