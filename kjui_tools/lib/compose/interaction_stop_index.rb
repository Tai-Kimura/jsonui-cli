# frozen_string_literal: true

require 'json'
require 'set'
require_relative 'include_expander'
require_relative '../core/tap_accessibility'
require_relative '../core/screen_index'

module KjuiTools
  module Compose
    # Which layouts a `userInteractionEnabled` stop can reach from outside
    # their own file: those drawn in a composable of their own — a
    # Collection's cells, headers and footers, an Embed's screen, a TabView
    # tab's view — inside a node whose flag is false or bound, anywhere under
    # the layouts directory, and whatever those draw in turn (the tap rule's
    # stoppable_layouts). annotate! cannot reach into them; the stopping node
    # provides the stop (LocalInteractionStopped) and the clicks of these
    # layouts read it. Every other layout is emitted as it was. Empty when the
    # directory is absent.
    module InteractionStopIndex
      def self.build(layouts_dir)
        root = layouts_dir.to_s
        return Set.new unless layouts_dir && File.directory?(root)

        trees = {}
        Dir.glob(File.join(root, '**', '*.json')).sort.each do |path|
          dirs = File.dirname(path).delete_prefix(root).split(File::SEPARATOR)
          next if (dirs & JsonUIShared::ScreenIndex::NON_LAYOUT_SUBTREES).any?

          tree = begin
            JSON.parse(File.read(path))
          rescue StandardError
            next
          end
          tree = begin
            IncludeExpander.process_includes(tree, File.dirname(path), nil, root)
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
