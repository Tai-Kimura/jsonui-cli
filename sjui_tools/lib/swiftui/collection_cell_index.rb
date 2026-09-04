# frozen_string_literal: true

require 'set'
require_relative 'scrolling_cell_index'

module SjuiTools
  module SwiftUI
    # Which layouts render as a Collection's cell, header or footer anywhere
    # in the project — regardless of scroll direction.
    #
    # WHY THIS IS NOT ScrollingCellIndex. That index answers a question about
    # scrolling, so it excludes horizontal and `lazy: "none"` hosts on
    # purpose. The accessibility question has no such exclusion: every cell
    # of every Collection is wrapped by the host with
    # `.accessibilityIdentifier("{collectionId}_item_{index}")`, and a plain
    # SwiftUI container is not an accessibility element, so that identifier
    # is pushed down onto the cell's own children (the library says so
    # itself, in DynamicModifierHelper: "Plain SwiftUI containers are not
    # accessibility elements, so a bare .accessibilityIdentifier is pushed
    # down onto the nearest descendant").
    #
    # A cell whose root declares an `id` was already safe: the id-bearing
    # container path makes the root an explicit accessibility container, and
    # the wrapper's identifier lands on the wrapper instead of the children.
    # A cell whose root declares no id got no such container, so its direct
    # children were renamed to `{collectionId}_item_{N}` and became
    # unreachable by their own identifiers (measured across 8 cells in one
    # consumer, 8/8 explained by this discriminator).
    #
    # So the mark is "this layout is somebody's cell root", and the converter
    # makes such a root a container whether or not it has an id.
    module CollectionCellIndex
      # Set of screen ids (layout basenames, variant-normalized) referenced as
      # cell / header / footer by ANY Collection under +layouts_dir+. Empty
      # when the directory is absent — a single-file conversion has no
      # project to scan and converts as before.
      def self.build(layouts_dir)
        ids = Set.new
        return ids unless layouts_dir && File.directory?(layouts_dir.to_s)

        ScrollingCellIndex.layout_files(layouts_dir).each do |path|
          data = begin
            JSON.parse(File.read(path))
          rescue StandardError
            nil
          end
          collect(data, ids)
        end
        ids
      end

      def self.collect(node, ids)
        case node
        when Hash
          if collection?(node)
            ScrollingCellIndex.references_of(node).each do |ref|
              ids << JsonUIShared::ScreenIndex.screen_id_for_path(ref)
            end
          end
          node.each_value { |value| collect(value, ids) }
        when Array
          node.each { |item| collect(item, ids) }
        end
      end

      # Any Collection. The reference keys and their resolution are
      # ScrollingCellIndex's, so "this layout is a cell of X" keeps one
      # spelling across the two indexes.
      def self.collection?(node)
        node['type'].to_s.casecmp('collection').zero?
      end
    end
  end
end
