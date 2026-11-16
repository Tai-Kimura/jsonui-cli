# frozen_string_literal: true

module RjuiTools
  module React
    module Helpers
      # Maps SF Symbol / Material icon names to Lucide React icon component names.
      # Centralized so converters can emit JSX and react_generator.rb can collect
      # which icon components are actually referenced, in order to emit the
      # matching `import { X } from 'lucide-react'` at the top of the file.
      module LucideIconHelper
        ICON_MAP = {
          'house' => 'Home',
          'house.fill' => 'Home',
          'Home' => 'Home',
          'person' => 'User',
          'person.fill' => 'User',
          'Person' => 'User',
          'gearshape' => 'Settings',
          'gearshape.fill' => 'Settings',
          'gear' => 'Settings',
          'Settings' => 'Settings',
          'magnifyingglass' => 'Search',
          'Search' => 'Search',
          'heart' => 'Heart',
          'heart.fill' => 'Heart',
          'Favorite' => 'Heart',
          'star' => 'Star',
          'star.fill' => 'Star',
          'Star' => 'Star',
          'bell' => 'Bell',
          'bell.fill' => 'Bell',
          'Notifications' => 'Bell',
          'cart' => 'ShoppingCart',
          'cart.fill' => 'ShoppingCart',
          'ShoppingCart' => 'ShoppingCart',
          'list.bullet' => 'List',
          'List' => 'List',
          'square.grid.2x2' => 'LayoutGrid',
          'GridView' => 'LayoutGrid',
          'circle' => 'Circle',
          'Circle' => 'Circle'
        }.freeze

        # Resolve an icon identifier to its Lucide React component name.
        # Unknown identifiers are passed through a best-effort PascalCase
        # conversion so authors can reference any Lucide icon by name
        # (e.g. 'arrow-right' → 'ArrowRight').
        def self.map_to_lucide(icon)
          return nil if icon.nil? || icon.to_s.empty?
          ICON_MAP[icon] || icon.to_s.split('.').first.split(/[-_]|(?=[A-Z])/).reject(&:empty?).map(&:capitalize).join
        end
      end
    end
  end
end
