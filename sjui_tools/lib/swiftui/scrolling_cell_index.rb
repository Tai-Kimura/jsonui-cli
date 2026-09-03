# frozen_string_literal: true

require 'json'
require 'set'
require_relative '../core/screen_index'

module SjuiTools
  module SwiftUI
    # Which layouts render inside a VERTICALLY SCROLLING Collection — as its
    # cell, header or footer — across the whole project.
    #
    # A converter sees one tree. JsonToSwiftUIConverter marks the descendants
    # of a ScrollView in that tree so a wrapping flow Collection under it lets
    # the ancestor scroll (the 2026-09-03 ruling: "its own bounds" is
    # literal). A cell layout is another file: its root has no ScrollView
    # above it in its own tree, yet on the device it sits inside the host's
    # scrolling Collection — a consumer's "flow chips in the cell of a
    # vertical list" shape, which the in-tree mark could not reach. This
    # index is the project-wide half: built once by `sjui build` over the
    # layout tree (the layer that knows the project), it names the layouts
    # whose root should carry the mark before conversion.
    #
    # Rule (same as SwiftJsonUI's dynamic half, 292106c): the host Collection
    # scrolls vertically when `lazy` is in effect (anything but "none") and it
    # is not horizontal (`layout` / `orientation` "horizontal", or
    # `horizontalScroll: true`). A flow host counts — with `lazy` in effect it
    # scrolls vertically by the same ruling. A horizontal host's cells are
    # not under a vertical scroll; a `lazy: "none"` host does not scroll.
    #
    # Reference keys are ScreenIndex's (cell / header / footer, and the
    # legacy cellClasses list), resolved to screen ids the way ScreenIndex
    # resolves them, so "this layout is a cell of X" is one spelling across
    # the two indexes.
    module ScrollingCellIndex
      REFERENCE_KEYS = %w[cell header footer].freeze
      REFERENCE_LIST_KEYS = %w[cellClasses headerClasses footerClasses].freeze

      # Set of screen ids (layout basenames, variant-normalized) referenced
      # as cell / header / footer by a vertically scrolling Collection
      # anywhere under +layouts_dir+. Empty when the directory is absent.
      def self.build(layouts_dir)
        ids = Set.new
        return ids unless layouts_dir && File.directory?(layouts_dir.to_s)

        layout_files(layouts_dir).each do |path|
          data = begin
            JSON.parse(File.read(path))
          rescue StandardError
            nil
          end
          collect(data, ids)
        end
        ids
      end

      def self.layout_files(layouts_dir)
        root = layouts_dir.to_s
        Dir.glob(File.join(root, '**', '*.json')).sort.reject do |path|
          dirs = File.dirname(path).delete_prefix(root).split(File::SEPARATOR)
          (dirs & JsonUIShared::ScreenIndex::NON_LAYOUT_SUBTREES).any?
        end
      end

      def self.collect(node, ids)
        case node
        when Hash
          references_of(node).each { |ref| ids << JsonUIShared::ScreenIndex.screen_id_for_path(ref) } if vertically_scrolling_collection?(node)
          node.each_value { |value| collect(value, ids) }
        when Array
          node.each { |item| collect(item, ids) }
        end
      end

      def self.vertically_scrolling_collection?(node)
        return false unless node['type'].to_s.casecmp('collection').zero?
        return false if node['lazy'] == 'none'

        !horizontal?(node)
      end

      # The three declared spellings of the same direction fact, as the
      # Collection converter and the dynamic renderer read them.
      def self.horizontal?(node)
        return true if node['horizontalScroll'] == true

        %w[layout orientation].any? { |key| node[key].to_s.casecmp('horizontal').zero? }
      end

      # Every layout this Collection instantiates: section-level cell /
      # header / footer, the same keys on the node itself, and the legacy
      # class lists (a string, or `{ "className": ... }`).
      def self.references_of(node)
        refs = []
        holders = [node] + Array(node['sections']).select { |s| s.is_a?(Hash) }
        holders.each do |holder|
          REFERENCE_KEYS.each do |key|
            value = holder[key]
            refs << value if value.is_a?(String) && !value.empty?
          end
        end
        REFERENCE_LIST_KEYS.each do |key|
          Array(node[key]).each do |item|
            name = item.is_a?(Hash) ? item['className'] : item
            refs << name if name.is_a?(String) && !name.empty?
          end
        end
        refs
      end
    end
  end
end
