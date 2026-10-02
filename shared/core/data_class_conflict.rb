# frozen_string_literal: true

require 'set'

module JsonUIShared
  # One data name declared twice with two types, where a face builds ONE Data
  # type from both declarations. Every face keeps the first declaration in
  # document order and drops the rest. Until jsonui-cli 1.9.6 sjui / kjui
  # dropped them silently (ticket data-name-declared-twice-with-two-types-is-
  # dropped-silently; ruling 2026-10-02 — a warning on every face, not an
  # error), and rjui wrote every one, which tsc rejects (ticket rjui-data-
  # name-declared-twice-is-written-twice).
  #
  # What "one Data type" is differs per face, and each face reports only what
  # it merges:
  #   sjui / kjui   the screen with its includes expanded inline
  #                 (data_model_updater_core.rb), so a partial and the screen
  #                 declaring one name meet here;
  #   rjui          one layout file — its root's data and its data-only
  #                 nodes. A partial is its own component with its own Data
  #                 type there, so declarations across an include never meet.
  #
  # Types are compared as the face writes them — after its TypeConverter
  # normalization (and the Event signature) — so two spellings of one type
  # are one type. Default values are not compared.
  #
  # The text is this file's, so it reads the same on every face; the
  # `WARNING:` head is a shape `jui build`'s warning count matches.
  class DataClassConflict
    def self.message(layout, name, kept, dropped)
      "WARNING: #{layout}: data property '#{name}' is declared as '#{kept}' and as '#{dropped}'. " \
        "The Data type keeps the first ('#{kept}') and drops the other — declare it once, or with one type."
    end

    def initialize(layout)
      @layout = layout
      @reported = Set.new
    end

    # Prints the warning once per layout, name and pair of types; returns the
    # message, or nil when the types agree or it was already said.
    def report(name, kept, dropped)
      kept = kept.to_s
      dropped = dropped.to_s
      return nil if kept == dropped
      return nil unless @reported.add?([name, kept, dropped])

      text = self.class.message(@layout, name, kept, dropped)
      puts "\e[33m  #{text}\e[0m"
      text
    end
  end
end
