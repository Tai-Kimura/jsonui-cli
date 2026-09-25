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
#   3. no layout under the layouts directory has the name it was generated
#      for — or, for an output the generator places by the layout's own
#      directory (a GeneratedView), the layout of that name MOVED: the file is
#      outside every directory a layout of its name is written to, and the
#      copy in one of those directories already exists. (Before that copy is
#      written, the old one is kept: it is the only one.)
#
# A file that meets 1 and 3 but not 2 is not the generator's to delete, and is
# named in a warning instead:
#   - an output the generator owns only in part (a Compose GeneratedView: the
#     generator rewrites the GENERATED_CODE block and nothing outside it);
#   - an output with no @generated line (a Data file from an older generator);
#   - a file the user writes (a View, a ViewModel). These are named only when
#     a generated output of the same name was found orphaned in the same run
#     (for a moved layout, only in the same directory as the stale copy): a
#     hand-written view that never had a layout (a toast, a licenses screen)
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
    # home_dir: only for an output placed by the layout's own directory — the
    #          writer's own function from a layout's path (relative to the
    #          layouts directory) to the directory it writes that output in
    Kind = Struct.new(:dir, :pattern, :owner, :home_dir, keyword_init: true)

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

    def moved_warning(owner, current)
      head = "its layout moved (the current copy is in #{current})"
      case owner
      when :block
        "#{head}; the generator owns only the GENERATED_CODE block, so it was not deleted — " \
          'delete it if nothing outside that block was edited by hand'
      when :user then "#{head}; this file is yours, so it was not deleted"
      else "#{head}, but it has no @generated line, so it was not deleted — delete it by hand if a generator wrote it"
      end
    end

    def name_key(name)
      name.to_s.delete('_-').downcase
    end

    # [name key, path of the layout that places it] for every name a layout
    # under layouts_dir gives its outputs: each file's base name, and for a
    # responsive variant (home@regular.json) also the `<base><Class>Variant`
    # its variant view is named after, placed with its base screen.
    def layout_entries(layouts_dir)
      return [] unless layouts_dir && Dir.exist?(layouts_dir)

      Dir.glob(File.join(layouts_dir, '**', '*.json')).sort.flat_map do |path|
        rel = path.sub(%r{\A#{Regexp.escape(layouts_dir)}/}, '')
        next [] if rel.start_with?('Resources/', 'Styles/')

        stem, size_class = File.basename(path, '.json').split('@', 2)
        dir = File.dirname(rel)
        base_rel = dir == '.' ? "#{stem}.json" : File.join(dir, "#{stem}.json")
        entries = [[name_key(stem), base_rel]]
        entries << [name_key("#{stem}#{size_class}Variant"), base_rel] if size_class
        entries
      end
    end

    def layout_names(layouts_dir)
      Set.new(layout_entries(layouts_dir).map(&:first))
    end

    def generated?(path)
      File.foreach(path).first(HEAD_LINES).any? { |line| line.include?(SENTINEL) }
    rescue ArgumentError, Errno::ENOENT, Errno::EISDIR
      false
    end

    def sweep(layouts_dir:, kinds:)
      entries = layout_entries(layouts_dir)
      names = Set.new(entries.map(&:first))
      # An empty set cannot tell "every layout was deleted" from "this is not
      # the layouts directory", and deleting on it would empty every output
      # directory at once.
      if names.empty?
        return Result.new(removed: [], kept: [],
                          skipped: "no layouts under #{layouts_dir}; nothing was pruned")
      end

      removed = []
      kept = []
      orphaned = Set.new   # names no layout has
      moved = {}           # [name, directory of a stale copy] => where the current one is
      user_candidates = []

      kinds.each do |kind|
        next unless kind.dir && Dir.exist?(kind.dir)

        homes = Hash.new { |hash, key| hash[key] = Set.new }
        if kind.home_dir
          entries.each { |key, base_rel| homes[key] << File.expand_path(kind.home_dir.call(base_rel)) }
        end

        Dir.glob(File.join(kind.dir, '**', '*')).sort.each do |path|
          next unless File.file?(path)

          match = kind.pattern.match(File.basename(path))
          next unless match

          key = name_key(match[:name])
          if kind.owner == :user
            user_candidates << [path, key]
            next
          end

          current = nil
          if names.include?(key)
            next unless kind.home_dir

            here = File.expand_path(File.dirname(path))
            next if homes[key].include?(here)

            current = homes[key].find { |dir| File.exist?(File.join(dir, File.basename(path))) }
            next unless current

            moved[[key, here]] = current.sub(%r{\A#{Regexp.escape(File.expand_path(kind.dir))}/}, '')
          else
            orphaned << key
          end
          shown_current = current && moved[[key, File.expand_path(File.dirname(path))]]

          if kind.owner == :generator && generated?(path)
            File.delete(path)
            removed << path
            remove_dir_if_empty(File.dirname(path), kind.dir)
          elsif kind.owner == :generator
            kept << [path, current ? moved_warning(:unmarked, shown_current) : WARNINGS[:unmarked]]
          else
            kept << [path, current ? moved_warning(:block, shown_current) : WARNINGS[:block]]
          end
        end
      end

      user_candidates.each do |path, key|
        if orphaned.include?(key)
          kept << [path, WARNINGS[:user]]
        elsif (current = moved[[key, File.expand_path(File.dirname(path))]])
          kept << [path, moved_warning(:user, current)]
        end
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
        lines << [:info, "Pruned #{result.removed.size} generated file(s) whose layout is gone or moved:"]
        result.removed.each { |path| lines << [:info, "  - #{shown.call(path)}"] }
      end
      unless result.kept.empty?
        lines << [:warn, "#{result.kept.size} file(s) whose layout is gone or moved were kept:"]
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
