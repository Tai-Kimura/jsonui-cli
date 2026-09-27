# frozen_string_literal: true

require 'fileutils'
require_relative '../../../core/converter_generator_core'

module SjuiTools
  module UIKit
    module XcodeProject
      module Generators
        # What one UIKit `g view / partial / collection` run changes before and
        # during its Xcode step, so that a failure there leaves the tree as it
        # was: the scaffold files the run created (from the record the shared
        # overwrite decision keeps — a file that was there is never deleted),
        # the directories it made, and project.pbxproj as it was when the run
        # began (an earlier add_file of the same run may have saved it).
        #
        # Until 1.9.0 a failure left the tree half-changed and, for one kind
        # of failure, said nothing: `XcodeProjectManager#add_file` rescues its
        # own errors and answers :failed, and the generators went on to "Xcode
        # project: no file added" and exit 0 with the new files on disk and out
        # of the project (a read-only project.pbxproj, measured 2026-09-26);
        # `g partial` had no rollback at all, and `g collection` rolled back only
        # the file whose step raised. Ticket
        # generate-commands-overwrite-edited-files-and-ignore-their-flags.
        class ScaffoldTransaction
          # Raised when a file could not be added to the Xcode project.
          class XcodeStepFailed < StandardError; end

          attr_reader :record

          def initialize(project_file_path)
            @record = JsonUIShared::ConverterGeneratorCore.scaffold_record
            @pbxproj = pbxproj_path(project_file_path)
            @pbxproj_bytes = @pbxproj && File.file?(@pbxproj) ? File.binread(@pbxproj) : nil
            @dirs = []
          end

          # FileUtils.mkdir_p that remembers each directory it made.
          def mkdir_p(dir)
            missing = []
            path = File.expand_path(dir)
            until File.directory?(path)
              missing << path
              parent = File.dirname(path)
              break if parent == path

              path = parent
            end
            FileUtils.mkdir_p(dir)
            @dirs.concat(missing)
            !missing.empty?
          end

          # add_file's answers, [[path, answer], ...]: raises XcodeStepFailed
          # naming each file whose answer was :failed (the ERROR add_file
          # logged says why).
          def check!(answers)
            failed = answers.select { |_, answer| answer == :failed }.map { |path, _| File.basename(path) }
            return if failed.empty?

            raise XcodeStepFailed, "could not add #{failed.join(', ')} to the Xcode project (the ERROR above says why)"
          end

          # Deletes the files this run created, removes the directories it made
          # once they are empty, and puts project.pbxproj back. Says each.
          def roll_back
            created = JsonUIShared::ConverterGeneratorCore.created_scaffold_files(@record)
            created.each do |path|
              next unless File.exist?(path)

              File.delete(path)
              puts "Deleted: #{path} (this run created it)"
            end
            (@record[:kept] + (@record[:overwritten] || [])).uniq.each do |path|
              puts "Not deleted: #{path} (it was there before this run)" if File.exist?(path)
            end
            @dirs.uniq.sort_by { |d| -d.length }.each do |dir|
              Dir.rmdir(dir) if File.directory?(dir) && Dir.empty?(dir)
            end
            restore_pbxproj
          end

          private

          def pbxproj_path(project_file_path)
            return nil unless project_file_path

            path = project_file_path.to_s
            path.end_with?('.pbxproj') ? path : File.join(path, 'project.pbxproj')
          end

          def restore_pbxproj
            return unless @pbxproj_bytes && File.file?(@pbxproj)
            return if File.binread(@pbxproj) == @pbxproj_bytes

            File.binwrite(@pbxproj, @pbxproj_bytes)
            puts "Restored: #{@pbxproj} (as it was before this run)"
          end
        end
      end
    end
  end
end
