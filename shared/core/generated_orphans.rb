# frozen_string_literal: true

require 'set'

# What a deleted layout leaves behind, and which of it the build may delete.
#
# Canonical copy: shared/core/generated_orphans.rb. sjui_tools, kjui_tools and
# rjui_tools each carry a byte-identical copy in lib/core/ (checked by their
# shared_core_mirror_spec), so the three faces apply one rule.
#
# A file is DELETED only when all three hold:
#   1. it sits in a directory the face's config declares for that output, and
#      has the name the generator gives that output (the face passes both);
#   2. the @generated sentinel is in its first lines — the generator's claim
#      that the whole file is its output;
#   3. no layout under the layouts directory has the name it was generated for.
#
# A file that meets 1 and 3 but not 2 is not the generator's to delete, and is
# named in a warning instead:
#   - an output the generator owns only in part (a Compose GeneratedView: the
#     generator rewrites the GENERATED_CODE block and nothing outside it);
#   - an output with no @generated line (a Data file from an older generator);
#   - a file the user writes (a View, a ViewModel). These are named only when
#     a generated output of the same name was found orphaned in the same run:
#     a hand-written view that never had a layout (a toast, a licenses screen)
#     is the user's own business and is not reported on every build.
#
# Names compare by their letters only, underscores and hyphens dropped and
# case ignored: the generators spell one layout's outputs with more than one
# PascalCase function (`capitalize` per segment in some places, a camelCase
# splitter in others), and match an existing Data file case-insensitively.
module JsonUIShared
  module GeneratedOrphans
    SENTINEL = '@generated'
    HEAD_LINES = 12

    # dir:     absolute directory the config declares for this output
    # pattern: Regexp over the file's basename; captures the layout name as `name`
    # owner:   :generator — the generator writes the whole file (rule above)
    #          :block     — the generator owns only a marked block of it
    #          :user      — the user writes it
    Kind = Struct.new(:dir, :pattern, :owner, keyword_init: true)

    Result = Struct.new(:removed, :kept, :skipped, keyword_init: true)

    WARNINGS = {
      block: 'its layout is gone; the generator owns only the GENERATED_CODE block, ' \
             'so it was not deleted — delete it if nothing outside that block was edited by hand',
      unmarked: 'its layout is gone, but it has no @generated line, so it was not deleted — ' \
                'delete it by hand if a generator wrote it',
      user: 'its layout is gone (its generated outputs were orphaned); this file is yours, ' \
            'so it was not deleted'
    }.freeze

    module_function

    def name_key(name)
      name.to_s.delete('_-').downcase
    end

    # Every name a layout under layouts_dir gives its outputs: each file's base
    # name, and for a responsive variant (home@regular.json) also the
    # `<base><Class>Variant` its variant view is named after.
    def layout_names(layouts_dir)
      names = Set.new
      return names unless layouts_dir && Dir.exist?(layouts_dir)

      Dir.glob(File.join(layouts_dir, '**', '*.json')).each do |path|
        rel = path.sub(%r{\A#{Regexp.escape(layouts_dir)}/}, '')
        next if rel.start_with?('Resources/', 'Styles/')

        stem, size_class = File.basename(path, '.json').split('@', 2)
        names << name_key(stem)
        names << name_key("#{stem}#{size_class}Variant") if size_class
      end
      names
    end

    def generated?(path)
      File.foreach(path).first(HEAD_LINES).any? { |line| line.include?(SENTINEL) }
    rescue ArgumentError, Errno::ENOENT, Errno::EISDIR
      false
    end

    def sweep(layouts_dir:, kinds:)
      names = layout_names(layouts_dir)
      # An empty set cannot tell "every layout was deleted" from "this is not
      # the layouts directory", and deleting on it would empty every output
      # directory at once.
      if names.empty?
        return Result.new(removed: [], kept: [],
                          skipped: "no layouts under #{layouts_dir}; nothing was pruned")
      end

      removed = []
      kept = []
      orphaned = Set.new
      user_candidates = []

      kinds.each do |kind|
        next unless kind.dir && Dir.exist?(kind.dir)

        Dir.glob(File.join(kind.dir, '**', '*')).sort.each do |path|
          next unless File.file?(path)

          match = kind.pattern.match(File.basename(path))
          next unless match

          key = name_key(match[:name])
          next if names.include?(key)

          case kind.owner
          when :generator
            orphaned << key
            if generated?(path)
              File.delete(path)
              removed << path
              remove_dir_if_empty(File.dirname(path), kind.dir)
            else
              kept << [path, WARNINGS[:unmarked]]
            end
          when :block
            orphaned << key
            kept << [path, WARNINGS[:block]]
          when :user
            user_candidates << [path, key]
          end
        end
      end

      user_candidates.each do |path, key|
        kept << [path, WARNINGS[:user]] if orphaned.include?(key)
      end

      Result.new(removed: removed, kept: kept, skipped: nil)
    end

    # The lines a build prints for a sweep: every deleted file and every kept
    # one by name, one per line.
    def report_lines(result, base: nil)
      shown = ->(path) { base ? path.sub(%r{\A#{Regexp.escape(base)}/}, '') : path }
      lines = []
      lines << [:warn, result.skipped] if result.skipped
      unless result.removed.empty?
        lines << [:info, "Pruned #{result.removed.size} generated file(s) whose layout is gone:"]
        result.removed.each { |path| lines << [:info, "  - #{shown.call(path)}"] }
      end
      unless result.kept.empty?
        lines << [:warn, "#{result.kept.size} file(s) whose layout is gone were kept:"]
        result.kept.each { |path, why| lines << [:warn, "  - #{shown.call(path)}: #{why}"] }
      end
      lines
    end

    def remove_dir_if_empty(dir, root)
      return if File.expand_path(dir) == File.expand_path(root)
      return unless (Dir.entries(dir) - %w[. ..]).empty?

      Dir.rmdir(dir)
    rescue SystemCallError
      nil
    end
  end
end
