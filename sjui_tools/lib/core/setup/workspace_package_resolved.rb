# frozen_string_literal: true

require 'fileutils'
require 'json'

module SjuiTools
  module Core
    module Setup
      # The `.xcworkspace`'s `Package.resolved`.
      #
      # setup used to create this file with `"pins" => []` whenever it was
      # missing, behind an `unless File.exist?` guard. Two consequences, both
      # measured on two faces of one consumer on 2026-09-10:
      #
      #   * `xcodebuild -project` reads the OTHER copy — the one under
      #     `<app>.xcodeproj/project.xcworkspace/…` with the real pins — so a
      #     deploy bakes the right versions, while opening the `.xcworkspace`
      #     in Xcode resolves from zero pins. The two builds can disagree
      #     about every dependency AND BOTH SUCCEED; nothing prints a version.
      #   * because of the `unless`, the empty file is written once and never
      #     touched again. Ceasing to create it repairs nothing for a tree
      #     that already has one — which is every tree that ran setup.
      #
      # So: never write an empty one, and reclaim the empty ones already
      # written. `reclaim` returns counts rather than a boolean because the
      # thing to assert is the SIDE EFFECT: a check that the file "is correct
      # afterwards" is satisfied just as well by a run that deleted it and
      # wrote it back.
      module WorkspacePackageResolved
        RELATIVE = File.join('xcshareddata', 'swiftpm', 'Package.resolved').freeze

        # removed: an empty file deleted / filled: an empty file overwritten
        # with the project's real pins / kept: a file with pins, untouched /
        # absent: nothing there, which is now the state setup leaves behind
        Outcome = Struct.new(:removed, :filled, :kept, :absent, :path, :pins) do
          def acted?
            removed + filled > 0
          end
        end

        module_function

        # Pins in a Package.resolved, or nil when the file cannot be read as
        # one. Version 1 nests them under "object"; versions 2 and 3 put them
        # at the top level. A reader that knows only one shape answers "0
        # pins" for a full file — the same answer it gives for the empty
        # shell this module exists to find.
        def pin_count(path)
          return nil unless File.file?(path)
          data = JSON.parse(File.read(path))
          return nil unless data.is_a?(Hash)
          pins = data['pins']
          if pins.nil? && data['object'].is_a?(Hash)
            pins = data['object']['pins']
          end
          pins.is_a?(Array) ? pins.size : nil
        rescue JSON::ParserError, SystemCallError
          nil
        end

        # The copy `xcodebuild -project` reads, which is where the real pins are.
        def project_copy_path(project_file_path)
          File.join(project_file_path, 'project.xcworkspace', RELATIVE)
        end

        def workspace_copy_path(workspace_path)
          File.join(workspace_path, RELATIVE)
        end

        # Reclaim an empty workspace Package.resolved, leaving a non-empty one
        # alone. Prefers the project's real pins over deletion: an absent file
        # makes Xcode resolve from scratch, which is correct but is also the
        # state that produced the split in the first place.
        def reclaim(workspace_path, project_file_path)
          shell = workspace_copy_path(workspace_path)
          outcome = Outcome.new(0, 0, 0, 0, shell, nil)
          unless File.exist?(shell)
            outcome.absent = 1
            return outcome
          end

          count = pin_count(shell)
          outcome.pins = count
          # nil means "not readable as a Package.resolved" — not ours to
          # judge, and deleting a file we cannot parse would destroy work.
          if count.nil? || count > 0
            outcome.kept = 1
            return outcome
          end

          source = project_copy_path(project_file_path)
          source_pins = pin_count(source)
          if source_pins && source_pins > 0
            FileUtils.cp(source, shell)
            outcome.filled = 1
            outcome.pins = source_pins
          else
            File.delete(shell)
            outcome.removed = 1
          end
          outcome
        end

        # One line for EVERY outcome, including the ones where nothing
        # happened. Staying silent when there is nothing to reclaim makes
        # "this tree was repaired" and "this version does not repair
        # anything" print the same thing — which is how the empty file
        # survived from 2026-03 to 2026-09 without being noticed.
        def report(outcome)
          if outcome.filled > 0
            puts "Reclaimed the workspace Package.resolved: filled #{outcome.pins} pin(s) " \
                 "from the project copy (#{outcome.path})"
          elsif outcome.removed > 0
            puts "Reclaimed the workspace Package.resolved: removed the empty file, " \
                 "no project copy to fill it from (#{outcome.path})"
          elsif outcome.kept > 0
            pins = outcome.pins.nil? ? 'unreadable' : "#{outcome.pins} pin(s)"
            puts "Workspace Package.resolved left as it is (#{pins}): #{outcome.path}"
          else
            puts "No workspace Package.resolved; Xcode will resolve and write one: #{outcome.path}"
          end
          outcome
        end
      end
    end
  end
end
