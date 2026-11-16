# frozen_string_literal: true

require 'json'
require 'set'
require_relative 'scrolling_cell_index'
require_relative 'collection_cell_index'

module SjuiTools
  module SwiftUI
    # The cell views a Collection's generated code names, and the ones no
    # Swift source defines.
    #
    # The generated code of a screen draws each cell / header / footer
    # reference as `<Name>View(data:)` (CollectionConverter.cell_view_name).
    # The build writes the cell layout's Data and GeneratedView, but the
    # `<Name>View` that wraps them and its ViewModel came only from
    # `sjui g collection`. A cell layout written by hand therefore built with
    # warning 0 and an app that did not compile (ticket
    # sjui-build-does-not-scaffold-cell-views-for-hand-written-cell-layouts).
    # kjui's build scaffolds a hand-added layout's missing files
    # (compose_builder.rb, ensure_kotlin_files_exist); this is that, for the
    # cells only:
    #
    # - a cell view no Swift source under the source path defines, whose
    #   layout the build converts (one layout, its GeneratedView written, the
    #   same name) is scaffolded — its View and ViewModel, from the templates
    #   `sjui g collection` writes, each only when no source defines it;
    # - one it cannot scaffold (no such layout, more than one, a partial,
    #   a refused layout, a name the layout does not give) is a warning:
    #   the generated code names a type nothing defines.
    #
    # Only the cells: a screen's View is named by the app's own navigation,
    # not by generated code, so a missing one does not break the build. Every
    # layout kjui's way would add a View and a ViewModel to each include
    # partial and app-owned screen (measured 2026-10-02 across 7 faces:
    # 22 layouts with no View; 0 referenced cell views missing).
    module CellViewScaffold
      Scaffold = Struct.new(:type, :view_name, :layout, :view_path, :view_model_path, keyword_init: true)
      Missing = Struct.new(:type, :refs, :reason, keyword_init: true)

      SKIPPED_DIRS = %w[.build build DerivedData Pods SourcePackages .git node_modules].freeze
      TYPE_DECL = /\b(?:struct|class|enum|actor|typealias)\s+([A-Za-z_][A-Za-z0-9_]*)/.freeze

      # +json_files+ are the layouts the build converts (no partial, no
      # variant, no UIKit file); +generated_view_path+ answers where the
      # build wrote a layout's GeneratedView.
      def self.plan(layouts_dir:, source_path:, json_files:, view_model_dir:, generated_view_path:)
        refs = references(layouts_dir)
        return [[], []] if refs.empty?

        defined = defined_types(source_path)
        by_type = json_files.group_by { |f| "#{view_name_for(f)}View" }
        scaffolds = []
        missing = []
        refs.each do |type, from|
          next if defined.include?(type)

          layouts = by_type[type] || []
          if layouts.size != 1
            reason = layouts.empty? ? 'no layout the build converts gives this name' : "#{layouts.size} layouts give this name"
            missing << Missing.new(type: type, refs: from, reason: reason)
            next
          end
          layout = layouts.first
          view_name = view_name_for(layout)
          generated = generated_view_path.call(layout, view_name)
          unless File.exist?(generated)
            missing << Missing.new(type: type, refs: from, reason: 'its layout produced no GeneratedView in this build')
            next
          end
          vm_type = "#{view_name}ViewModel"
          scaffolds << Scaffold.new(
            type: type, view_name: view_name, layout: layout,
            view_path: File.join(File.dirname(generated), "#{type}.swift"),
            view_model_path: defined.include?(vm_type) ? nil : File.join(view_model_dir, "#{vm_type}.swift")
          )
        end
        [scaffolds, missing]
      end

      # type => sorted reference strings, over every layout file (a partial
      # can hold a Collection too).
      def self.references(layouts_dir)
        refs = Hash.new { |h, k| h[k] = Set.new }
        return {} unless layouts_dir && File.directory?(layouts_dir.to_s)

        ScrollingCellIndex.layout_files(layouts_dir).each do |path|
          data = begin
            JSON.parse(File.read(path))
          rescue StandardError
            nil
          end
          collect(data, refs)
        end
        refs.transform_values { |s| s.to_a.sort }
      end

      def self.collect(node, refs)
        case node
        when Hash
          if CollectionCellIndex.collection?(node)
            ScrollingCellIndex.references_of(node).each do |ref|
              type = Views::CollectionConverter.cell_view_name(ref)
              refs[type] << ref if type
            end
          end
          node.each_value { |value| collect(value, refs) }
        when Array
          node.each { |item| collect(item, refs) }
        end
      end

      def self.defined_types(source_path)
        types = Set.new
        swift_files(source_path.to_s).each do |file|
          File.read(file, encoding: 'UTF-8', invalid: :replace, undef: :replace)
              .scan(TYPE_DECL) { |(name)| types << name }
        rescue StandardError
          next
        end
        types
      end

      def self.swift_files(root)
        return [] unless File.directory?(root)

        found = []
        stack = [root]
        until stack.empty?
          dir = stack.pop
          Dir.each_child(dir) do |name|
            path = File.join(dir, name)
            if File.directory?(path)
              stack << path unless SKIPPED_DIRS.include?(name) || name.end_with?('.xcodeproj', '.xcassets')
            elsif name.end_with?('.swift')
              found << path
            end
          end
        end
        found.sort
      end

      # The name the build gives a layout's Data / GeneratedView (build.rb).
      def self.view_name_for(json_file)
        File.basename(json_file, '.json').split(/[_\-]/).map(&:capitalize).join
      end
    end
  end
end
