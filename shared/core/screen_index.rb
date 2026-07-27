# frozen_string_literal: true

require 'json'
require_relative 'layout_variant'

module JsonUIShared
  # Screen identity for the platform code generators.
  #
  # Answers the only two questions code generation has to ask before it can
  # emit a screen marker: "is this layout a screen?" and "what is its
  # canonical id?". The rules are declared in
  # `shared/core/screen_identity.json`; this is the Ruby reader of that
  # canon, and `jui_tools/jui_cli/core/screen_identity.py` is the Python
  # one. The two are held to the same behavior by a cross-language
  # agreement test — if you change one, change both.
  #
  # Canonical rules implemented:
  #
  # - id = layout basename without `.json`, collected RECURSIVELY, unique
  #   project-wide, variants (`home@regular`) normalized to the base.
  # - classification = explicit `role` > referenced-as-cell/include >
  #   `partial: true` > screen. The derivation is deliberately imperfect,
  #   so `reason` is carried on every entry for tools to report.
  #
  # Usage:
  #   index = JsonUIShared::ScreenIndex.build('/path/to/Layouts')
  #   index.screen?('home')            # => true
  #   index.marker_for('home')         # => '__screen_home'
  #
  class ScreenIndex
    # Keys through which a layout instantiates ANOTHER layout. A layout on
    # the receiving end of one of these is not a screen — it renders inside
    # its host, potentially once per data row.
    NON_SCREEN_REFERENCE_KEYS = %w[cell header footer include].freeze

    # Same idea, but the value is a list of layout references.
    NON_SCREEN_REFERENCE_LIST_KEYS = %w[cellClasses].freeze

    # Roles a layout may declare explicitly on its root node.
    VALID_ROLES = %w[screen cell partial].freeze

    # Directories under the layout root that hold resources rather than
    # layouts. Their contents are skipped entirely — a resource file is
    # referenced by nobody, so without this it would default to a screen and
    # grow a marker. Canon: screenId.nonLayoutSubtrees.
    NON_LAYOUT_SUBTREES = %w[Resources Styles].freeze

    MARKER_PREFIX = '__screen_'

    Entry = Struct.new(:screen_id, :path, :role, :reason) do
      def screen?
        role == 'screen'
      end

      def marker
        ScreenIndex.marker_name(screen_id)
      end
    end

    # Runtime marker identifier for a screen id.
    def self.marker_name(screen_id)
      "#{MARKER_PREFIX}#{screen_id}"
    end

    # Canonical screen id for a layout path (variant-normalized).
    def self.screen_id_for_path(path)
      stem = File.basename(path.to_s)
      stem = stem[0...-'.json'.length] if stem.end_with?('.json')
      LayoutVariant.split(stem).first
    end

    # Classify every layout under +layouts_dir+ (recursive).
    #
    # +app_owned_screens+ are ids the app implements without a JsonUI
    # layout (a hand-written page). They are real navigation destinations,
    # so they enter the index as screens.
    def self.build(layouts_dir, app_owned_screens: nil)
      index = new
      index.send(:load!, layouts_dir, app_owned_screens)
      index
    end

    attr_reader :entries, :collisions

    def initialize
      @entries = {}
      @collisions = {}
    end

    def get(screen_id)
      @entries[screen_id]
    end

    def known?(screen_id)
      @entries.key?(screen_id)
    end

    def screen?(screen_id)
      entry = @entries[screen_id]
      !entry.nil? && entry.screen?
    end

    # True when the layout at +path+ is a screen (the form code generation
    # actually calls: it holds a path, not an id).
    def screen_for_path?(path)
      screen?(self.class.screen_id_for_path(path))
    end

    def marker_for(screen_id)
      self.class.marker_name(screen_id)
    end

    def screen_ids
      @entries.select { |_, v| v.screen? }.keys.sort
    end

    def non_screen_ids
      @entries.reject { |_, v| v.screen? }.keys.sort
    end

    # Name shapes that almost always mean "renders inside a host". Used ONLY
    # to flag a derived classification for human review — never to classify.
    REVIEW_SUFFIXES = /_(cell|header|footer|row|item)\z/

    # Screens whose role was DERIVED, not declared.
    #
    # This is the COMPLETE set of classifications the derivation could have
    # got wrong. `screens_needing_review` is only a name-based hint inside
    # it, so anything that reports "what needs checking" has to start here —
    # a hint presented as a complete list is what lets a wrongly-derived
    # screen keep its marker unnoticed.
    def derived_screen_ids
      @entries.values.select { |e| e.screen? && e.reason == 'default' }.map(&:screen_id).sort
    end

    # The subset of derived screens that are NAMED like a fragment.
    #
    # A hint, never a complete list: it only catches `_cell` / `_row` style
    # names. A cell instantiated from host-language code (CellBuilder, a
    # ViewModel assembling cellClasses) is referenced by no layout JSON and
    # is usually not named like one either, so it defaults to `screen` and
    # this misses it. Measured on a real project: 7 flagged here, 8 more
    # wrongly derived screens not flagged. Callers must present it as a hint
    # and surface `derived_screen_ids` as the set that actually needs review.
    def screens_needing_review
      @entries.values
              .select { |e| e.screen? && e.reason == 'default' && e.screen_id =~ REVIEW_SUFFIXES }
              .map(&:screen_id)
              .sort
    end

    # One-line summary plus any review hints, for a build to print.
    def report_lines
      lines = ["Screen identity: #{screen_ids.length} screen(s), #{non_screen_ids.length} non-screen(s)"]
      derived = derived_screen_ids
      unless derived.empty?
        lines << "  #{derived.length} of #{screen_ids.length} screen(s) DERIVED, not declared. " \
                 'Derivation cannot see cells built from host code; declare ' \
                 "\"role\": \"cell\" on any that are not screens " \
                 "('jui screens --json' lists them under derivedScreens)."
      end
      screens_needing_review.each do |id|
        lines << "  hint: '#{id}' is treated as a SCREEN (nothing references it as a cell/include). " \
                 "If that is wrong, add \"role\": \"cell\" to its layout root."
      end
      lines
    end

    # Derived classification, for tools to surface so authors can correct
    # outliers with an explicit `role`.
    def classification_report
      @entries.values.sort_by(&:screen_id).map do |entry|
        {
          'screen' => entry.screen_id,
          'role' => entry.role,
          'reason' => entry.reason,
          'path' => entry.path.to_s,
        }
      end
    end

    private

    def load!(layouts_dir, app_owned_screens)
      unless layouts_dir && File.directory?(layouts_dir.to_s)
        merge_app_owned!(app_owned_screens)
        return
      end

      documents = {}
      seen_paths = {}
      referenced = {}

      layout_files(layouts_dir).each do |path|
        screen_id = self.class.screen_id_for_path(path)
        data = load_json(path)
        collect_non_screen_references(data, referenced)

        # Variants collapse onto their base; the base file owns the entry.
        stem = File.basename(path, '.json')
        next unless LayoutVariant.split(stem)[1].nil?

        (seen_paths[screen_id] ||= []) << path
        documents[screen_id] ||= [path, data]
      end

      seen_paths.each do |screen_id, paths|
        @collisions[screen_id] = paths if paths.length > 1
      end

      documents.each do |screen_id, (path, data)|
        explicit = explicit_role(data)
        if explicit
          @entries[screen_id] = Entry.new(screen_id, path, explicit, 'explicit')
        elsif referenced.key?(screen_id)
          @entries[screen_id] = Entry.new(screen_id, path, 'cell', 'referenced')
        elsif data.is_a?(Hash) && data['partial'] == true
          @entries[screen_id] = Entry.new(screen_id, path, 'partial', 'partial-flag')
        else
          @entries[screen_id] = Entry.new(screen_id, path, 'screen', 'default')
        end
      end

      merge_app_owned!(app_owned_screens)
    end

    def merge_app_owned!(screen_ids)
      Array(screen_ids).each do |raw|
        next unless raw.is_a?(String) && !raw.empty?

        screen_id = self.class.screen_id_for_path(raw)
        # A declared id that also has a layout keeps its layout entry: the
        # declaration is for screens the app owns INSTEAD of a layout.
        @entries[screen_id] ||= Entry.new(screen_id, '', 'screen', 'app-owned')
      end
    end

    def layout_files(layouts_dir)
      root = layouts_dir.to_s
      Dir.glob(File.join(root, '**', '*.json')).sort.reject do |path|
        dirs = File.dirname(path).delete_prefix(root).split(File::SEPARATOR)
        (dirs & NON_LAYOUT_SUBTREES).any?
      end
    end

    def load_json(path)
      JSON.parse(File.read(path))
    rescue StandardError
      nil
    end

    def explicit_role(data)
      return nil unless data.is_a?(Hash)

      role = data['role']
      return role if role.is_a?(String) && VALID_ROLES.include?(role)

      nil
    end

    def collect_non_screen_references(node, out)
      case node
      when Hash
        NON_SCREEN_REFERENCE_KEYS.each do |key|
          value = node[key]
          out[self.class.screen_id_for_path(value)] = true if value.is_a?(String) && !value.empty?
        end
        NON_SCREEN_REFERENCE_LIST_KEYS.each do |key|
          value = node[key]
          next unless value.is_a?(Array)

          value.each do |item|
            out[self.class.screen_id_for_path(item)] = true if item.is_a?(String) && !item.empty?
          end
        end
        node.each_value { |value| collect_non_screen_references(value, out) }
      when Array
        node.each { |item| collect_non_screen_references(item, out) }
      end
    end
  end
end
