# frozen_string_literal: true

require 'json'
require 'set'
require_relative 'scrolling_cell_index'
require_relative 'include_expander'
require_relative '../core/tap_accessibility'
require_relative '../core/screen_index'

module SjuiTools
  module SwiftUI
    # Which layouts a `userInteractionEnabled` stop can reach from outside
    # their own file: those drawn in a view of their own — a Collection's
    # cells, headers and footers, an Embed's screen, a TabView tab's view —
    # inside a node whose flag is false or bound, anywhere under the layouts
    # directory, and whatever those draw in turn (the tap rule's
    # stoppable_layouts). annotate! cannot reach into them; the stopping node
    # hands the stop down through the environment (jsonuiInteractionStopped),
    # and the views of these layouts read it. Every other layout is emitted as
    # it was. Empty when the directory is absent — a single-file conversion
    # has no project to scan and converts as before.
    module InteractionStopIndex
      def self.build(layouts_dir)
        return Set.new unless layouts_dir && File.directory?(layouts_dir.to_s)

        trees = {}
        ScrollingCellIndex.layout_files(layouts_dir).each do |path|
          tree = begin
            JSON.parse(File.read(path))
          rescue StandardError
            next
          end
          tree = begin
            IncludeExpander.process_includes(tree, File.dirname(path), nil, layouts_dir.to_s)
          rescue StandardError
            tree
          end
          trees[JsonUIShared::ScreenIndex.screen_id_for_path(path)] = tree
        end
        JsonUIShared::TapAccessibility.stoppable_layouts(trees) do |ref|
          JsonUIShared::ScreenIndex.screen_id_for_path(ref)
        end
      end
    end
  end
end
