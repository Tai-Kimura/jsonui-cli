# frozen_string_literal: true

require_relative '../core/responsive_resolver'
require_relative 'tailwind_mapper'

module RjuiTools
  module React
    # Generates Tailwind CSS responsive classes from JsonUI responsive blocks.
    #
    # Size class -> Tailwind breakpoint mapping:
    #   compact            -> (default, no prefix)
    #   medium             -> md:  (768px+)
    #   regular            -> lg:  (1024px+)
    #   landscape          -> requires useMediaQuery hook
    #   compact-landscape  -> requires useMediaQuery hook
    #   medium-landscape   -> requires useMediaQuery hook (+ md: for width)
    #   regular-landscape  -> requires useMediaQuery hook (+ lg: for width)
    #
    module ResponsiveHelper
      # Tailwind breakpoint prefix for each width size class
      BREAKPOINT_PREFIX = {
        'compact' => '',
        'medium' => 'md:',
        'regular' => 'lg:'
      }.freeze

      # Attributes that map to specific Tailwind utilities
      # Each entry: attribute_name => lambda(value, prefix) -> class string
      ATTRIBUTE_MAPPERS = {
        'orientation' => ->(v, prefix) {
          case v&.downcase
          when 'horizontal' then "#{prefix}flex-row"
          when 'vertical' then "#{prefix}flex-col"
          end
        },
        'spacing' => ->(v, prefix) {
          tw = TailwindMapper::PADDING_MAP[v] || v
          "#{prefix}gap-#{tw}"
        },
        'fontSize' => ->(v, prefix) {
          mapped = TailwindMapper::FONT_SIZE_MAP[v]
          if mapped
            # text-sm -> md:text-sm
            "#{prefix}#{mapped}"
          else
            "#{prefix}text-[#{v}px]"
          end
        },
        'padding' => ->(v, prefix) {
          map_responsive_padding(v, prefix)
        },
        'width' => ->(v, prefix) {
          raw = TailwindMapper.map_width(v)
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        'height' => ->(v, prefix) {
          raw = TailwindMapper.map_height(v)
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        'visibility' => ->(v, prefix) {
          case v
          when 'visible'
            "#{prefix}block"
          when 'gone'
            "#{prefix}hidden"
          end
        },
        'background' => ->(v, prefix) {
          raw = TailwindMapper.map_color(v, 'bg')
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        'fontColor' => ->(v, prefix) {
          raw = TailwindMapper.map_color(v, 'text')
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        'cornerRadius' => ->(v, prefix) {
          raw = TailwindMapper.map_corner_radius(v)
          raw.empty? ? nil : "#{prefix}#{raw}"
        },
        'textAlign' => ->(v, prefix) {
          raw = TailwindMapper.map_text_align(v)
          raw.empty? ? nil : "#{prefix}#{raw}"
        }
      }.freeze

      class << self
        # Build responsive Tailwind classes for a component.
        #
        # Returns a Hash:
        #   {
        #     classes: "flex-col lg:flex-row gap-2 lg:gap-6",
        #     needs_landscape_hook: true,
        #     landscape_classes: { "isLandscape" => "flex-row gap-8" },
        #     stripped_keys: Set["orientation", "spacing"]
        #   }
        #
        # `stripped_keys` lists attribute keys that were handled by responsive
        # and should NOT be emitted by the normal build_class_name logic for
        # the default (compact) value.
        def build_responsive(component)
          result = {
            classes: [],
            needs_landscape_hook: false,
            landscape_styles: {},
            stripped_keys: Set.new
          }

          return result unless JsonUIShared::ResponsiveResolver.responsive?(component)

          overridden = JsonUIShared::ResponsiveResolver.overridden_keys(component)
          return result if overridden.empty?

          size_classes = JsonUIShared::ResponsiveResolver.size_classes(component)
          has_landscape = size_classes.any? { |sc| sc.include?('landscape') }

          # For each size class, generate prefixed Tailwind classes
          size_classes.each do |sc|
            parsed = JsonUIShared::ResponsiveResolver.parse_size_class(sc)
            overrides = component.dig('responsive', sc)
            next unless overrides.is_a?(Hash)

            if parsed[:landscape]
              # Landscape requires useMediaQuery hook
              result[:needs_landscape_hook] = true
              landscape_key = build_landscape_key(parsed)
              result[:landscape_styles][landscape_key] ||= []

              overrides.each do |attr, value|
                next if %w[type child data responsive].include?(attr)

                mapper = ATTRIBUTE_MAPPERS[attr]
                if mapper
                  # For landscape compound size classes, use width prefix inside the hook conditional
                  cls = mapper.call(value, '')
                  result[:landscape_styles][landscape_key] << cls if cls
                end
              end
            else
              # Pure width breakpoint -> Tailwind responsive prefix
              prefix = BREAKPOINT_PREFIX[parsed[:width]] || ''

              overrides.each do |attr, value|
                next if %w[type child data responsive].include?(attr)

                mapper = ATTRIBUTE_MAPPERS[attr]
                if mapper
                  cls = mapper.call(value, prefix)
                  result[:classes] << cls if cls
                end
              end
            end
          end

          # Mark overridden keys so base converter can handle defaults
          result[:stripped_keys] = overridden

          # Add default (compact) classes for overridden attributes without prefix
          overridden.each do |attr|
            next if %w[type child data responsive].include?(attr)
            next unless component.key?(attr)

            mapper = ATTRIBUTE_MAPPERS[attr]
            next unless mapper

            default_value = component[attr]

            # For visibility: if default is "gone" and responsive overrides to "visible",
            # emit "hidden lg:block" pattern
            if attr == 'visibility' && default_value == 'gone'
              result[:classes].unshift('hidden')
              next
            end

            cls = mapper.call(default_value, '')
            result[:classes].unshift(cls) if cls
          end

          result
        end

        # Generate the useMediaQuery hook call string for landscape detection.
        # Returns the TypeScript/JSX code string.
        def landscape_hook_declaration
          "const isLandscape = useMediaQuery('(orientation: landscape)');"
        end

        # Build a conditional className expression for landscape overrides.
        #
        # Example output:
        #   `${isLandscape ? "flex-row gap-8" : ""}`
        def build_landscape_class_expression(landscape_styles)
          return '' if landscape_styles.empty?

          parts = landscape_styles.map do |key, classes|
            classes_str = classes.compact.join(' ')
            next if classes_str.empty?

            condition = landscape_condition(key)
            "${#{condition} ? \"#{classes_str}\" : \"\"}"
          end.compact

          parts.join(' ')
        end

        # Check if a component (or any descendant) needs the landscape hook.
        # Walks the entire subtree even when the current node has no
        # `responsive` block of its own, because a parent view without
        # responsive overrides may still contain a child that does.
        def needs_landscape_hook?(component)
          return false unless component.is_a?(Hash)

          if JsonUIShared::ResponsiveResolver.responsive?(component)
            size_classes = JsonUIShared::ResponsiveResolver.size_classes(component)
            return true if size_classes.any? { |sc| sc.include?('landscape') }
          end

          children = component['child']
          if children.is_a?(Array)
            children.each do |child|
              return true if child.is_a?(Hash) && needs_landscape_hook?(child)
            end
          elsif children.is_a?(Hash)
            return true if needs_landscape_hook?(children)
          end

          false
        end

        private

        def build_landscape_key(parsed)
          if parsed[:width]
            "#{parsed[:width]}-landscape"
          else
            'landscape'
          end
        end

        def landscape_condition(key)
          case key
          when 'landscape'
            'isLandscape'
          when 'compact-landscape'
            'isLandscape'
          when 'medium-landscape'
            'isLandscape'
          when 'regular-landscape'
            'isLandscape'
          else
            'isLandscape'
          end
        end

        def map_responsive_padding(value, prefix)
          case value
          when Numeric
            tw = TailwindMapper::PADDING_MAP[value] || value
            "#{prefix}p-#{tw}"
          when Array
            map_responsive_padding_array(value, prefix)
          else
            nil
          end
        end

        def map_responsive_padding_array(arr, prefix)
          case arr.length
          when 1
            tw = TailwindMapper::PADDING_MAP[arr[0]] || arr[0]
            "#{prefix}p-#{tw}"
          when 2
            twy = TailwindMapper::PADDING_MAP[arr[0]] || arr[0]
            twx = TailwindMapper::PADDING_MAP[arr[1]] || arr[1]
            "#{prefix}py-#{twy} #{prefix}px-#{twx}"
          when 4
            [
              "#{prefix}pt-#{TailwindMapper::PADDING_MAP[arr[0]] || arr[0]}",
              "#{prefix}pr-#{TailwindMapper::PADDING_MAP[arr[1]] || arr[1]}",
              "#{prefix}pb-#{TailwindMapper::PADDING_MAP[arr[2]] || arr[2]}",
              "#{prefix}pl-#{TailwindMapper::PADDING_MAP[arr[3]] || arr[3]}"
            ].join(' ')
          else
            nil
          end
        end
      end
    end
  end
end
